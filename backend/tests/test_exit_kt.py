"""Exit KT from the database (owner decisions 2026-10-10, ADR-039)."""

import uuid

from tests.test_companion_commands import count, fresh
from tests.test_demo_slice import code, pick

H = {"X-WorkWeave-Client": "web"}


def k() -> str:
    return str(uuid.uuid4())


def case(client) -> dict:
    r = client.get("/api/exit-kt/case")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def post(client, path: str, c: dict, **body):
    return client.post(f"/api/exit-kt/{path}", json={"idempotency_key": k(), "expected_revision": c["revision"], **body}, headers=H)


def ok(r) -> dict:
    assert r.status_code == 200, r.text
    return r.json()["data"]


def item(c: dict, title: str) -> dict:
    return next(i for i in c["knowledge_items"] if i["title"] == title)


def test_each_role_sees_its_part_of_the_case(client):
    fresh(client, "Alex")  # the employee in a role transition
    c = case(client)
    assert c["case_kind"] == "ROLE_TRANSITION" and len(c["knowledge_items"]) == 3 and len(c["findings"]) == 3
    assert c["interviews"] == []  # consent-bound interviews are never copied into a demo
    assert c["artifacts"][0]["revisions"][0]["status"] == "DRAFT"  # Alex's own private draft
    assert item(c, "Calibration and evidence handling")["linked_source"].startswith("SOP-001 v3.3")
    assert {x["label"] for x in c["checklist"]} == {"Evidence-based escalation practice documented and approved", "Machine #14 maintenance responsibility transferred or explicitly retained"}
    pick(client, "Morgan")  # reviewer and manager
    m = case(client)
    assert m["artifacts"] == [] and m["knowledge_items"]  # drafts stay private until submitted
    pick(client, "Jamie")  # proposed successor
    j = case(client)
    assert j["knowledge_items"] == [] and j["findings"] == [] and j["artifacts"] == [] and j["package"]["draft_sections"] == []
    pick(client, "Sam")
    assert case(client) is None


def test_ai_parts_say_they_arent_connected(client):
    fresh(client, "Alex")  # EXIT_KT_ENGINE=none in tests
    c = case(client)
    kti = item(c, "Evidence-based escalation practice")["kt_item_id"]
    assert not c["kt_available"] and c["copilot"][0]["text"].startswith("The knowledge-transfer assistant isn't connected")
    for path, body in (("discovery", {"idempotency_key": k()}), (f"knowledge-items/{kti}/interview", {"idempotency_key": k(), "consent": True}),
                       ("copilot", {"idempotency_key": k(), "text": "What do I own?"})):
        r = client.post(f"/api/exit-kt/{path}", json=body, headers=H)
        assert code(r) == "CAPABILITY_UNAVAILABLE", path


def test_manual_knowledge_and_findings(client, engine):
    ws = fresh(client, "Alex")
    c = case(client)
    c2 = ok(post(client, "knowledge-items", c, title="Vendor escalation contacts", description="Who to call at the parts vendor."))
    added = item(c2, "Vendor escalation contacts")
    assert added["origin"] == "MANUAL" and added["kt_status"] == "INTERVIEW_REQUIRED"
    stale = post(client, "knowledge-items", c, title="x")
    assert stale.status_code == 409 and code(stale) == "REVISION_CONFLICT"
    linked = ok(post(client, f"knowledge-items/{item(c2, 'Calibration and evidence handling')['kt_item_id']}/link-existing", c2))
    assert item(linked, "Calibration and evidence handling")["kt_status"] == "COMPLETE"
    f = linked["findings"][0]
    assert code(post(client, f"findings/{f['finding_id']}/review", linked, decision="DISMISS", reason=" ")) == "MALFORMED_INPUT"
    reviewed = ok(post(client, f"findings/{f['finding_id']}/review", linked, decision="CONFIRM", reason="v3.3 notes still in the shared drive."))
    assert next(x for x in reviewed["findings"] if x["finding_id"] == f["finding_id"])["review_reason"] == "v3.3 notes still in the shared drive."
    assert count(engine, ws, "SELECT count(*) FROM workweave.audit_events WHERE workspace_id=:w AND action LIKE 'exit_kt_%'") == 3


def _approved_and_promoted(client) -> dict:
    """Alex edits and submits the draft; Morgan approves and promotes it."""
    c = case(client)
    art = c["artifacts"][0]
    c = ok(client.patch(f"/api/exit-kt/artifacts/{art['artifact_id']}", json={"idempotency_key": k(), "expected_revision": c["revision"], "content": "1. Cite the source version.\n2. Keep the cause unknown."}, headers=H))
    rev = c["artifacts"][0]["current_revision_id"]
    c = ok(post(client, f"artifacts/{art['artifact_id']}/submit", c, artifact_revision_id=rev, audience="TEAM"))
    assert c["artifacts"][0]["revisions"][-1]["status"] == "PENDING_REVIEW"
    pick(client, "Morgan")
    m = case(client)
    assert m["artifacts"][0]["revisions"][-1]["content"].startswith("1. Cite")  # submitted, so the reviewer sees it
    m = ok(post(client, f"artifacts/{art['artifact_id']}/decision", m, artifact_revision_id=rev, decision="APPROVE"))
    m = ok(post(client, f"artifacts/{art['artifact_id']}/promote", m, artifact_revision_id=rev))
    assert m["artifacts"][0]["promotion"] == {"document_version_label": "KT-001 v1", "index_status": "PENDING"}
    assert item(m, "Evidence-based escalation practice")["kt_status"] == "COMPLETE"
    return m


def test_knowledge_needs_exact_revision_review_and_isnt_self_approved(client, engine):
    ws = fresh(client, "Alex")
    c = case(client)
    art = c["artifacts"][0]
    rev = art["current_revision_id"]
    self_approve = post(client, f"artifacts/{art['artifact_id']}/decision", c, artifact_revision_id=rev, decision="APPROVE")
    assert self_approve.status_code == 403
    c = ok(post(client, f"artifacts/{art['artifact_id']}/submit", c, artifact_revision_id=rev, audience="TEAM"))
    pick(client, "Morgan")
    m = case(client)
    back = ok(post(client, f"artifacts/{art['artifact_id']}/decision", m, artifact_revision_id=rev, decision="REQUEST_REVISION", comment="Add who verifies the evidence."))
    assert back["artifacts"][0]["revisions"][-1]["status"] == "REVISION_REQUIRED"
    early = post(client, f"artifacts/{art['artifact_id']}/promote", back, artifact_revision_id=rev)
    assert early.status_code == 409  # only approved knowledge is promoted
    pick(client, "Alex")
    a = case(client)
    a = ok(client.patch(f"/api/exit-kt/artifacts/{art['artifact_id']}", json={"idempotency_key": k(), "expected_revision": a["revision"], "content": "Ask the reviewer to verify."}, headers=H))
    assert [r["version"] for r in a["artifacts"][0]["revisions"]] == [1, 2]  # the reviewed revision is immutable
    assert count(engine, ws, "SELECT count(*) FROM workweave.knowledge_document_versions v JOIN workweave.knowledge_documents d ON d.document_id=v.document_id WHERE v.workspace_id=:w AND d.document_type='KT_ARTIFACT'") == 0


def test_transfer_needs_approval_receipt_and_effective_time(client, engine):
    ws = fresh(client, "Alex")
    m = _approved_and_promoted(client)
    t = m["transfers"][0]
    blocked = post(client, f"transfers/{t['transfer_id']}/confirm", m)
    assert blocked.status_code == 409 and "no approved successor package" in blocked.json()["error"]["message"]
    pick(client, "Alex")
    a = case(client)
    a = ok(post(client, "package/assemble", a))
    assert next(s for s in a["package"]["draft_sections"] if s["title"] == "Approved knowledge")["content"] == "Requesting evidence-based clarification (KT-001 v1)"
    a = ok(post(client, "package/submit", a))
    pick(client, "Morgan")
    m = ok(post(client, "package/decision", case(client), decision="APPROVE"))
    version = m["package"]["current_approved_version_id"]
    blocked = post(client, f"transfers/{t['transfer_id']}/confirm", m)
    assert "hasn't confirmed receipt" in blocked.json()["error"]["message"]
    pick(client, "Jamie")
    j = case(client)
    assert j["package"]["versions"][0]["sections"] and j["package"]["draft_sections"] == []
    j = ok(client.post(f"/api/exit-kt/package/versions/{version}/receipt", json={"idempotency_key": k()}, headers=H))
    assert j["package"]["receipts"] == [{"package_version_id": version, "employee_id": j["package"]["successor_employee_id"]}]
    pick(client, "Morgan")
    m = case(client)
    blocked = post(client, f"transfers/{t['transfer_id']}/confirm", m)
    assert "effective time" in blocked.json()["error"]["message"]
    m = ok(post(client, f"transfers/{t['transfer_id']}/effective-time", m))
    m = ok(post(client, f"transfers/{t['transfer_id']}/confirm", m))
    moved = next(r for r in m["responsibilities"] if r["responsibility_id"] == t["responsibility_id"])
    assert moved["owner_employee_id"] == j["package"]["successor_employee_id"] and moved["ownership_revision"] == 2
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='exit_kt.responsibility_transferred'") == 1
    # Checklist: only that item's reviewed evidence resolves it; then the case can complete.
    know = next(x for x in m["checklist"] if "documented and approved" in x["label"])
    resp = next(x for x in m["checklist"] if "transferred or explicitly retained" in x["label"])
    wrong = post(client, f"checklist/{know['checklist_item_id']}/resolve", m, evidence_ref=f"transfer:{t['transfer_id']}")
    assert wrong.status_code == 409
    early = post(client, "complete", m)
    assert early.status_code == 409
    m = ok(post(client, f"checklist/{know['checklist_item_id']}/resolve", m, evidence_ref=f"promotion:{m['artifacts'][0]['artifact_id']}"))
    m = ok(post(client, f"checklist/{resp['checklist_item_id']}/resolve", m, evidence_ref=f"transfer:{t['transfer_id']}"))
    done = ok(post(client, "complete", m))
    assert done["status"] == "COMPLETE"


def test_a_returned_package_and_a_checklist_exception(client):
    fresh(client, "Alex")
    a = ok(post(client, "package/submit", ok(post(client, "package/assemble", case(client)))))
    assert a["package"]["status"] == "SUBMITTED"
    assert code(post(client, "package/decision", a, decision="APPROVE")) == "FORBIDDEN"  # not their own
    pick(client, "Morgan")
    m = case(client)
    assert code(post(client, "package/decision", m, decision="REJECT")) == "MALFORMED_INPUT"
    m = ok(post(client, "package/decision", m, decision="REJECT", comment="Include the recurring review."))
    assert m["package"]["status"] == "REJECTED" and m["package"]["review_comment"] == "Include the recurring review."
    x = next(i for i in m["checklist"] if "transferred or explicitly retained" in i["label"])
    m = ok(post(client, f"checklist/{x['checklist_item_id']}/exception", m, reason="Alex keeps this responsibility in the new role."))
    after = next(i for i in m["checklist"] if i["checklist_item_id"] == x["checklist_item_id"])
    assert after["status"] == "RESOLVED" and after["exception_reason"] and after["evidence_refs"] == []
    pick(client, "Jamie")
    assert code(post(client, f"checklist/{m['checklist'][0]['checklist_item_id']}/exception", case(client), reason="x")) == "FORBIDDEN"


def test_the_manager_assigns_the_successor_which_never_transfers_ownership(client, engine):
    ws = fresh(client, "Morgan")
    m = case(client)
    dana = next(p["employee_id"] for p in client.get("/api/personas").json()["data"] if p["first_name"] == "Dana")
    m = ok(post(client, "successor", m, successor_employee_id=dana))
    assert m["package"]["successor_employee_id"] == dana
    assert code(post(client, "successor", m, successor_employee_id=m["employee_id"])) == "MALFORMED_INPUT"  # not the person handing over
    assert all(r["owner_employee_id"] == m["employee_id"] for r in m["responsibilities"])  # nothing transferred
    pick(client, "Alex")
    assert code(post(client, "successor", case(client), successor_employee_id=dana)) == "FORBIDDEN"


def test_the_manager_opens_a_case_once_per_person(client):
    fresh(client, "Morgan")
    people = {p["first_name"]: p["employee_id"] for p in client.get("/api/personas").json()["data"]}
    body = {"idempotency_key": k(), "employee_id": people["Jamie"], "case_kind": "DEPARTURE"}
    assert code(client.post("/api/exit-kt/cases", json=body, headers=H)) == "MALFORMED_INPUT"  # a departure needs a date
    r = client.post("/api/exit-kt/cases", json={**body, "idempotency_key": k(), "final_working_date": "2026-11-30"}, headers=H)
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    assert c["employee_id"] == people["Jamie"] and c["case_kind"] == "DEPARTURE" and c["status"] == "DISCOVERY" and c["final_working_date"] == "2026-11-30"
    again = client.post("/api/exit-kt/cases", json={**body, "idempotency_key": k(), "final_working_date": "2026-11-30"}, headers=H)
    assert code(again) == "GUARD_FAILED"
    assert code(client.post("/api/exit-kt/cases", json={**body, "idempotency_key": k(), "employee_id": people["Morgan"], "case_kind": "ROLE_TRANSITION"}, headers=H)) == "FORBIDDEN"
    pick(client, "Alex")  # a shift lead without responsibility:transfer
    assert code(client.post("/api/exit-kt/cases", json={**body, "idempotency_key": k(), "employee_id": people["Sam"], "case_kind": "ROLE_TRANSITION"}, headers=H)) == "FORBIDDEN"
