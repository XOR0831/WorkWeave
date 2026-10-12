"use client";

import { useState } from "react";
import { RequireSession } from "@/components/shell/AppShell";
import { SourceDrawer } from "@/components/chat";
import { Evidence, Loading, PageError, Status, humanize } from "@/components/ui";
import { useClient, useResource, useSession } from "@/lib/preview/client-context";
import type { Citation, TimelineEntry } from "@/types/contracts";

type Filter = "ALL" | "CURRENT" | "HISTORICAL" | "PENDING";

export default function MemoryPage() {
  return (
    <RequireSession>
      <Memory />
    </RequireSession>
  );
}

function Memory() {
  const { session } = useSession();
  const client = useClient();
  const tl = useResource((c) => c.getTimeline(), [session?.persona.employee_id]);
  const docs = useResource((c) => c.listDocumentVersions(), [session?.persona.employee_id]);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [cite, setCite] = useState<Citation | null>(null);
  if (tl.loading) return <Loading label="Loading knowledge" />;
  if (tl.error) return <PageError error={tl.error} onRetry={tl.reload} />;
  const entries = (tl.data ?? []).filter((e) => filter === "ALL" || e.temporal === filter);
  const open = async (e: TimelineEntry) => {
    const d = docs.data?.find((x) => x.document_version_id === e.document_version_id);
    if (!d) return;
    // The approved version's own text; the entry's summary only if it can't be loaded.
    const body = await client.getSourceContent(d.document_version_id).catch(() => null);
    setCite({ citation_id: e.entry_id, label: `${d.document_code} v${d.version}`, excerpt: { source_id: e.entry_id, document_version_id: d.document_version_id, heading_path: [d.title], text: body?.text ?? e.detail, evidence_type: e.evidence_type } });
  };
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Knowledge and history</h1>
          <p>Approved documents, superseded versions and work history, each labelled current, historical or pending. Private drafts and interviews never appear here.</p>
        </div>
      </div>
      <fieldset className="row" style={{ border: 0, padding: 0 }} data-tour="knowledge-filter">
        <legend className="sr-only">Show</legend>
        {(["ALL", "CURRENT", "HISTORICAL", "PENDING"] as Filter[]).map((f) => (
          <label key={f} className="choice" style={{ marginRight: 12 }}>
            <input type="radio" name="tl-filter" checked={filter === f} onChange={() => setFilter(f)} /> {f === "ALL" ? "Everything" : humanize(f)}
          </label>
        ))}
      </fieldset>
      <ol className="list">
        {entries.map((e) => (
          <li key={e.entry_id} className={`list-item stitched stitched-${e.evidence_type.toLowerCase()}`}>
            <div className="row-between">
              <b>{e.label}</b>
              <span className="row">
                <Status value={e.temporal === "PENDING" ? "PENDING" : e.temporal} label={e.temporal === "PENDING" ? "Index pending" : humanize(e.temporal)} />
                <Evidence type={e.evidence_type} />
              </span>
            </div>
            <span className="small">{e.detail}</span>
            <span className="small muted">{humanize(e.kind)}</span>
            {e.document_version_id && (
              <div>
                <button className="btn btn-small" onClick={() => void open(e)}>
                  View source
                </button>
              </div>
            )}
          </li>
        ))}
        {entries.length === 0 && <li className="muted">Nothing matches this filter.</li>}
      </ol>
      <SourceDrawer citation={cite} onClose={() => setCite(null)} />
    </div>
  );
}
