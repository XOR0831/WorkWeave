"use client";

import Link from "next/link";
import { useState } from "react";
import { RequireSession } from "@/components/shell/AppShell";
import { ErrorNotice, Loading, PageError, PageHeader, StateView, Status, humanize } from "@/components/ui";
import { useCommand, useResource, useRuntime, useSession } from "@/lib/preview/client-context";
import { useSearch } from "@/lib/preview/use-search";
import { useOnChange } from "@/lib/preview/use-on-change";
import { ReportChip } from "@/features/companion/canvases";
import type { TicketSystemItem } from "@/types/contracts";

/**
 * The company's ticket tool, simulated for the demo (ADR-033). A ticket's status here is its real
 * status; WorkWeave matches it with what people report in the Work Companion. Nobody validates.
 */
export default function TicketSystemPage() {
  return (
    <RequireSession>
      <TicketSystem />
    </RequireSession>
  );
}

type ToolStatus = "IN_PROGRESS" | "BLOCKED" | "COMPLETED" | "CANCELLED";
const CLOSED = ["COMPLETED", "CLOSED", "CANCELLED"];

/** The changes the ticket's assignee can make from its current status. */
function nextSteps(status: string): { to: ToolStatus; label: string; primary?: boolean }[] {
  if (CLOSED.includes(status)) return [{ to: "IN_PROGRESS", label: "Reopen" }];
  return [
    ...(status !== "IN_PROGRESS" ? [{ to: "IN_PROGRESS" as const, label: status === "BLOCKED" ? "Unblock" : "Start work" }] : []),
    ...(status !== "BLOCKED" ? [{ to: "BLOCKED" as const, label: "Mark blocked" }] : []),
    { to: "COMPLETED", label: "Resolve", primary: true },
    { to: "CANCELLED", label: "Cancel ticket" },
  ];
}

function TicketSystem() {
  const { session, nameOf } = useSession();
  const api = useRuntime().mode === "http";
  const search = useSearch();
  const view = useResource((c) => c.getTicketSystem(), [session?.persona.employee_id]);
  const [selected, setSelected] = useState<string | null>(null);
  useOnChange(search?.get("item") ?? null, () => setSelected(search?.get("item") ?? null));

  if (!api)
    return (
      <StateView title="Ticket system not available in this preview" action={<Link className="btn btn-primary" href="/companion/">Back to Work Companion</Link>}>
        The simulated ticket system runs with the WorkWeave backend.
      </StateView>
    );
  if (view.loading || search === null) return <Loading label="Opening the ticket system" />;
  if (view.error) return <PageError error={view.error} onRetry={view.reload} />;
  const v = view.data!;
  const t = session!.scenario.terminology;
  const current = v.items.find((i) => i.work_item_id === selected) ?? v.items[0];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Simulated external tool"
        title={v.system_name}
        purpose={`Stands in for ${session!.scenario.company_name}'s real ${t.workItem} tool. A ${t.workItem}'s status here is its real status; WorkWeave matches it with what people report in the Work Companion.`}
        actions={
          <Link className="btn btn-small" href="/companion/">
            Back to Work Companion
          </Link>
        }
      />
      <div className="tool-band" role="note">
        Simulated for the demo. Changes apply only to your demo copy.
      </div>
      <div className="split tool-split">
        <section className="panel" aria-labelledby="h-queue">
          <h2 id="h-queue">Your team&apos;s {t.workItems}</h2>
          {v.items.length === 0 ? (
            <p className="muted">No {t.workItems} yet.</p>
          ) : (
            <div className="table-wrap" role="region" tabIndex={0} aria-label={`${t.workItems} (scrolls horizontally)`}>
              <table>
                <caption className="sr-only">{t.workItems}</caption>
                <thead>
                  <tr>
                    <th scope="col">ID</th>
                    <th scope="col">Title</th>
                    <th scope="col">Status</th>
                    <th scope="col">Assignee</th>
                    <th scope="col">Due</th>
                  </tr>
                </thead>
                <tbody>
                  {v.items.map((i) => (
                    <tr key={i.work_item_id} aria-current={i.work_item_id === current?.work_item_id ? "true" : undefined}>
                      <th scope="row">
                        <button className="link-btn mono-id" onClick={() => setSelected(i.work_item_id)} aria-label={`Open ${i.external_id}`}>
                          {i.external_id}
                        </button>
                      </th>
                      <td>{i.title}</td>
                      <td>
                        <Status value={i.status} />
                      </td>
                      <td>{i.assignee_id ? nameOf(i.assignee_id) : <span className="muted">Unassigned</span>}</td>
                      <td className="small">{i.due_label || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <aside className="split-aside" aria-label="Selected item">
          {current && <TicketDetail key={current.work_item_id} item={current} />}
        </aside>
      </div>
    </div>
  );
}

function TicketDetail({ item }: { item: TicketSystemItem }) {
  const { nameOf, session } = useSession();
  const cmd = useCommand();
  const [note, setNote] = useState("");
  const change = async (to: ToolStatus) => {
    const r = await cmd.run((c, k) => c.updateTicketStatus(item.work_item_id, to, note, { idempotency_key: k, expected_revision: item.revision }));
    if (r) setNote("");
  };
  const t = session!.scenario.terminology;
  return (
    <section className="panel stack-s" aria-labelledby="h-ticket" data-tour="ticket-detail">
      <div className="row-between">
        <h2 id="h-ticket">
          <span className="mono-id">{item.external_id}</span> {item.title}
        </h2>
        <Status value={item.status} />
      </div>
      <p className="small">{item.description}</p>
      <dl className="kv">
        <dt>Priority</dt>
        <dd>{humanize(item.priority)}</dd>
        <dt>Assignee</dt>
        <dd>{item.assignee_id ? nameOf(item.assignee_id) : "Unassigned"}</dd>
        {item.due_label && (
          <>
            <dt>Due</dt>
            <dd>{item.due_label}</dd>
          </>
        )}
        {item.report && item.report.sync_status !== "SUPERSEDED" && (
          <>
            <dt>In WorkWeave</dt>
            <dd>
              <ReportChip report={item.report} />
              {item.report.sync_status === "MATCHED" && <span className="small">Matches what {nameOf(item.report.employee_id)} reported.</span>}
            </dd>
          </>
        )}
      </dl>
      {item.can_update ? (
        <div className="stack-s">
          <div className="field">
            <label htmlFor="tool-note">Work note (optional)</label>
            <textarea id="tool-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What changed" />
          </div>
          <div className="row">
            {nextSteps(item.status).map((s) => (
              <button key={s.to} className={`btn btn-small${s.primary ? " btn-primary" : ""}`} disabled={cmd.pending} onClick={() => void change(s.to)}>
                {s.label}
              </button>
            ))}
          </div>
          {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
        </div>
      ) : (
        <p className="small muted">
          {item.assignee_id ? `Only ${nameOf(item.assignee_id)}, the assignee, can change this ${t.workItem}.` : `Unassigned. Your shift lead assigns ${t.workItems} in the Work Companion.`}
        </p>
      )}
      <section className="stack-s">
        <h3>History in the ticket system</h3>
        {item.history.length === 0 && <p className="small muted">No changes yet.</p>}
        <ul className="list">
          {item.history.map((h) => (
            <li key={h.work_event_id} className="list-item">
              <div className="row-between">
                <span className="small">
                  {h.from_status && h.to_status ? (
                    <>
                      {humanize(h.from_status)} → <b>{humanize(h.to_status)}</b>
                    </>
                  ) : (
                    <b>{humanize(h.event_type)}</b>
                  )}
                </span>
                <span className="small muted">
                  {nameOf(h.employee_id)}, {h.observed_label}
                </span>
              </div>
              {h.note && <span className="small">{h.note}</span>}
            </li>
          ))}
        </ul>
      </section>
    </section>
  );
}
