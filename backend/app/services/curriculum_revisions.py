"""Curriculum revisions (owner decision 2026-10-11, ADR-050).

A published curriculum is frozen. To change it, a manager creates a draft revision: a new curriculum
row with the same name and the next version (1.0 → 1.1), holding copies of the published version's
approved sources, topics, subtopics, objectives, section links and prerequisites, all with new IDs.
Learners' progress is tied to the curriculum it was made in, so nobody's progress moves by itself.

In the draft the manager can:
- swap a document for a newer version: upload it to the draft; once it is approved and ingested, its
  subtopics inherit the objectives of the old version's subtopics with the same heading (the section
  remapping) and the old version leaves the draft. Anything new or renamed needs an objective, which
  publishing already requires. Until then the draft keeps the old version's path;
- remove a source from the draft;
- leave subtopics out of the path, or bring them back;
- move topics up or down (within their document version).

Publishing a revision archives the previous published version. People who already started keep it;
assignments nobody has started yet move to the new version.
"""

import json
import re
from typing import Any

from sqlalchemy import Connection, text

from app.errors import ApiError
from app.repositories import commands
from app.services.curriculum_authoring import W, _bump, _draft, _manager, _one
from app.services.work_commands import _check_revision, _command, _id


def _rows(conn: Connection, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings()]


def next_version(conn: Connection, org, ws, name: str, version: str) -> str:
    """1.0 → 1.1 → 1.2 …, skipping versions this name already has."""
    m = re.fullmatch(r"(\d+)\.(\d+)", version.strip())
    major, minor = (int(m.group(1)), int(m.group(2))) if m else (None, 0)
    taken = {r[0] for r in conn.execute(text(f"SELECT version FROM {W}.curricula WHERE organization_id=:o AND workspace_id=:w AND lower(name)=lower(:n)"), {"o": org, "w": ws, "n": name})}
    while True:
        minor += 1
        candidate = f"{major}.{minor}" if major is not None else f"{version}-r{minor + 1}"
        if candidate not in taken:
            return candidate


def draft_revision_of(conn: Connection, org, ws, c: dict[str, Any]) -> dict[str, Any] | None:
    """The open draft with this curriculum's name, if any (one draft revision at a time)."""
    return _one(conn, f"""SELECT curriculum_id, version FROM {W}.curricula WHERE organization_id=:o AND workspace_id=:w AND lower(name)=lower(:n)
                          AND status='DRAFT' AND curriculum_id <> :c ORDER BY created_at DESC LIMIT 1""", {"o": org, "w": ws, "n": c["name"], "c": c["curriculum_id"]})


def other_versions(conn: Connection, org, ws, c: dict[str, Any]) -> list[dict[str, Any]]:
    return _rows(conn, f"""SELECT curriculum_id, version, status, published_at FROM {W}.curricula WHERE organization_id=:o AND workspace_id=:w
                           AND lower(name)=lower(:n) AND curriculum_id <> :c ORDER BY created_at""", {"o": org, "w": ws, "n": c["name"], "c": c["curriculum_id"]})


# ---------------------------------------------------------------- create a draft revision
def create(conn: Connection, token, curriculum_id: str, key: str, request_id) -> dict[str, Any]:
    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = _manager(conn, r, me)
        base = _one(conn, f"SELECT * FROM {W}.curricula WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c FOR UPDATE",
                    {"o": org, "w": ws, "c": _id(curriculum_id, "curriculum")})
        if not base:
            raise ApiError("NOT_FOUND", "This curriculum doesn't exist in this workspace.")
        if base["status"] != "PUBLISHED":
            raise ApiError("GUARD_FAILED", "Only a published curriculum needs a draft revision; a draft can be edited directly.")
        existing = draft_revision_of(conn, org, ws, base)
        if existing:
            return {"curriculum_id": str(existing["curriculum_id"]), "version": existing["version"], "existing": True}, 1
        version = next_version(conn, org, ws, base["name"], base["version"])
        p = {"o": org, "w": ws}
        new = conn.execute(text(f"""INSERT INTO {W}.curricula (organization_id, workspace_id, name, version, description, status, completion_policy_version)
                                    VALUES (:o, :w, :n, :v, :d, 'DRAFT', :cp) RETURNING curriculum_id"""),
                           {**p, "n": base["name"], "v": version, "d": base["description"], "cp": base["completion_policy_version"]}).scalar_one()
        old = base["curriculum_id"]
        # Sources: the approved exact versions only (a pending upload stays with the version it was made for).
        src_map: dict[Any, Any] = {}
        for s in _rows(conn, f"""SELECT cs.* FROM {W}.curriculum_sources cs JOIN {W}.knowledge_document_versions v
                                 ON v.organization_id=cs.organization_id AND v.workspace_id=cs.workspace_id AND v.document_version_id=cs.document_version_id
                                 WHERE cs.organization_id=:o AND cs.workspace_id=:w AND cs.curriculum_id=:c AND v.approval_status='APPROVED'""", {**p, "c": old}):
            src_map[s["curriculum_source_id"]] = conn.execute(text(f"""INSERT INTO {W}.curriculum_sources (organization_id, workspace_id, curriculum_id, document_id, document_version_id, relationship_type)
                                                                     VALUES (:o, :w, :c, :d, :v, :t) RETURNING curriculum_source_id"""),
                                                              {**p, "c": new, "d": s["document_id"], "v": s["document_version_id"], "t": s["relationship_type"]}).scalar_one()
        topic_map: dict[Any, Any] = {}
        for t in _rows(conn, f"SELECT * FROM {W}.curriculum_topics WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c AND active", {**p, "c": old}):
            topic_map[t["topic_id"]] = conn.execute(text(f"""INSERT INTO {W}.curriculum_topics (organization_id, workspace_id, curriculum_id, name, description, order_index, document_version_id)
                                                          VALUES (:o, :w, :c, :n, :d, :i, :v) RETURNING topic_id"""),
                                                    {**p, "c": new, "n": t["name"], "d": t["description"], "i": t["order_index"], "v": t["document_version_id"]}).scalar_one()
        sub_map: dict[Any, Any] = {}
        if topic_map:
            for s in _rows(conn, f"SELECT * FROM {W}.curriculum_subtopics WHERE organization_id=:o AND workspace_id=:w AND topic_id = ANY(:t) AND active", {**p, "t": list(topic_map)}):
                sub_map[s["subtopic_id"]] = conn.execute(text(f"""INSERT INTO {W}.curriculum_subtopics (organization_id, workspace_id, topic_id, name, description, order_index)
                                                               VALUES (:o, :w, :t, :n, :d, :i) RETURNING subtopic_id"""),
                                                         {**p, "t": topic_map[s["topic_id"]], "n": s["name"], "d": s["description"], "i": s["order_index"]}).scalar_one()
        if sub_map:
            for o in _rows(conn, f"SELECT * FROM {W}.learning_objectives WHERE organization_id=:o AND workspace_id=:w AND subtopic_id = ANY(:s)", {**p, "s": list(sub_map)}):
                _copy_objective(conn, org, ws, o, sub_map[o["subtopic_id"]])
            for x in _rows(conn, f"SELECT * FROM {W}.curriculum_prerequisites WHERE organization_id=:o AND workspace_id=:w AND subtopic_id = ANY(:s)", {**p, "s": list(sub_map)}):
                if x["prerequisite_subtopic_id"] in sub_map:
                    conn.execute(text(f"INSERT INTO {W}.curriculum_prerequisites (organization_id, workspace_id, subtopic_id, prerequisite_subtopic_id) VALUES (:o, :w, :s, :q)"),
                                 {**p, "s": sub_map[x["subtopic_id"]], "q": sub_map[x["prerequisite_subtopic_id"]]})
        for x in _rows(conn, f"SELECT * FROM {W}.curriculum_source_sections WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c", {**p, "c": old}):
            if x["curriculum_source_id"] in src_map and x["topic_id"] in topic_map and x["subtopic_id"] in sub_map:
                conn.execute(text(f"""INSERT INTO {W}.curriculum_source_sections (organization_id, workspace_id, curriculum_source_id, curriculum_id, document_version_id, section_id, topic_id, subtopic_id, relationship_type)
                                      VALUES (:o, :w, :cs, :c, :v, :sec, :t, :s, :rt)"""),
                             {**p, "cs": src_map[x["curriculum_source_id"]], "c": new, "v": x["document_version_id"], "sec": x["section_id"], "t": topic_map[x["topic_id"]],
                              "s": sub_map[x["subtopic_id"]], "rt": x["relationship_type"]})
        commands.audit(conn, org, ws, me, "curriculum.revision_created", "curriculum", new, 1, request_id)
        return {"curriculum_id": str(new), "version": version, "existing": False}, 1

    return _command(conn, token, "curriculum.create_revision", key, {"curriculum_id": curriculum_id}, run)


def _copy_objective(conn: Connection, org, ws, o: dict[str, Any], subtopic_id) -> None:
    conn.execute(text(f"""INSERT INTO {W}.learning_objectives (organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version, required, hint_policy, competency_id)
                          VALUES (:o, :w, :s, :d, CAST(:a AS jsonb), :cv, :r, CAST(:h AS jsonb), :comp)"""),
                 {"o": org, "w": ws, "s": subtopic_id, "d": o["description"], "a": _json(o["assessment_criteria"]), "cv": o["criteria_version"], "r": o["required"],
                  "h": _json(o["hint_policy"]), "comp": o["competency_id"]})


def _json(v: Any) -> str:
    return json.dumps(v if v is not None else {})


# ---------------------------------------------------------------- swapping and removing sources in a draft
def drop_version(conn: Connection, org, ws, curriculum_id, document_version_id) -> None:
    """Takes a document version out of a draft: its link, section links, topics, subtopics and their
    objectives and prerequisites. Drafts have no learners, so nothing else refers to them."""
    p = {"o": org, "w": ws, "c": curriculum_id, "v": document_version_id}
    subs = f"""SELECT s.subtopic_id FROM {W}.curriculum_subtopics s JOIN {W}.curriculum_topics t ON t.organization_id=s.organization_id AND t.workspace_id=s.workspace_id
               AND t.topic_id=s.topic_id WHERE t.organization_id=:o AND t.workspace_id=:w AND t.curriculum_id=:c AND t.document_version_id=:v"""
    conn.execute(text(f"DELETE FROM {W}.curriculum_source_sections WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c AND document_version_id=:v"), p)
    conn.execute(text(f"DELETE FROM {W}.curriculum_prerequisites WHERE organization_id=:o AND workspace_id=:w AND (subtopic_id IN ({subs}) OR prerequisite_subtopic_id IN ({subs}))"), p)
    conn.execute(text(f"DELETE FROM {W}.learning_objectives WHERE organization_id=:o AND workspace_id=:w AND subtopic_id IN ({subs})"), p)
    conn.execute(text(f"""DELETE FROM {W}.curriculum_subtopics WHERE organization_id=:o AND workspace_id=:w AND topic_id IN
                          (SELECT topic_id FROM {W}.curriculum_topics WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c AND document_version_id=:v)"""), p)
    conn.execute(text(f"DELETE FROM {W}.curriculum_topics WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c AND document_version_id=:v"), p)
    conn.execute(text(f"DELETE FROM {W}.curriculum_sources WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c AND document_version_id=:v"), p)


def older_versions(conn: Connection, org, ws, curriculum_id, document_version_id) -> list[Any]:
    """Other versions of the same document linked to this draft (the ones a newer upload replaces)."""
    return [r[0] for r in conn.execute(text(f"""SELECT cs.document_version_id FROM {W}.curriculum_sources cs
                                                JOIN {W}.knowledge_document_versions v ON v.organization_id=cs.organization_id AND v.workspace_id=cs.workspace_id AND v.document_version_id=:v
                                                WHERE cs.organization_id=:o AND cs.workspace_id=:w AND cs.curriculum_id=:c AND cs.document_id=v.document_id AND cs.document_version_id <> :v"""),
                                       {"o": org, "w": ws, "c": curriculum_id, "v": document_version_id})]


def replace_after_ingestion(conn: Connection, org, ws, curriculum_id, document_version_id) -> int:
    """Once a newer version of a linked document is ingested into a draft: its subtopics inherit the
    objectives of the older version's subtopics with the same heading (the section remapping), then the
    older version leaves the draft. Until then the draft keeps the older version's path, so a rejected
    or failed upload changes nothing. Returns how many objectives carried over."""
    old = older_versions(conn, org, ws, curriculum_id, document_version_id)
    if not old:
        return 0
    n = carry_objectives(conn, org, ws, curriculum_id, document_version_id, old)
    for v in old:
        drop_version(conn, org, ws, curriculum_id, v)
    return n


def remove_source(conn: Connection, token, curriculum_id: str, curriculum_source_id: str, key: str, expected_revision: int | None, request_id) -> dict[str, Any]:
    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = _manager(conn, r, me)
        c = _draft(conn, org, ws, curriculum_id)
        _check_revision(c["revision"], expected_revision, "curriculum")
        s = _one(conn, f"SELECT * FROM {W}.curriculum_sources WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c AND curriculum_source_id=:s",
                 {"o": org, "w": ws, "c": c["curriculum_id"], "s": _id(curriculum_source_id, "source")})
        if not s:
            raise ApiError("NOT_FOUND", "This source isn't linked to this draft.")
        drop_version(conn, org, ws, c["curriculum_id"], s["document_version_id"])
        rev = _bump(conn, c)
        commands.audit(conn, org, ws, me, "curriculum.source_removed", "curriculum", c["curriculum_id"], rev, request_id)
        return {"curriculum_id": curriculum_id}, rev

    return _command(conn, token, "curriculum.remove_source", key, {"curriculum_id": curriculum_id, "source": curriculum_source_id, "expected_revision": expected_revision}, run)


# ---------------------------------------------------------------- editing the path
def _draft_subtopic(conn: Connection, org, ws, c: dict[str, Any], subtopic_id: str) -> dict[str, Any]:
    s = _one(conn, f"""SELECT s.* FROM {W}.curriculum_subtopics s JOIN {W}.curriculum_topics t ON t.organization_id=s.organization_id AND t.workspace_id=s.workspace_id AND t.topic_id=s.topic_id
                       WHERE s.organization_id=:o AND s.workspace_id=:w AND s.subtopic_id=:s AND t.curriculum_id=:c AND t.active FOR UPDATE OF s""",
             {"o": org, "w": ws, "s": _id(subtopic_id, "subtopic"), "c": c["curriculum_id"]})
    if not s:
        raise ApiError("NOT_FOUND", "This subtopic isn't in this draft's path.")
    return s


def set_subtopic(conn: Connection, token, curriculum_id: str, subtopic_id: str, included: bool, key: str, expected_revision: int | None, request_id) -> dict[str, Any]:
    """Leave a subtopic out of the path (it keeps its objective), or bring it back."""

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = _manager(conn, r, me)
        c = _draft(conn, org, ws, curriculum_id)
        _check_revision(c["revision"], expected_revision, "curriculum")
        s = _draft_subtopic(conn, org, ws, c, subtopic_id)
        conn.execute(text(f"UPDATE {W}.curriculum_subtopics SET active=:a, updated_at=now(), revision=revision+1 WHERE organization_id=:o AND workspace_id=:w AND subtopic_id=:s"),
                     {"a": included, "o": org, "w": ws, "s": s["subtopic_id"]})
        rev = _bump(conn, c)
        commands.audit(conn, org, ws, me, "curriculum.path_edited", "curriculum", c["curriculum_id"], rev, request_id)
        return {"curriculum_id": curriculum_id}, rev

    return _command(conn, token, "curriculum.set_subtopic", key, {"curriculum_id": curriculum_id, "subtopic": subtopic_id, "included": included, "expected_revision": expected_revision}, run)


def move_topic(conn: Connection, token, curriculum_id: str, topic_id: str, direction: str, key: str, expected_revision: int | None, request_id) -> dict[str, Any]:
    """Swap a topic with its neighbour among the active topics of the same document version."""

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = _manager(conn, r, me)
        c = _draft(conn, org, ws, curriculum_id)
        _check_revision(c["revision"], expected_revision, "curriculum")
        p = {"o": org, "w": ws, "c": c["curriculum_id"]}
        t = _one(conn, f"SELECT * FROM {W}.curriculum_topics WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c AND topic_id=:t AND active FOR UPDATE",
                 {**p, "t": _id(topic_id, "topic")})
        if not t:
            raise ApiError("NOT_FOUND", "This topic isn't in this draft's path.")
        group = _rows(conn, f"""SELECT topic_id, order_index FROM {W}.curriculum_topics WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c AND active
                                AND document_version_id IS NOT DISTINCT FROM :v ORDER BY order_index FOR UPDATE""", {**p, "v": t["document_version_id"]})
        i = next(n for n, x in enumerate(group) if x["topic_id"] == t["topic_id"])
        j = i - 1 if direction == "UP" else i + 1
        if j < 0 or j >= len(group):
            raise ApiError("GUARD_FAILED", "This topic is already at the " + ("top." if direction == "UP" else "bottom."))
        other = group[j]
        spare = conn.execute(text(f"SELECT coalesce(max(order_index), 0) + 1 FROM {W}.curriculum_topics WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c"), p).scalar_one()
        for tid, idx in ((t["topic_id"], spare), (other["topic_id"], t["order_index"]), (t["topic_id"], other["order_index"])):  # swap through a free slot
            conn.execute(text(f"UPDATE {W}.curriculum_topics SET order_index=:i, updated_at=now(), revision=revision+1 WHERE organization_id=:o AND workspace_id=:w AND topic_id=:t"),
                         {**p, "i": idx, "t": tid})
        rev = _bump(conn, c)
        commands.audit(conn, org, ws, me, "curriculum.path_edited", "curriculum", c["curriculum_id"], rev, request_id)
        return {"curriculum_id": curriculum_id}, rev

    return _command(conn, token, "curriculum.move_topic", key, {"curriculum_id": curriculum_id, "topic": topic_id, "direction": direction, "expected_revision": expected_revision}, run)


# ---------------------------------------------------------------- after ingestion: carry objectives over
def _heading(name: str) -> str:
    return re.sub(r"^\s*\d+(\.\d+)*\.?\s*", "", name or "").strip().lower()


def carry_objectives(conn: Connection, org, ws, curriculum_id, document_version_id, old_versions: list[Any]) -> int:
    """New subtopics without an objective inherit the objective of an older version's subtopic with the same heading."""
    p = {"o": org, "w": ws, "c": curriculum_id, "v": document_version_id, "old": list(old_versions)}
    new_subs = _rows(conn, f"""SELECT s.subtopic_id, s.name FROM {W}.curriculum_subtopics s JOIN {W}.curriculum_topics t
                               ON t.organization_id=s.organization_id AND t.workspace_id=s.workspace_id AND t.topic_id=s.topic_id
                               WHERE t.organization_id=:o AND t.workspace_id=:w AND t.curriculum_id=:c AND t.document_version_id=:v
                               AND NOT EXISTS (SELECT 1 FROM {W}.learning_objectives lo WHERE lo.organization_id=s.organization_id AND lo.workspace_id=s.workspace_id AND lo.subtopic_id=s.subtopic_id)""", p)
    old = _rows(conn, f"""SELECT s.name, lo.* FROM {W}.curriculum_subtopics s
                          JOIN {W}.curriculum_topics t ON t.organization_id=s.organization_id AND t.workspace_id=s.workspace_id AND t.topic_id=s.topic_id
                          JOIN {W}.learning_objectives lo ON lo.organization_id=s.organization_id AND lo.workspace_id=s.workspace_id AND lo.subtopic_id=s.subtopic_id
                          WHERE t.organization_id=:o AND t.workspace_id=:w AND t.curriculum_id=:c AND t.document_version_id = ANY(:old)""", p)
    by_heading: dict[str, dict[str, Any]] = {}
    for o in old:
        by_heading.setdefault(_heading(o["name"]), o)
    n = 0
    for s in new_subs:
        o = by_heading.get(_heading(s["name"]))
        if o:
            _copy_objective(conn, org, ws, o, s["subtopic_id"])
            n += 1
    return n


# ---------------------------------------------------------------- publishing a revision
def after_publish(conn: Connection, org, ws, c: dict[str, Any], me, request_id) -> list[str]:
    """Archives the previously published version(s) and moves assignments nobody has started yet."""
    p = {"o": org, "w": ws, "n": c["name"], "c": c["curriculum_id"]}
    prev = [r[0] for r in conn.execute(text(f"""UPDATE {W}.curricula SET status='ARCHIVED', updated_at=now(), revision=revision+1
                                                WHERE organization_id=:o AND workspace_id=:w AND lower(name)=lower(:n) AND status='PUBLISHED' AND curriculum_id <> :c
                                                RETURNING curriculum_id"""), p)]
    if prev:  # a learning assignment and the assignment it came from move together; checked at commit
        conn.execute(text("SET CONSTRAINTS workweave.fk_learning_assignments_169 DEFERRED"))
    for old in prev:
        q = {**p, "old": old}
        unstarted = f"""NOT EXISTS (SELECT 1 FROM {W}.learning_sessions ls WHERE ls.organization_id=la.organization_id AND ls.workspace_id=la.workspace_id AND ls.learning_assignment_id=la.learning_assignment_id)
                        AND NOT EXISTS (SELECT 1 FROM {W}.employee_learning_progress pr WHERE pr.organization_id=la.organization_id AND pr.workspace_id=la.workspace_id AND pr.learning_assignment_id=la.learning_assignment_id)"""
        moved = [r[0] for r in conn.execute(text(f"""UPDATE {W}.learning_assignments la SET curriculum_id=:c, updated_at=now(), revision=revision+1
                                                     WHERE la.organization_id=:o AND la.workspace_id=:w AND la.curriculum_id=:old AND la.status='ACTIVE' AND {unstarted}
                                                     RETURNING la.originating_assignment_id"""), q)]
        conn.execute(text(f"""UPDATE {W}.curriculum_assignments ca SET curriculum_id=:c, updated_at=now(), revision=revision+1
                              WHERE ca.organization_id=:o AND ca.workspace_id=:w AND ca.curriculum_id=:old AND ca.status='ACTIVE'
                              AND (ca.assignment_id = ANY(:moved) OR NOT EXISTS (SELECT 1 FROM {W}.learning_assignments la WHERE la.organization_id=ca.organization_id
                                   AND la.workspace_id=ca.workspace_id AND la.originating_assignment_id=ca.assignment_id))"""),
                     {**q, "moved": [m for m in moved if m]})
        commands.audit(conn, org, ws, me, "curriculum.archived", "curriculum", old, 1, request_id)
    return [str(x) for x in prev]
