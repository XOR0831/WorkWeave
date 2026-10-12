"use client";

import Link from "next/link";
import { useState } from "react";
import { RequireSession } from "@/components/shell/AppShell";
import { ErrorNotice, Loading, PageError, StateView, Status, humanize } from "@/components/ui";
import { useCommand, useResource, useSession } from "@/lib/preview/client-context";

export default function ReviewsPage() {
  return (
    <RequireSession>
      <Reviews />
    </RequireSession>
  );
}

function Reviews() {
  const { session } = useSession();
  const q = useResource((c) => c.listReviews(), [session?.persona.employee_id]);
  const cmd = useCommand();
  const [comments, setComments] = useState<Record<string, string>>({});
  if (q.loading) return <Loading label="Loading review queue" />;
  if (q.error) return <PageError error={q.error} onRetry={q.reload} />;
  const items = q.data ?? [];
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Reviewer workspace</h1>
          <p>Submitted knowledge notes, KT artifacts and successor packages. Each decision binds the exact submitted revision. Shift handovers aren&apos;t reviewed here; shift leads publish them directly.</p>
        </div>
      </div>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      {items.length === 0 ? (
        <StateView title="Nothing is waiting for review">New submissions appear here and in your inbox.</StateView>
      ) : (
        <ul className="list">
          {items.map((r) => (
            <li key={r.review_id} className="list-item">
              <div className="row-between">
                <b>{r.title}</b>
                <span className="row">
                  <Status value="PENDING_REVIEW" label={humanize(r.kind)} />
                  <span className="small muted">{r.revision_label}</span>
                </span>
              </div>
              <span className="small muted">
                Submitted by {r.submitted_by}. Requested audience: {r.audience.toLowerCase()}.
              </span>
              <div className="excerpt" style={{ whiteSpace: "pre-wrap" }}>
                {r.content}
              </div>
              {r.kind === "MEMORY_DRAFT" ? (
                <div className="stack-s">
                  <div className="field">
                    <label htmlFor={`c-${r.review_id}`}>Comment</label>
                    <textarea id={`c-${r.review_id}`} value={comments[r.review_id] ?? ""} onChange={(e) => setComments({ ...comments, [r.review_id]: e.target.value })} placeholder="Required to reject" />
                  </div>
                  <p className="small muted">Approving keeps the note labelled as a reported observation. It doesn&apos;t make it verified, complete work, or change an SOP.</p>
                  <div className="row">
                    <button className="btn btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((c, k) => c.decideMemoryDraft(r.resource_id, "APPROVE", comments[r.review_id] ?? "", { idempotency_key: k }))}>
                      Approve note
                    </button>
                    <button className="btn btn-danger" disabled={cmd.pending} onClick={() => void cmd.run((c, k) => c.decideMemoryDraft(r.resource_id, "REJECT", comments[r.review_id] ?? "", { idempotency_key: k }))}>
                      Reject note
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <Link className="btn btn-small btn-primary" href={r.href}>
                    Review in Exit KT
                  </Link>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
