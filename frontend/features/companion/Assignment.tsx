"use client";

import { useState } from "react";
import { ErrorNotice, Loading, Status } from "@/components/ui";
import { useCommand, useResource, useSession } from "@/lib/preview/client-context";
import type { WorkItem } from "@/types/contracts";

/**
 * Who has this ticket and why (ADR-035), inside the ticket's details (API mode).
 * - "Why this person?" for the assignee and the lead of the shift in progress: the competency facts
 *   saved when it was assigned; the lead also sees how the members on the shift compared.
 * - The lead can assign an unassigned ticket, or override who has it, choosing someone on the shift
 *   (the lead included).
 */
export function AssignmentPanel({ item, isLead }: { item: WorkItem; isLead: boolean }) {
  const { session } = useSession();
  const mine = item.assignee_id === session?.persona.employee_id;
  const [why, setWhy] = useState(false);
  const [changing, setChanging] = useState(false);
  const open = !["COMPLETED", "CLOSED", "CANCELLED"].includes(item.status);
  if (!mine && !isLead) return item.assignment_source === "AUTOMATIC" ? <span className="fixture-tag">Assigned automatically by competency</span> : null;
  return (
    <section className="stack-s" aria-label="Assignment">
      <div className="row">
        {item.assignment_source === "AUTOMATIC" && <span className="fixture-tag">Assigned automatically by competency</span>}
        {item.assignee_id && (
          <button className="btn btn-small" aria-expanded={why} onClick={() => setWhy(!why)}>
            {why ? "Hide why" : "Why this person?"}
          </button>
        )}
        {isLead && open && (
          <button className="btn btn-small" aria-expanded={changing} onClick={() => setChanging(!changing)}>
            {item.assignee_id ? "Change assignee" : "Assign"}
          </button>
        )}
      </div>
      {why && <Why id={item.work_item_id} />}
      {changing && <Reassign item={item} onDone={() => setChanging(false)} />}
    </section>
  );
}

function Why({ id }: { id: string }) {
  const x = useResource((c) => c.getAssignmentExplanation(id), [id]);
  if (x.loading) return <Loading />;
  if (x.error) return <ErrorNotice error={x.error} onRetry={x.reload} />;
  const d = x.data!;
  return (
    <div className="stitched stack-s" data-testid="assignment-why">
      <p className="small" style={{ margin: 0 }}>{d.summary}</p>
      {d.requirements && d.requirements.length > 0 && (
        <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
          {d.requirements.map((r) => (
            <li key={r.name}>
              <b>{r.name}</b>
              {r.required_level ? ` (level ${r.required_level})` : ""}: {r.met ? "validated evidence" : "no validated evidence yet"}
            </li>
          ))}
        </ul>
      )}
      {d.compared && d.compared.length > 1 && (
        <div className="table-wrap" role="region" tabIndex={0} aria-label="How the members on the shift compared">
          <table className="rich-table">
            <caption className="small muted" style={{ textAlign: "left" }}>How the members on the shift compared when it was assigned</caption>
            <thead>
              <tr>
                <th scope="col">Member</th>
                <th scope="col">Competency gaps</th>
                <th scope="col">Open tickets</th>
                <th scope="col">Availability</th>
              </tr>
            </thead>
            <tbody>
              {d.compared.map((c) => (
                <tr key={c.name}>
                  <td>{c.name}</td>
                  <td>{c.gaps}</td>
                  <td>{c.open_work}</td>
                  <td>{c.availability.toLowerCase()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Reassign({ item, onDone }: { item: WorkItem; onDone: () => void }) {
  const { session } = useSession();
  const cands = useResource((c) => c.getAssignmentCandidates(item.work_item_id), [item.work_item_id]);
  const cmd = useCommand();
  const [who, setWho] = useState("");
  if (cands.loading) return <Loading />;
  if (cands.error) return <ErrorNotice error={cands.error} onRetry={cands.reload} />;
  const list = (cands.data ?? []).filter((c) => c.employee_id !== item.assignee_id);
  if (list.length === 0) return <p className="small muted">No one else on your shift can take it right now.</p>;
  return (
    <div className="stack-s">
      <label className="small stack-s">
        Give it to someone on your shift
        <select value={who} onChange={(e) => setWho(e.target.value)}>
          <option value="">Choose a member…</option>
          {list.map((c) => (
            <option key={c.employee_id} value={c.employee_id}>
              {c.name}
              {c.employee_id === session?.persona.employee_id ? " (you)" : ""} · {c.gaps.length ? `no validated evidence for ${c.gaps.join(", ")}` : "meets the competency requirements"} · {c.open_work} open
              {c.availability === "UNAVAILABLE" ? " · unavailable now" : ""}
            </option>
          ))}
        </select>
      </label>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      <div className="row">
        <button
          className="btn btn-small btn-primary"
          disabled={!who || cmd.pending}
          onClick={async () => {
            const r = await cmd.run((c, k) => c.reassignWorkItem(item.work_item_id, who, { idempotency_key: k, expected_revision: item.revision }));
            if (r) onDone();
          }}
        >
          {item.assignee_id ? "Change assignee" : "Assign"}
        </button>
        <button className="btn btn-small" onClick={onDone}>
          Cancel
        </button>
        {item.assignee_id && <Status value="PENDING" label="The current assignee is notified" />}
      </div>
    </div>
  );
}
