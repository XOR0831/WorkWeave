"use client";

import { RichText } from "@/lib/text/RichText";
import { useResource } from "@/lib/preview/client-context";
import { Status } from "@/components/ui";
import type { Citation } from "@/types/contracts";

/**
 * "Reference for this explanation": one excerpt reused from the tutor message's own citations
 * (no second retrieval). Pinning an older citation never moves curriculum position.
 * Revoked sources fail closed: the cached excerpt is not shown.
 */
export function ReferencePanel({
  citation,
  pinned,
  onReturn,
  onOpen,
  bare = false,
}: {
  citation: Citation | null;
  pinned: boolean;
  onReturn: () => void;
  onOpen: (c: Citation) => void;
  /** Inside the mobile bottom sheet: the sheet supplies the heading and frame. */
  bare?: boolean;
}) {
  const dv = citation?.excerpt.document_version_id ?? "";
  const src = useResource((c) => (dv ? c.getSourceContent(dv) : Promise.resolve(null)), [dv]);
  return (
    <section className={bare ? "stack-s" : "panel stack-s"} aria-labelledby={bare ? undefined : "h-ref"} aria-label={bare ? "Reference" : undefined}>
      {!bare && <p className="eyebrow">Grounded in your material</p>}
      <div className="row-between">
        {!bare && <h2 id="h-ref">Reference for this explanation</h2>}
        {pinned && (
          <button className="btn btn-small btn-ghost" onClick={onReturn}>
            Return to current
          </button>
        )}
      </div>
      {!citation ? (
        <p className="muted small">The tutor&apos;s cited source appears here.</p>
      ) : src.error && src.error.code !== "CAPABILITY_UNAVAILABLE" ? (
        <div className="notice notice-warn">
          <span className="notice-title">Source unavailable</span>
          <span>{src.error.message}</span>
        </div>
      ) : (
        // The excerpt comes with the saved reply (checked by the backend); the full-source lookup is
        // optional, so a screen that isn't connected yet only drops the status badge and the link.
        <>
          <div className="row">
            <b>{citation.label}</b>
            {src.data && <Status value={src.data.version.temporal_status} />}
            {pinned && <span className="fixture-tag">Earlier citation</span>}
          </div>
          <span className="small muted">{citation.excerpt.heading_path.join(" › ")}</span>
          {/* Long sources scroll inside the panel (keyboard-focusable); a new citation starts at its top. */}
          <div
            key={citation.citation_id}
            className={`excerpt ${bare ? "" : "excerpt-scroll"} ${src.data && src.data.version.temporal_status !== "CURRENT" ? "excerpt-historical" : ""}`}
            tabIndex={bare ? undefined : 0}
            role={bare ? undefined : "region"}
            aria-label={bare ? undefined : `Source excerpt: ${citation.label}`}
            data-testid="source-excerpt"
          >
            <RichText text={citation.excerpt.text} />
          </div>
          {!src.error && (
            <button className="btn btn-small" onClick={() => onOpen(citation)}>
              Open source
            </button>
          )}
        </>
      )}
    </section>
  );
}
