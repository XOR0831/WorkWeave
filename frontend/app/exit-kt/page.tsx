"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { useOnChange } from "@/lib/preview/use-on-change";
import { RequireSession } from "@/components/shell/AppShell";
import { Dialog, ErrorNotice, Loading, PageHeader, PageError, StateView, Status, humanize } from "@/components/ui";
import { useCommand, useResource, useRuntime, useSession } from "@/lib/preview/client-context";
import { KtCopilot } from "@/features/exit-kt/Discovery";
import { KnowledgeArea } from "@/features/exit-kt/KnowledgeArea";
import { ResponsibilityArea } from "@/features/exit-kt/ResponsibilityArea";
import { CompletenessArea, FindingsArea, SuccessorView } from "@/features/exit-kt/OtherAreas";
import type { CaseKind, ExitKtCase } from "@/types/contracts";

const AREAS = [
  { id: "knowledge", label: "Knowledge Transfer" },
  { id: "responsibility", label: "Responsibility Transfer" },
  { id: "findings", label: "AI Findings" },
  { id: "completeness", label: "KT Completeness" },
] as const;
type AreaId = (typeof AREAS)[number]["id"];

/** Reads/writes ?area= via useSyncExternalStore so the static export needs no Suspense boundary. */
const AREA_EVENT = "ww-area-change";
function subscribeArea(cb: () => void) {
  window.addEventListener("popstate", cb);
  window.addEventListener(AREA_EVENT, cb);
  return () => {
    window.removeEventListener("popstate", cb);
    window.removeEventListener(AREA_EVENT, cb);
  };
}
function useAreaParam(): [AreaId, (a: AreaId) => void] {
  const raw = useSyncExternalStore(subscribeArea, () => new URLSearchParams(window.location.search).get("area"), () => null);
  const area: AreaId = AREAS.some((x) => x.id === raw) ? (raw as AreaId) : "knowledge";
  const set = (a: AreaId) => {
    const url = new URL(window.location.href);
    url.searchParams.set("area", a);
    window.history.replaceState(null, "", url);
    window.dispatchEvent(new Event(AREA_EVENT));
  };
  return [area, set];
}

export default function ExitKtPage() {
  return (
    <RequireSession>
      <ExitKt />
    </RequireSession>
  );
}

function ExitKt() {
  const { session, nameOf } = useSession();
  const pid = session?.persona.employee_id;
  const kt = useResource((c) => c.getExitKtCase(), [pid]);
  const [area, setArea] = useAreaParam();
  const [setup, setSetup] = useState(false);
  const api = useRuntime().mode === "http";
  // While promoted knowledge is being indexed (ADR-053), refresh until it's searchable or failed.
  const indexing = api && !!kt.data?.artifacts.some((a) => a.promotion?.index_status === "PENDING");
  const reload = kt.reload;
  useEffect(() => {
    if (!indexing) return;
    const t = window.setInterval(reload, 4000);
    return () => window.clearInterval(t);
  }, [indexing, reload]);

  if (kt.loading) return <Loading label="Loading knowledge transfer" />;
  if (kt.error) return <PageError error={kt.error} onRetry={kt.reload} />;
  // API (docs/32): the manager (responsibility:transfer) opens cases; the preview also lets the employee.
  const canOpen = session!.persona.grants.includes("responsibility.confirm") || (!api && session!.persona.grants.includes("exitkt.subject"));
  if (!kt.data)
    return (
      <>
        <StateView title="You aren't part of a knowledge-transfer case" action={canOpen ? <button className="btn btn-primary" onClick={() => setSetup(true)}>Open a case</button> : undefined}>
          Cases appear here for the departing or transitioning employee, their reviewer, and the proposed successor.
        </StateView>
        <CaseSetup open={setup} onClose={() => setSetup(false)} />
      </>
    );
  const c: ExitKtCase = kt.data;
  const role = c.employee_id === pid ? "SUBJECT" : session!.persona.grants.includes("responsibility.confirm") || c.reviewer_employee_id === pid ? "REVIEWER" : "SUCCESSOR";

  return (
    <div className="stack">
      <PageHeader
        eyebrow={c.case_kind === "DEPARTURE" ? "Preserve knowledge · Departure" : "Preserve knowledge · Transfer a role"}
        title={c.case_kind === "DEPARTURE" ? "Someone leaves. Knowledge stays." : "A role changes. Knowledge stays."}
        purpose={
          <>
            {humanize(c.case_kind)}
            {c.case_kind === "DEPARTURE" && c.final_working_date ? `, final working day ${c.final_working_date.toLowerCase()}` : ""} for {nameOf(c.employee_id)} · Reviewer {nameOf(c.reviewer_employee_id)} · Successor {nameOf(c.package.successor_employee_id)}
          </>
        }
        actions={
          <>
            <Status value={c.status} />
            {role !== "SUCCESSOR" && canOpen && (
              <button className="btn btn-small" onClick={() => setSetup(true)}>
                New case
              </button>
            )}
          </>
        }
      />
      {role === "SUCCESSOR" ? (
        <SuccessorView c={c} />
      ) : (
        // The work in the centre; the assistant alone on the right, like the Companion and Shift Handover.
        <div className={api ? "split" : "stack"}>
          <div className="stack" style={{ minWidth: 0 }}>
            <CaseSummary c={c} showOpenWork={area !== "completeness"} />
            <div className="tabs" role="tablist" aria-label="Exit KT areas">
            {AREAS.map((a) => (
              <button
                key={a.id}
                role="tab"
                id={`tab-${a.id}`}
                aria-controls={`panel-${a.id}`}
                aria-selected={area === a.id}
                tabIndex={area === a.id ? 0 : -1}
                className="tab"
                onClick={() => setArea(a.id)}
                onKeyDown={(e) => {
                  const i = AREAS.findIndex((x) => x.id === area);
                  const n = e.key === "ArrowRight" ? (i + 1) % AREAS.length : e.key === "ArrowLeft" ? (i + AREAS.length - 1) % AREAS.length : -1;
                  if (n >= 0) {
                    setArea(AREAS[n]!.id);
                    document.getElementById(`tab-${AREAS[n]!.id}`)?.focus();
                  }
                }}
              >
                {a.label}
              </button>
            ))}
          </div>
            <section className="kt-panel" role="tabpanel" id={`panel-${area}`} aria-labelledby={`tab-${area}`}>
              {area === "knowledge" && <KnowledgeArea c={c} role={role} />}
              {area === "responsibility" && <ResponsibilityArea c={c} role={role} />}
              {area === "findings" && <FindingsArea c={c} />}
              {area === "completeness" && <CompletenessArea c={c} />}
            </section>
          </div>
          {api && (
            <aside className="split-aside" aria-label="Knowledge-transfer assistant panel">
              <KtCopilot c={c} />
            </aside>
          )}
        </div>
      )}
      <CaseSetup open={setup} onClose={() => setSetup(false)} />
    </div>
  );
}

/**
 * Independent case decisions (approval, package, receipt, effective time, ownership, gaps).
 * Each is its own action; none completes another, so there is no single progress bar.
 */
function CaseSummary({ c, showOpenWork }: { c: ExitKtCase; showOpenWork: boolean }) {
  const { nameOf } = useSession();
  const revisions = c.artifacts.map((a) => a.revisions.find((r) => r.artifact_revision_id === a.current_revision_id)?.status);
  const approval = revisions.includes("PENDING_REVIEW") ? "PENDING_REVIEW" : revisions.length && revisions.every((r) => r === "APPROVED") ? "APPROVED" : revisions.length ? "DRAFT" : "NOT_STARTED";
  const pkg = c.package;
  const received = Boolean(pkg.current_approved_version_id && pkg.receipts.some((r) => r.package_version_id === pkg.current_approved_version_id));
  const transfer = c.transfers.find((t) => t.status !== "TRANSFERRED" && t.status !== "DISCOVERED") ?? c.transfers.find((t) => t.status === "TRANSFERRED");
  const transferred = c.transfers.some((t) => t.status === "TRANSFERRED");
  const gaps = c.knowledge_items.filter((k) => (k.documentation_status === "MISSING" || k.documentation_status === "OUTDATED") && k.kt_status !== "COMPLETE").length;
  const rows: [string, React.ReactNode][] = [
    ["Knowledge approval", <Status key="a" value={approval} label={approval === "NOT_STARTED" ? "None submitted" : undefined} />],
    ["Package", <Status key="p" value={pkg.status} />],
    ["Successor receipt", <Status key="r" value={received ? "COMPLETED" : "NOT_STARTED"} label={received ? "Received" : "Not received"} />],
    ["Effective time", transfer ? <Status key="e" value={transfer.effective_reached ? "COMPLETED" : "DRAFT"} label={transfer.effective_reached ? "Reached" : transfer.effective_label} /> : <span key="e" className="small muted">No transfer proposed</span>],
    ["Ownership transfer", <Status key="o" value={transferred ? "TRANSFERRED" : "NOT_STARTED"} label={transferred ? "Transferred" : "Not confirmed"} />],
    ["Knowledge gaps", <Status key="g" value={gaps ? "MISSING" : "COMPLETED"} label={gaps ? `${gaps} open` : "None open"} />],
  ];
  return (
    <section className="kt-summary stack" aria-labelledby="h-case">
      <section className="panel">
        <h2 id="h-case">Case summary</h2>
        <p className="small muted">
          {c.responsibilities.map((r) => r.title).join(", ") || "No responsibilities listed"} · Successor {nameOf(pkg.successor_employee_id)}
        </p>
        <dl className="case-rows">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        <p className="small muted">These are independent decisions; none happens automatically.</p>
      </section>
      {showOpenWork && c.open_work_note && <p className="panel panel-quiet small kt-open-work">{c.open_work_note}</p>}
    </section>
  );
}

function CaseSetup({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { personas, session } = useSession();
  const cmd = useCommand();
  const api = useRuntime().mode === "http";
  const [employee, setEmployee] = useState(session?.persona.employee_id ?? "");
  const [kind, setKind] = useState<CaseKind>("ROLE_TRANSITION");
  const [date, setDate] = useState("");
  const [reviewer, setReviewer] = useState(personas.find((p) => p.grants.includes("knowledge.review"))?.employee_id ?? "");
  const [created, setCreated] = useState(false);
  useOnChange(open, () => {
    if (!open) setCreated(false);
  });
  return (
    <Dialog
      open={open}
      title="Open a knowledge-transfer case"
      onClose={onClose}
      footer={
        !created && (
          <button
            className="btn btn-primary"
            disabled={cmd.pending}
            onClick={async () => {
              const r = await cmd.run((c, k) => c.createExitKtCase({ employee_id: employee, case_kind: kind, final_working_date: date || undefined, reviewer_employee_id: reviewer }, { idempotency_key: k }));
              if (r) setCreated(true);
            }}
          >
            Open case
          </button>
        )
      }
    >
      {created ? (
        <div className="notice notice-ok">
          <span>{api ? "Case opened in discovery. Run discovery so the assistant can reconstruct what the records show." : "Case opened in discovery. This preview keeps the scenario's main case on screen; the new case validates the setup form only."}</span>
        </div>
      ) : (
        <>
          <div className="field">
            <label htmlFor="cs-emp">Employee</label>
            <select id="cs-emp" value={employee} onChange={(e) => setEmployee(e.target.value)}>
              {personas.map((p) => (
                <option key={p.employee_id} value={p.employee_id}>
                  {p.first_name} {p.last_name}
                </option>
              ))}
            </select>
          </div>
          <fieldset>
            <legend>Case type</legend>
            <label className="choice">
              <input type="radio" checked={kind === "ROLE_TRANSITION"} onChange={() => setKind("ROLE_TRANSITION")} /> Role transition (staying with the organization)
            </label>
            <label className="choice">
              <input type="radio" checked={kind === "DEPARTURE"} onChange={() => setKind("DEPARTURE")} /> Departure
            </label>
          </fieldset>
          {kind === "DEPARTURE" && (
            <div className="field">
              <label htmlFor="cs-date">Final working date</label>
              <input id="cs-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              <span className="hint">Required for departures only.</span>
            </div>
          )}
          <div className="field">
            <label htmlFor="cs-rev">Knowledge reviewer</label>
            <select id="cs-rev" value={reviewer} onChange={(e) => setReviewer(e.target.value)}>
              {personas.map((p) => (
                <option key={p.employee_id} value={p.employee_id}>
                  {p.first_name} {p.last_name}
                </option>
              ))}
            </select>
          </div>
          <p className="small muted">Opening a case doesn&apos;t give consent to share interviews. The employee controls what they submit.</p>
          {cmd.error && <ErrorNotice error={cmd.error} />}
        </>
      )}
    </Dialog>
  );
}
