"use client";

import { useState } from "react";
import { Dialog, ErrorNotice, Evidence, OriginTag, Status } from "@/components/ui";
import { useCommand, useRuntime, useSession } from "@/lib/preview/client-context";
import { transferBlockers } from "@/lib/domain/rules";
import type { ExitKtCase, ResponsibilityTransfer } from "@/types/contracts";

export function ResponsibilityArea({ c, role }: { c: ExitKtCase; role: "SUBJECT" | "REVIEWER" }) {
  const cmd = useCommand();
  const { nameOf, personas, session } = useSession();
  const [confirm, setConfirm] = useState<ResponsibilityTransfer | null>(null);
  const [comment, setComment] = useState("");
  const isManager = session?.persona.grants.includes("responsibility.confirm");
  const isReviewer = session?.persona.grants.includes("knowledge.review") && c.employee_id !== session.persona.employee_id;
  const pkg = c.package;
  const api = useRuntime().mode === "http";
  const ver = (k: string) => ({ idempotency_key: k, expected_revision: c.revision });
  const latest = pkg.versions.find((v) => v.package_version_id === pkg.current_approved_version_id);
  const candidates = personas.filter((p) => p.employee_id !== c.employee_id && p.grants.includes("work.report"));

  return (
    <div className="stack">
      <p className="muted small" style={{ maxWidth: "70ch" }}>
        Responsibilities stay with {nameOf(c.employee_id)} until a manager confirms each transfer. That needs the successor&apos;s receipt of the current approved package, the effective time, and an unchanged owner.
      </p>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      {api && isManager && (
        <div className="panel stack-s">
          <div className="row">
            <label className="small" htmlFor="kt-successor">
              Successor for the package
            </label>
            <select id="kt-successor" style={{ width: "auto" }} value={pkg.successor_employee_id || ""} disabled={cmd.pending}
              onChange={(e) => e.target.value && void cmd.run((cl, k) => cl.assignSuccessor(e.target.value, ver(k)))}>
              <option value="">Choose a successor</option>
              {personas.filter((p) => p.employee_id !== c.employee_id).map((p) => (
                <option key={p.employee_id} value={p.employee_id}>
                  {p.first_name} {p.last_name}
                </option>
              ))}
            </select>
            {c.kt_available && (
              <button className="btn btn-small" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.recommendSuccessors({ idempotency_key: k }))}>
                {cmd.pending ? "Working…" : "Recommend successors"}
              </button>
            )}
          </div>
          <span className="small muted">Recommendations come from related work, validated competency evidence, workload and availability. You confirm each transfer separately; nothing changes owner by itself.</span>
        </div>
      )}
      <section className="stack-s" aria-labelledby="h-resp">
        <h3 id="h-resp">Responsibilities</h3>
        {c.transfers.map((t) => {
          const r = c.responsibilities.find((x) => x.responsibility_id === t.responsibility_id)!;
          const blockers = transferBlockers(c, t.transfer_id);
          return (
            <div key={t.transfer_id} className="list-item">
              <div className="row-between">
                <b>{r.title}</b>
                <Status value={t.status} />
              </div>
              <dl className="kv small">
                <dt>Current owner</dt>
                <dd>
                  {nameOf(r.owner_employee_id)} (ownership revision {r.ownership_revision})
                </dd>
                <dt>Recommended</dt>
                <dd className="row">
                  {t.recommended_owner_employee_id ? nameOf(t.recommended_owner_employee_id) : "No successor proposed"} <OriginTag origin={t.origin} />
                </dd>
                <dt>Final selection</dt>
                <dd>
                  {isManager && t.status !== "TRANSFERRED" ? (
                    <>
                      <label className="sr-only" htmlFor={`fo-${t.transfer_id}`}>
                        Final successor for {r.title}
                      </label>
                      <select
                        id={`fo-${t.transfer_id}`}
                        style={{ width: "auto" }}
                        value={t.final_owner_employee_id ?? t.recommended_owner_employee_id ?? ""}
                        disabled={cmd.pending}
                        onChange={(e) => void cmd.run((cl, k) => cl.editTransfer(t.transfer_id, e.target.value, ver(k)))}
                      >
                        <option value="" disabled>
                          Choose a successor
                        </option>
                        {candidates.map((p) => (
                          <option key={p.employee_id} value={p.employee_id}>
                            {p.first_name} {p.last_name}
                          </option>
                        ))}
                      </select>
                    </>
                  ) : (
                    nameOf(t.final_owner_employee_id ?? t.recommended_owner_employee_id)
                  )}
                </dd>
                <dt>Effective</dt>
                <dd className="row">
                  {t.effective_label}
                  {isManager && !t.effective_reached && t.status !== "TRANSFERRED" && (
                    <button className="btn btn-small" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.reviewEffectiveTime(t.transfer_id, ver(k)))}>
                      Review and set to now
                    </button>
                  )}
                </dd>
                {t.recommendation_reason && (
                  <>
                    <dt>Reason</dt>
                    <dd>{t.recommendation_reason}</dd>
                  </>
                )}
              </dl>
              {t.status !== "TRANSFERRED" && (
                <div className="stack-s">
                  {blockers.length > 0 ? (
                    <ul className="small" style={{ margin: 0, paddingLeft: 18 }} aria-label="Why ownership can't transfer yet">
                      {blockers.map((b) => (
                        <li key={b}>{b}</li>
                      ))}
                    </ul>
                  ) : (
                    <span className="small">All transfer conditions are met.</span>
                  )}
                  {isManager && (
                    <div>
                      <button className="btn btn-small btn-primary" onClick={() => setConfirm(t)}>
                        Review transfer
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </section>

      <section className="stack-s" aria-labelledby="h-pkg">
        <div className="row-between">
          <h3 id="h-pkg">Successor package for {nameOf(pkg.successor_employee_id)}</h3>
          <Status value={pkg.status} />
        </div>
        {pkg.review_comment && pkg.status === "REJECTED" && (
          <div className="notice notice-warn">
            <span>Reviewer feedback: {pkg.review_comment}</span>
          </div>
        )}
        <div className="list">
          {pkg.draft_sections.map((s) => (
            <div key={s.title} className={`list-item ${s.evidence_type ? `stitched stitched-${s.evidence_type.toLowerCase()}` : ""}`}>
              <span className="row">
                <b>{s.title}</b> {s.evidence_type && <Evidence type={s.evidence_type} />}
              </span>
              <span className="small">{s.content}</span>
            </div>
          ))}
        </div>
        <p className="small muted">Only approved knowledge is included. Private interviews and pending drafts are excluded.</p>
        <div className="row">
          {role === "SUBJECT" && (pkg.status === "DRAFT" || pkg.status === "REJECTED" || pkg.status === "APPROVED") && (
            <button className="btn" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.assemblePackage(ver(k)))}>
              Assemble from approved knowledge
            </button>
          )}
          {role === "SUBJECT" && (pkg.status === "DRAFT" || pkg.status === "REJECTED") && (
            <button className="btn btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.submitPackage(ver(k)))}>
              Submit package for review
            </button>
          )}
        </div>
        {isReviewer && pkg.status === "SUBMITTED" && (
          <fieldset>
            <legend>Your decision on revision {pkg.revision}</legend>
            <div className="field">
              <label htmlFor="pkg-comment">Comment</label>
              <textarea id="pkg-comment" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Required to reject" />
            </div>
            <div className="row">
              <button className="btn btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.decidePackage("APPROVE", comment, ver(k)))}>
                Approve package
              </button>
              <button className="btn btn-danger" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.decidePackage("REJECT", comment, ver(k)))}>
                Reject package
              </button>
            </div>
          </fieldset>
        )}
        {latest && (
          <p className="small">
            Approved version {pkg.versions.length} (by {nameOf(latest.approved_by)}).{" "}
            {pkg.receipts.some((r) => r.package_version_id === latest.package_version_id) ? `${nameOf(pkg.successor_employee_id)} confirmed receipt.` : `Waiting for ${nameOf(pkg.successor_employee_id)} to confirm receipt.`}
          </p>
        )}
      </section>

      <Dialog
        open={Boolean(confirm)}
        title="Confirm responsibility transfer"
        onClose={() => setConfirm(null)}
        footer={
          confirm && (
            <button
              className="btn btn-primary"
              disabled={cmd.pending || transferBlockers(c, confirm.transfer_id).length > 0}
              onClick={async () => {
                const r = await cmd.run((cl, k) => cl.confirmTransfer(confirm.transfer_id, ver(k)));
                if (r) setConfirm(null);
              }}
            >
              {cmd.pending ? "Transferring…" : "Confirm transfer"}
            </button>
          )
        }
      >
        {confirm && (
          <>
            {(() => {
              const r = c.responsibilities.find((x) => x.responsibility_id === confirm.responsibility_id)!;
              const to = confirm.final_owner_employee_id ?? confirm.recommended_owner_employee_id;
              const blockers = transferBlockers(c, confirm.transfer_id);
              return (
                <>
                  <dl className="kv">
                    <dt>Responsibility</dt>
                    <dd>{r.title}</dd>
                    <dt>From</dt>
                    <dd>{nameOf(r.owner_employee_id)}</dd>
                    <dt>To</dt>
                    <dd>{to ? nameOf(to) : "Not selected"}</dd>
                    <dt>Owner revision</dt>
                    <dd>
                      Expected {confirm.expected_owner_revision}, current {r.ownership_revision}
                    </dd>
                    <dt>Package receipt</dt>
                    <dd>{pkg.receipts.some((x) => x.package_version_id === pkg.current_approved_version_id && x.employee_id === to) ? "Current approved version received" : "Not received"}</dd>
                    <dt>Effective</dt>
                    <dd>{confirm.effective_label}</dd>
                  </dl>
                  {blockers.length > 0 ? (
                    <ErrorNotice error={{ code: "GUARD_FAILED", message: `Ownership stays unchanged: ${blockers.join("; ")}.`, retryable: false }} />
                  ) : (
                    <p className="small">This changes ownership of this responsibility only. Individual work items and open knowledge gaps stay as they are.</p>
                  )}
                </>
              );
            })()}
            {cmd.error && <ErrorNotice error={cmd.error} />}
          </>
        )}
      </Dialog>
    </div>
  );
}
