/**
 * A short checklist of the steps in a guidance reply, for the work area (the full reply stays in the
 * conversation). Deterministic formatting only: it keeps the reply's own list items, shortened to
 * their bold lead ("**Claim:** …") or first sentence. It adds nothing the reply didn't say, and a
 * reply without a list gives no checklist.
 */
export interface StepSummary {
  label: string;
  detail: string;
}

const ITEM = /^\s*(?:\d+[.)]|[-*•])\s+(.*)$/;
const LEAD = /^\*\*(.+?)\*\*\s*[:\-–—]?\s*(.*)$/;
const MAX_DETAIL = 140;

function plain(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, "$1").replace(/\*(\S(?:.*?\S)?)\*/g, "$1").trim();
}

function firstSentence(text: string): string {
  const t = plain(text);
  const end = t.search(/[.!?](\s|$)/);
  const s = end >= 0 ? t.slice(0, end + 1) : t;
  return s.length > MAX_DETAIL ? `${s.slice(0, MAX_DETAIL - 1).trimEnd()}…` : s;
}

export function summarizeSteps(text: string): StepSummary[] {
  // Inline bullets (" * **A:** … * **B:** …") are split into lines first.
  const lines = text.replace(/\r\n/g, "\n").replace(/\s\*\s(?=\*\*)/g, "\n* ").split("\n");
  const out: StepSummary[] = [];
  for (const line of lines) {
    const m = ITEM.exec(line);
    if (!m) continue;
    const body = m[1]!.trim();
    const lead = LEAD.exec(body);
    if (lead) out.push({ label: plain(lead[1]!).replace(/:$/, ""), detail: firstSentence(lead[2]!) });
    else out.push({ label: firstSentence(body), detail: "" });
  }
  return out.filter((s) => s.label);
}
