"use client";

import { useState } from "react";
import type { CanvasView, Citation, DelegationProposal, ReportedState, SyncStatus, WorkEvent, WorkItem, WorkDashboard } from "@/types/contracts";
import Link from "next/link";
import { useResource, useRuntime, useSession, useCommand } from "@/lib/preview/client-context";
import { Dialog, ErrorNotice, Evidence, FixtureTag, Loading, OriginTag, Status, humanize } from "@/components/ui";
import { RichText } from "@/lib/text/RichText";
import { summarizeSteps } from "@/lib/text/steps";
import { AssignmentPanel } from "@/features/companion/Assignment";

/** Predefined canvas renderers. The view is chosen only by a validated ui_action (no local routing). */
/** API mode, until the engine can change the canvas: the briefing opens item details and the lead's
 * proposal in a drawer over it (the canvas itself doesn't change). */
export interface BriefingActions {
  onOpenItem: (item: WorkItem) => void;
  onOpenProposal: (id: string) => void;
}

export function Canvas({ view, onCite, onReport, actions }: { view: CanvasView; onCite: (c: Citation) => void; onReport: (item: WorkItem) => void; actions?: BriefingActions }) {
  switch (view.view) {
    case "BRIEFING":
      return <Briefing actions={actions} />;
    case "WORK_ITEMS":
      return <WorkItems filters={view.filters} selectedId={view.selected_id} onReport={onReport} />;
    case "WORK_UPDATES":
      return <Updates />;
    case "FOCUS_PLAN":
      return <FocusPlan />;
    case "GUIDANCE":
      return <Guidance id={view.guidance_id} onCite={onCite} onReport={onReport} />;
    case "DELEGATION_PROPOSAL":
      return <Delegation id={view.proposal_id} />;
  }
}

export function canvasTitle(view: CanvasView, workItems: string) {
  switch (view.view) {
    case "BRIEFING":
      return "Work briefing";
    case "WORK_ITEMS":
      return view.selected_id ? "Item detail" : `${workItems.charAt(0).toUpperCase()}${workItems.slice(1)}${view.filters?.status?.length === 1 ? `: ${humanize(view.filters.status[0]!).toLowerCase()} only` : ""}`;
    case "WORK_UPDATES":
      return "Recent work updates";
    case "FOCUS_PLAN":
      return "Focus plan";
    case "GUIDANCE":
      return "Guidance from approved sources";
    case "DELEGATION_PROPOSAL":
      return "Delegation proposal";
  }
}

/** ADR-033: what someone reported in the Companion, next to (never instead of) the ticket's status. */
export function ReportChip({ report }: { report?: ReportedState | null }) {
  if (!report || report.sync_status === "SUPERSEDED" || report.sync_status === "MATCHED") return null;
  const said = report.reported_status === "DONE" ? "done" : report.reported_status === "BLOCKED" ? "blocked" : "in progress";
  const label = report.sync_status === "NEEDS_REVIEW" ? `Reported ${said} · the ticket system closed it differently` : `Reported ${said} · waiting for the ticket system`;
  return <Status value={report.sync_status} label={label} />;
}

function SyncChip({ sync }: { sync?: SyncStatus }) {
  if (!sync) return null;
  const label = { AWAITING_SOURCE: "Waiting for the ticket system", MATCHED: "Matches the ticket system", NEEDS_REVIEW: "Needs review", SUPERSEDED: "Replaced by a newer report" }[sync];
  return <Status value={sync} label={label} />;
}

function SourceTag({ source }: { source?: WorkEvent["source"] }) {
  if (source === "TICKET_SYSTEM") return <span className="fixture-tag">Ticket system</span>;
  if (source === "COMPANION") return <span className="fixture-tag">Companion report</span>;
  return null;
}

export function Dashboard({ data }: { data?: WorkDashboard }) {
  const { session } = useSession();
  if (!data) return <Loading label="Loading dashboard" />;
  const t = session?.scenario.terminology;
  return (
    <div className="stack-s">
      <p className="small dash-shift">
        {data.shift_label ? <span>{data.shift_label}. </span> : <span className="muted">No active shift. </span>}
        {data.incoming_continuity ? <span className="muted">Incoming: {data.incoming_continuity}.</span> : <span className="muted">No incoming handover.</span>}
      </p>
      <div className="metric-row">
        <div className="metric">
          <span className="metric-value">{data.active_count}</span>
          <span className="metric-label">{data.scope === "OWN" ? `Your ${t?.workItems ?? "work"}` : data.scope === "TEAM" ? `Team ${t?.workItems ?? "work"}` : `Active ${t?.workItems}`}</span>
        </div>
        <div className="metric">
          <span className="metric-value">{data.blocked_count}</span>
          <span className="metric-label">Blocked</span>
        </div>
        <div className="metric">
          <span className="metric-value">{data.overdue_count}</span>
          <span className="metric-label">Overdue</span>
        </div>
        {data.can_delegate && data.unassigned_count !== undefined && (
          <div className="metric">
            <span className="metric-value">{data.unassigned_count}</span>
            <span className="metric-label">Unassigned</span>
          </div>
        )}
        <div className="metric">
          <span className="stack-s" style={{ gap: 4 }}>
            <Status value={data.work_state} />
            <span className="small muted">Temporary, from counts</span>
          </span>
          <span className="metric-label">Work state</span>
        </div>
      </div>
    </div>
  );
}

function Briefing({ actions }: { actions?: BriefingActions }) {
  const { session, nameOf } = useSession();
  const dash = useResource((c) => c.getWorkDashboard(), [session?.persona.employee_id]);
  const items = useResource((c) => c.listWorkItems(), [session?.persona.employee_id]);
  const events = useResource((c) => c.listWorkEvents(), [session?.persona.employee_id]);
  const isLead = dash.data?.can_delegate ?? Boolean(session?.persona.grants.includes("delegation.confirm"));
  const proposals = useResource((c) => (actions && isLead ? c.listProposals() : Promise.resolve([])), [session?.persona.employee_id, Boolean(actions), isLead]);
  if (dash.loading || items.loading) return <Loading />;
  const open = (items.data ?? []).filter((i) => !i.historical && !["COMPLETED", "CLOSED", "CANCELLED"].includes(i.status));
  const pending = (events.data ?? []).filter((e) => e.validation === "PENDING" && e.event_type === "REPORTED_COMPLETE");
  const openProposal = (proposals.data ?? []).find((p) => (p.status === "PROPOSED" || p.status === "EDITED") && !p.overtaken);
  const itemOf = (id: string) => (items.data ?? []).find((i) => i.work_item_id === id);
  return (
    <div className="stack">
      <section>
        <h3>Priorities</h3>
        <ul className="list" style={{ marginTop: 8 }}>
          {(dash.data?.priorities ?? []).map((p) => (
            <li key={p} className="list-item">
              {p}
            </li>
          ))}
          {!dash.data?.priorities.length && <li className="muted">No priorities recorded.</li>}
        </ul>
      </section>
      <section>
        <h3>Open work</h3>
        <ul className="list" style={{ marginTop: 8 }}>
          {open.map((i) => (
            <li key={i.work_item_id} className="list-item">
              <div className="row-between">
                <span>
                  <span className="mono-id">{i.external_id}</span> {i.title}
                </span>
                <Status value={i.status} />
              </div>
              <span className="small muted">
                {i.due_label}. {i.assignee_id ? `Assigned to ${nameOf(i.assignee_id)}` : "Not assigned"}
              </span>
              {i.report && (
                <span>
                  <ReportChip report={i.report} />
                </span>
              )}
              {actions && (
                <div>
                  <button className="btn btn-small" onClick={() => actions.onOpenItem(i)} aria-label={`Open ${i.external_id} details`}>
                    {i.assignee_id === session?.persona.employee_id ? "Open and report" : "Open details"}
                  </button>
                </div>
              )}
            </li>
          ))}
          {open.length === 0 && <li className="muted">No open work.</li>}
        </ul>
      </section>
      {actions && (dash.data?.awaiting_sync_count ?? 0) > 0 && (
        <div className="notice notice-info">
          <span className="notice-title">Waiting for the ticket system</span>
          <span>
            {dash.data!.awaiting_sync_count} {dash.data!.awaiting_sync_count === 1 ? "item was" : "items were"} reported done here but {dash.data!.awaiting_sync_count === 1 ? "is" : "are"} still open in the {dash.data!.system_name ?? "ticket system"}. They stay on your list, at lower priority, until it&apos;s resolved there.
          </span>
        </div>
      )}
      {actions && (dash.data?.needs_review_count ?? 0) > 0 && (
        <div className="notice notice-warn">
          <span className="notice-title">Report and ticket system disagree</span>
          <span>The ticket system closed {dash.data!.needs_review_count === 1 ? "an item" : "items"} differently from what was reported. Check the item&apos;s timeline.</span>
        </div>
      )}
      {actions && openProposal && (
        <div className="notice notice-info">
          <span className="notice-title">Delegation proposal to review</span>
          <span>
            {openProposal.items.length} open {openProposal.items.length === 1 ? "item has" : "items have"} a suggested assignee. Nothing is assigned until you confirm.
          </span>
          <div>
            <button className="btn btn-small btn-primary" onClick={() => actions.onOpenProposal(openProposal.delegation_proposal_id)}>
              Review proposal
            </button>
          </div>
        </div>
      )}
      {pending.length > 0 && (
        <div className="notice notice-warn">
          <span className="notice-title">Waiting for validation</span>
          {pending.map((e) => (
            <span key={e.work_event_id}>
              {nameOf(e.employee_id)} reported completion{itemOf(e.work_item_id) ? ` of ${itemOf(e.work_item_id)!.external_id}` : ""} {e.observed_label}. A report isn&apos;t official completion until the lead validates it.
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function WorkItems({ filters, selectedId, onReport }: { filters?: { status?: string[] }; selectedId?: string; onReport: (i: WorkItem) => void }) {
  const { session, nameOf } = useSession();
  const items = useResource((c) => c.listWorkItems(), [session?.persona.employee_id]);
  if (items.loading) return <Loading />;
  if (items.error) return <ErrorNotice error={items.error} onRetry={items.reload} />;
  const all = (items.data ?? []).filter((i) => !i.historical);
  if (selectedId) {
    const item = (items.data ?? []).find((i) => i.work_item_id === selectedId);
    if (!item) return <p className="muted">That item isn&apos;t available to you.</p>;
    return <ItemDetail item={item} onReport={onReport} />;
  }
  const shown = filters?.status ? all.filter((i) => filters.status!.includes(i.status)) : all;
  return (
    <div className="stack-s">
      {filters?.status && (
        <p className="small muted">
          Filter: {filters.status.map((s) => humanize(s).toLowerCase()).join(", ")}. {shown.length} of {all.length} shown.
        </p>
      )}
      {shown.length === 0 ? (
        <div className="state" style={{ padding: 16 }}>
          <h2>Nothing matches this filter</h2>
          <p>Ask in the conversation to change or clear the filter.</p>
        </div>
      ) : (
        <ul className="list">
          {shown.map((i) => (
            <li key={i.work_item_id} className="list-item">
              <div className="row-between">
                <span>
                  <span className="mono-id">{i.external_id}</span> {i.title}
                </span>
                <span className="row">
                  <Status value={i.priority === "HIGH" ? "BLOCKED" : "NOT_STARTED"} label={`${humanize(i.priority)} priority`} />
                  <Status value={i.status} />
                </span>
              </div>
              <span className="small">{i.description}</span>
              <span className="small muted">
                {i.due_label}. {i.assignee_id ? `Assigned to ${nameOf(i.assignee_id)}` : "Not assigned"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ItemDetail({ item, onReport }: { item: WorkItem; onReport: (i: WorkItem) => void }) {
  const { session, nameOf } = useSession();
  const events = useResource((c) => c.listWorkEvents(), [session?.persona.employee_id, item.work_item_id]);
  const api = useRuntime().mode === "http";
  const dash = useResource((c) => c.getWorkDashboard(), [session?.persona.employee_id]);
  const mine = item.assignee_id === session?.persona.employee_id;
  const evs = (events.data ?? []).filter((e) => e.work_item_id === item.work_item_id);
  return (
    <div className="stack">
      <div className="stack-s">
        <div className="row-between">
          <h3>
            <span className="mono-id">{item.external_id}</span> {item.title}
          </h3>
          <Status value={item.status} />
        </div>
        <p>{item.description}</p>
        <dl className="kv">
          <dt>Type</dt>
          <dd>{humanize(item.work_item_type)}</dd>
          <dt>Priority</dt>
          <dd>{humanize(item.priority)}</dd>
          <dt>Due</dt>
          <dd>{item.due_label}</dd>
          <dt>Assigned</dt>
          <dd>{item.assignee_id ? nameOf(item.assignee_id) : "Not assigned"}</dd>
          {item.report && (
            <>
              <dt>Reported</dt>
              <dd>
                <ReportChip report={item.report} /> {item.report.sync_status === "MATCHED" && <span className="small muted">Matches the ticket system.</span>}
              </dd>
            </>
          )}
          <dt>Revision</dt>
          <dd>{item.revision}</dd>
        </dl>
        <div className="row">
          {mine && !["COMPLETED", "CLOSED", "CANCELLED"].includes(item.status) && (
            <button className="btn btn-small" onClick={() => onReport(item)}>
              Report on this item
            </button>
          )}
          {api && (
            <Link className="btn btn-small" href={`/companion/tool/?item=${item.work_item_id}`}>
              Open in {dash.data?.system_name ?? "the ticket system"}
            </Link>
          )}
        </div>
        {api && <AssignmentPanel item={item} isLead={Boolean(dash.data?.can_delegate)} />}
      </div>
      <section>
        <h3>Timeline</h3>
        <ul className="list" style={{ marginTop: 8 }}>
          {evs.map((e) => (
            <li key={e.work_event_id} className={`list-item stitched stitched-${e.evidence_type.toLowerCase()}`}>
              <div className="row-between">
                <span className="row">
                  <b>{humanize(e.event_type)}</b>
                  <Evidence type={e.evidence_type} />
                  <SourceTag source={e.source} />
                  <SyncChip sync={e.sync_status} />
                  {e.validation && <Status value={e.validation} label={e.validation === "PENDING" ? "Awaiting validation" : humanize(e.validation)} />}
                </span>
                <span className="small muted">
                  {nameOf(e.employee_id)}, {e.observed_label}
                </span>
              </div>
              <span className="small">{e.description}</span>
            </li>
          ))}
          {evs.length === 0 && <li className="muted small">No permitted events yet.</li>}
        </ul>
      </section>
    </div>
  );
}

function Updates() {
  const { session, nameOf } = useSession();
  const events = useResource((c) => c.listWorkEvents(), [session?.persona.employee_id]);
  const items = useResource((c) => c.listWorkItems(), [session?.persona.employee_id]);
  if (events.loading) return <Loading />;
  const idOf = (id: string) => items.data?.find((i) => i.work_item_id === id)?.external_id ?? "";
  return (
    <ul className="list">
      {(events.data ?? []).map((e) => (
        <li key={e.work_event_id} className={`list-item stitched stitched-${e.evidence_type.toLowerCase()}`}>
          <div className="row-between">
            <span className="row">
              <span className="mono-id">{idOf(e.work_item_id)}</span> <b>{humanize(e.event_type)}</b> <Evidence type={e.evidence_type} /> <SourceTag source={e.source} /> <SyncChip sync={e.sync_status} />
              {e.validation && <Status value={e.validation} label={e.validation === "PENDING" ? "Awaiting validation" : humanize(e.validation)} />}
            </span>
            <span className="small muted">
              {nameOf(e.employee_id)}, {e.observed_label}
            </span>
          </div>
          <span className="small">{e.description}</span>
        </li>
      ))}
    </ul>
  );
}

function FocusPlan() {
  const { session } = useSession();
  const items = useResource((c) => c.listWorkItems(), [session?.persona.employee_id]);
  const events = useResource((c) => c.listWorkEvents(), [session?.persona.employee_id]);
  if (items.loading) return <Loading />;
  const open = (items.data ?? []).filter((i) => !i.historical && !["COMPLETED", "CLOSED", "CANCELLED"].includes(i.status));
  const pendingIds = new Set((events.data ?? []).filter((e) => e.validation === "PENDING").map((e) => e.work_item_id));
  const rank = (i: WorkItem) => (pendingIds.has(i.work_item_id) ? 0 : i.status === "BLOCKED" ? 1 : i.priority === "HIGH" ? 2 : 3);
  const ordered = [...open].sort((a, b) => rank(a) - rank(b));
  const why = (i: WorkItem) => (pendingIds.has(i.work_item_id) ? "A report is waiting for validation" : i.status === "BLOCKED" ? "Blocked; follow up on what it's waiting for" : i.priority === "HIGH" ? `High priority, ${i.due_label.toLowerCase()}` : i.due_label);
  return (
    <div className="stack-s">
      <p className="small muted">Ordered by pending validations, blockers, priority and deadlines. This is a work order, not a ranking of people.</p>
      <ol className="list">
        {ordered.map((i, n) => (
          <li key={i.work_item_id} className="list-item">
            <span>
              <b>{n + 1}.</b> <span className="mono-id">{i.external_id}</span> {i.title}
            </span>
            <span className="small muted">{why(i)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/**
 * Guidance in the work area: the ticket it is about, then a short checklist of the suggested steps.
 * The full answer stays in the conversation; sources open their excerpt in the source drawer.
 */
function Guidance({ id, onCite, onReport }: { id: string; onCite: (c: Citation) => void; onReport: (item: WorkItem) => void }) {
  const { session } = useSession();
  const api = useRuntime().mode === "http";
  const g = useResource((c) => c.getGuidance(id), [id]);
  const items = useResource((c) => c.listWorkItems(), [session?.persona.employee_id]);
  if (g.loading) return <Loading />;
  if (g.error) return <ErrorNotice error={g.error} onRetry={g.reload} />;
  const d = g.data!;
  const item = d.related_work_item_id ? items.data?.find((i) => i.work_item_id === d.related_work_item_id) : undefined;
  const steps = summarizeSteps(d.answer);
  return (
    <div className="stack">
      {item ? <ItemDetail item={item} onReport={onReport} /> : (
        <div className="row">
          <b>“{d.question}”</b>
          {!api && <FixtureTag />}
        </div>
      )}
      {d.answer_status === "INSUFFICIENT_EVIDENCE" && (
        <div className="notice notice-warn">
          <span className="notice-title">The approved sources don&apos;t answer this</span>
          <span>No procedure or value is suggested. Ask an authorized reviewer for the applicable source.</span>
        </div>
      )}
      <section className="stack-s" aria-labelledby={`steps-${id}`}>
        <h3 id={`steps-${id}`}>Suggested steps</h3>
        {steps.length > 0 ? (
          <ol className="steps-summary">
            {steps.map((s, i) => (
              <li key={i}>
                <b>{s.label}</b>
                {s.detail && <span className="small"> {s.detail}</span>}
              </li>
            ))}
          </ol>
        ) : (
          <div className="small">
            <RichText text={d.answer} />
          </div>
        )}
        <p className="small muted">The full answer is in the conversation{api ? "" : " (scripted preview)"}.</p>
      </section>
      {d.unknowns.length > 0 && (
        <div className="stitched stitched-unknown stack-s">
          <span className="row">
            <b>Unknown</b> <Evidence type="UNKNOWN" />
          </span>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {d.unknowns.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </div>
      )}
      <section className="stack-s">
        <h3>Sources</h3>
        {d.citations.length === 0 && <p className="small muted">No permitted sources are available for this answer.</p>}
        <div className="row">
          {d.citations.map((c) => (
            <button key={c.citation_id} className="cite" onClick={() => onCite(c)}>
              {c.label}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

export function Delegation({ id }: { id: string }) {
  const { personas, nameOf, session } = useSession();
  const p = useResource((c) => c.getProposal(id), [id]);
  const items = useResource((c) => c.listWorkItems(), [session?.persona.employee_id]);
  const cmd = useCommand();
  const [confirm, setConfirm] = useState(false);
  const [reject, setReject] = useState(false);
  const [reason, setReason] = useState("");
  if (p.loading) return <Loading />;
  if (p.error) return <ErrorNotice error={p.error} onRetry={p.reload} />;
  const prop = p.data as DelegationProposal;
  // Overtaken: every ticket in it already has someone (assigned automatically, ADR-035).
  const locked = prop.status === "CONFIRMED" || prop.status === "REJECTED" || Boolean(prop.overtaken);
  const wi = (wid: string) => items.data?.find((i) => i.work_item_id === wid);
  const candidates = personas.filter((x) => x.grants.includes("work.report") && x.employment_status !== "EXITED" && (!prop.candidate_ids || prop.candidate_ids.includes(x.employee_id)));
  return (
    <div className="stack">
      <div className="row-between">
        <span className="row">
          <Status value={prop.status} />
          <OriginTag origin={prop.origin} />
          <span className="small muted">Revision {prop.revision}</span>
        </span>
        {!locked && <span className="small">Nothing is assigned until you confirm.</span>}
        {prop.overtaken && <span className="small">These tickets were already assigned automatically by competency. Change an assignee from the ticket&apos;s details.</span>}
      </div>
      <div className="table-wrap" role="region" tabIndex={0} aria-label="Delegation assignments (scrolls horizontally)">
        <table>
          <caption className="sr-only">Proposed assignments</caption>
          <thead>
            <tr>
              <th scope="col">Work</th>
              <th scope="col">Recommended</th>
              <th scope="col">Final selection</th>
              <th scope="col">Reason and evidence</th>
            </tr>
          </thead>
          <tbody>
            {prop.items.map((it) => (
              <tr key={it.proposal_item_id}>
                <th scope="row">
                  <span className="mono-id">{wi(it.work_item_id)?.external_id}</span>
                  <br />
                  <span className="small muted">{wi(it.work_item_id)?.title}</span>
                </th>
                <td>{nameOf(it.recommended_employee_id)}</td>
                <td>
                  {locked ? (
                    nameOf(it.final_employee_id ?? it.recommended_employee_id)
                  ) : (
                    <>
                      <label className="sr-only" htmlFor={`sel-${it.proposal_item_id}`}>
                        Final selection for {wi(it.work_item_id)?.external_id}
                      </label>
                      <select
                        id={`sel-${it.proposal_item_id}`}
                        value={it.final_employee_id ?? it.recommended_employee_id}
                        disabled={cmd.pending}
                        onChange={(e) => void cmd.run((c, k) => c.editProposalItem(prop.delegation_proposal_id, it.work_item_id, e.target.value, { idempotency_key: k, expected_revision: prop.revision }))}
                      >
                        {candidates.map((c) => (
                          <option key={c.employee_id} value={c.employee_id}>
                            {c.first_name} {c.last_name}
                          </option>
                        ))}
                      </select>
                    </>
                  )}
                  {it.final_employee_id && it.final_employee_id !== it.recommended_employee_id && <span className="small muted"> (edited)</span>}
                </td>
                <td className="small">
                  {it.recommendation_reason}
                  <ul style={{ margin: "4px 0 0", paddingLeft: 16 }}>
                    {it.evidence.map((e) => (
                      <li key={e}>{e}</li>
                    ))}
                  </ul>
                  {it.uncertainty && <span className="muted">Uncertain: {it.uncertainty}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">Recommendations come from the seeded scenario, not a live recommendation engine. Only validated evidence and declared availability are considered; private learning history isn&apos;t.</p>
      {cmd.error && <ErrorNotice error={cmd.error} onRetry={cmd.error.code === "REVISION_CONFLICT" ? () => { cmd.clearError(); p.reload(); } : undefined} onDismiss={cmd.clearError} />}
      {!locked && (
        <div className="row">
          <button className="btn btn-primary" onClick={() => setConfirm(true)}>
            Review and confirm
          </button>
          <button className="btn" onClick={() => setReject(true)}>
            Reject proposal
          </button>
        </div>
      )}
      {prop.status === "CONFIRMED" && (
        <div className="notice notice-ok">
          <span className="notice-title">Assignments confirmed</span>
          <span>Assignees see the work in their Companion. Inbox notifications are informational only.</span>
        </div>
      )}
      <Dialog
        open={confirm}
        title="Confirm assignments"
        onClose={() => setConfirm(false)}
        footer={
          <>
            <button className="btn" onClick={() => setConfirm(false)}>
              Keep editing
            </button>
            <button
              className="btn btn-primary"
              disabled={cmd.pending}
              onClick={async () => {
                const r = await cmd.run((c, k) => c.confirmProposal(prop.delegation_proposal_id, { idempotency_key: k, expected_revision: prop.revision }));
                if (r) setConfirm(false);
              }}
            >
              {cmd.pending ? "Confirming…" : "Confirm assignments"}
            </button>
          </>
        }
      >
        <p>These assignments will be created together:</p>
        <ul>
          {prop.items.map((it) => (
            <li key={it.proposal_item_id}>
              {wi(it.work_item_id)?.external_id} → <b>{nameOf(it.final_employee_id ?? it.recommended_employee_id)}</b>
            </li>
          ))}
        </ul>
        <p className="small muted">The server rechecks membership, availability and current work before committing. If anything changed, you&apos;ll be asked to review again.</p>
        {cmd.error && <ErrorNotice error={cmd.error} />}
      </Dialog>
      <Dialog
        open={reject}
        title="Reject proposal"
        onClose={() => setReject(false)}
        dirty={reason.length > 0}
        footer={
          <button
            className="btn btn-danger"
            disabled={cmd.pending}
            onClick={async () => {
              const r = await cmd.run((c, k) => c.rejectProposal(prop.delegation_proposal_id, reason, { idempotency_key: k, expected_revision: prop.revision }));
              if (r) setReject(false);
            }}
          >
            Reject proposal
          </button>
        }
      >
        <div className="field">
          <label htmlFor="rej-reason">Reason</label>
          <textarea id="rej-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        {cmd.error && <ErrorNotice error={cmd.error} />}
      </Dialog>
    </div>
  );
}
