/**
 * API mode (docs/32): what the knowledge-transfer assistant reconstructed from the records, and a
 * private conversation with it. Everything here is a proposal: knowledge-at-risk is computed by rules
 * (each factor shows its records), ownership is "confirmed" only from a responsibility record, and
 * nothing approves, transfers or completes anything.
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { ChatErrorNote, ExamplePrompts, ChatHeader, Transcript } from "@/components/chat";
import { ktExamples } from "@/features/chat/examples";
import { ChatVoiceComposer, KT_VOICE, ListenButton, ReadAloudControls, useChatVoice } from "@/features/voice/ChatVoice";
import { Evidence, Status, humanize } from "@/components/ui";
import { newKey, useClient, useCommand } from "@/lib/preview/client-context";
import type { ExitKtCase, KtCitation, KtDiscovery, KtRiskFactor } from "@/types/contracts";

const FACTOR: Record<KtRiskFactor["factor"], string> = {
  SOLE_OWNER: "Sole owner",
  MISSING_DOCUMENTATION: "Missing or outdated documentation",
  NO_SUCCESSOR: "No successor",
  OPEN_WORK: "Open work",
  RECENT_CHANGE: "Recent change",
  HIGH_CASE_FREQUENCY: "Many related cases",
};

function Sources({ cites }: { cites: KtCitation[] }) {
  if (!cites.length) return null;
  return <span className="small muted"> · {cites.map((c) => c.label).filter(Boolean).slice(0, 3).join(" · ")}</span>;
}

export function riskWhy(factors: KtRiskFactor[] | undefined): string {
  const on = (factors ?? []).filter((f) => f.established).map((f) => FACTOR[f.factor].toLowerCase());
  return on.length ? on.join(", ") : "no risk factor established";
}

export function DiscoveryPanel({ d }: { d: KtDiscovery }) {
  return (
    <section className="panel stack-s" aria-labelledby="h-discovery">
      <div className="row-between">
        <h3 id="h-discovery">What the records show</h3>
        <span className="small muted">Reconstructed {new Date(d.discovered_at).toLocaleString("en", { dateStyle: "medium", timeStyle: "short" })} · verify and correct</span>
      </div>
      <p className="small">{d.overview}</p>

      <h4 className="small">Knowledge at risk</h4>
      <p className="small muted">Scored by fixed rules, not by the AI. A factor counts only when a record shows it.</p>
      <ul className="list">
        {d.risks.map((r) => (
          <li key={`${r.area_type}-${r.area_id}`} className="list-item">
            <div className="row-between">
              <b>{r.title}</b>
              <Status value={r.level === "HIGH" ? "FAILED" : r.level === "MEDIUM" ? "PENDING" : "COMPLETED"} label={`${humanize(r.level)} risk · ${r.score}`} />
            </div>
            <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
              {r.factors.filter((f) => f.established).map((f) => (
                <li key={f.factor}>
                  {FACTOR[f.factor]} (+{f.weight}): {f.note}
                  <Sources cites={f.sources} />
                </li>
              ))}
            </ul>
            {r.factors.some((f) => !f.established) && (
              <span className="small muted">Not established: {r.factors.filter((f) => !f.established).map((f) => FACTOR[f.factor].toLowerCase()).join(", ")}</span>
            )}
          </li>
        ))}
      </ul>

      {d.responsibilities.length > 0 && (
        <>
          <h4 className="small">Responsibilities</h4>
          <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
            {d.responsibilities.map((r) => (
              <li key={r.title}>
                <b>{r.title}</b> <Status value={r.ownership === "CONFIRMED" ? "COMPLETED" : "PENDING"} label={r.ownership === "CONFIRMED" ? "Owner on record" : "Inferred from work"} /> {r.note}
                <Sources cites={r.citations} />
              </li>
            ))}
          </ul>
        </>
      )}
      {d.expertise.length > 0 && (
        <>
          <h4 className="small">Historical cases</h4>
          <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
            {d.expertise.map((x) => (
              <li key={x.text}>
                {x.text} <Evidence type={x.evidence_type} />
                <Sources cites={x.citations} />
              </li>
            ))}
          </ul>
        </>
      )}
      {d.changes.length > 0 && (
        <>
          <h4 className="small">Changes over time</h4>
          <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
            {d.changes.map((x) => (
              <li key={x.text}>
                {x.text}
                <Sources cites={x.citations} />
              </li>
            ))}
          </ul>
        </>
      )}
      {d.documents.length > 0 && (
        <p className="small">
          <b>Documents:</b> {d.documents.map((x) => `${x.label} (${x.temporal_status === "CURRENT" ? "current" : "history, not current instructions"})`).join("; ")}
        </p>
      )}
      {d.open_work.length > 0 && (
        <p className="small">
          <b>Still open:</b> {d.open_work.map((x) => `${x.label} (${humanize(x.status)})`).join("; ")}. Completing knowledge transfer doesn&apos;t close or reassign these.
        </p>
      )}
      {d.unknowns.length > 0 && <p className="small muted">Not in the records: {d.unknowns.join("; ")}</p>}
    </section>
  );
}

/** The person's own conversation with the knowledge-transfer assistant (employee, manager or successor).
 * Like the Companion, it speaks first: an empty conversation asks once for an opening brief. */
export function KtCopilot({ c }: { c: ExitKtCase }) {
  const cmd = useCommand();
  // Voice (ADR-045): tap-to-talk, and new answers read aloud when switched on.
  const cv = useChatVoice({ channel: KT_VOICE, conversationId: c.exit_kt_case_id, messages: c.copilot, enabled: c.kt_available });
  const send = async (text: string, input_kind: "TEXT" | "VOICE_TRANSCRIPT") => Boolean(await cmd.run((cl, k) => cl.askKtCopilot({ idempotency_key: k, client_turn_id: newKey("turn"), text, input_kind })));
  const empty = !(c.copilot ?? []).some((m) => m.sender !== "SYSTEM");
  const client = useClient();
  const asked = useRef<string | null>(null);
  const [briefing, setBriefing] = useState(false);
  useEffect(() => {
    // Once per case and page load; the brief is saved, so later visits show the conversation instead.
    // It's the assistant speaking first, not the person's command: if the assistant is still busy (e.g. a
    // brief started before a reload), it waits and tries again quietly instead of showing an error.
    if (!c.kt_available || !empty || asked.current === c.exit_kt_case_id) return;
    asked.current = c.exit_kt_case_id;
    let alive = true;
    const attempt = async (left: number) => {
      setBriefing(true);
      try {
        await client.askKtCopilot({ idempotency_key: newKey("kt-brief"), client_turn_id: newKey("turn"), text: "", input_kind: "TEXT" });
      } catch {
        if (alive && left > 0) {
          setTimeout(() => void attempt(left - 1), 5000);
          return;
        }
      }
      if (alive) setBriefing(false);
    };
    void attempt(3);
    return () => {
      alive = false;
    };
  }, [c.kt_available, empty, c.exit_kt_case_id, client]);
  return (
    <section className="chat chat-tall" aria-label="Knowledge-transfer assistant">
      <ChatHeader
        title="WorkWeave"
        subtitle={c.kt_available ? "Answers from this case's records · private to you" : "Assistant not connected · the case comes from the database"}
        action={
          <span className="small muted" role="status" aria-live="polite">
            {briefing && empty ? "Preparing your brief…" : cmd.pending ? "Thinking…" : ""}
          </span>
        }
      />
      <Transcript label="Knowledge-transfer assistant" messages={(c.copilot ?? []).map((m) => ({ id: m.message_id, sender: m.sender, text: m.text, provenance: m.provenance, citations: m.citations, meta: <ListenButton cv={cv} m={m} /> }))} />
      {cmd.error && (
        <div style={{ padding: "0 14px" }}>
          <ChatErrorNote error={cmd.error} onDismiss={cmd.clearError} />
        </div>
      )}
      {c.kt_available && <ExamplePrompts examples={ktExamples({ responsibility: c.responsibilities[0]?.title })} disabled={cmd.pending} onPick={(text) => void send(text, "TEXT")} />}
      {c.kt_available && <ReadAloudControls cv={cv} />}
      <ChatVoiceComposer cv={cv} label="Ask about this case" onSend={send} pending={cmd.pending} disabled={!c.kt_available} placeholder="What's most at risk? What still needs capturing?" />
    </section>
  );
}
