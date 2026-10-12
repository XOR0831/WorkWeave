"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ApiError, EvidenceType, Origin } from "@/types/contracts";
import { useOnChange } from "@/lib/preview/use-on-change";

// ---------------------------------------------------------------- status vocabulary
const TONES: Record<string, string> = {
  CURRENT: "current",
  APPROVED: "approved",
  COMPLETED: "done",
  COMPLETE: "done",
  CLOSED: "done",
  ACKNOWLEDGED: "done",
  RESOLVED: "done",
  CONFIRMED: "done",
  TRANSFERRED: "done",
  VALIDATED: "done",
  PUBLISHED: "approved",
  ON_TRACK: "done",
  DOCUMENTED: "done",
  EXISTING_KNOWLEDGE: "done",
  IN_PROGRESS: "progress",
  ACTIVE: "progress",
  PENDING: "pending",
  PENDING_REVIEW: "pending",
  PROPOSED: "pending",
  EDITED: "pending",
  SUBMITTED: "pending",
  DRAFT: "info",
  DRAFT_CREATED: "info",
  UNDER_REVIEW: "pending",
  REVISION_REQUIRED: "pending",
  NEEDS_REVIEW: "pending",
  AWAITING_SOURCE: "pending",
  MATCHED: "done",
  INTERVIEW_REQUIRED: "pending",
  INTERVIEW_IN_PROGRESS: "progress",
  OPEN: "pending",
  BLOCKED: "blocked",
  DISPUTED: "blocked",
  REJECTED: "blocked",
  MISSING: "blocked",
  OUTDATED: "pending",
  HIGH_WORKLOAD: "pending",
  NEEDS_FOCUS: "pending",
  NEEDS_SUPPORT: "pending",
  SUPERSEDED: "historical",
  HISTORICAL: "historical",
  ARCHIVED: "historical",
  NOT_STARTED: "historical",
  NOT_REQUIRED: "historical",
  DISMISSED: "historical",
  IGNORED: "historical",
  CANCELLED: "historical",
  DISCOVERED: "info",
};

export function humanize(v: string) {
  const s = v.replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function Status({ value, label }: { value: string; label?: string }) {
  const tone = TONES[value] ?? "neutral";
  return <span className={`badge badge-${tone}`}>{label ?? humanize(value)}</span>;
}

export function Evidence({ type }: { type: EvidenceType }) {
  const text = { OBSERVED: "Observed", REPORTED: "Reported", INFERRED: "Inferred", UNKNOWN: "Unknown" }[type];
  return (
    <span className={`evidence evidence-${type.toLowerCase()}`} title={`Evidence type: ${text}`}>
      {text}
    </span>
  );
}

export function OriginTag({ origin }: { origin: Origin }) {
  const text = { SYNTHETIC_SEED: "Synthetic seed record", MANUAL: "Added manually", PREVIEW_FIXTURE: "Preview fixture", AI_ENGINE: "Suggested by the work assistant" }[origin];
  return <span className="fixture-tag">{text}</span>;
}

export function FixtureTag({ children = "Scripted preview response" }: { children?: ReactNode }) {
  return <span className="fixture-tag">{children}</span>;
}

/** Approved page header pattern: eyebrow → title → one-line purpose, actions on the right. */
export function PageHeader({ eyebrow, title, purpose, actions }: { eyebrow?: ReactNode; title: ReactNode; purpose?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {purpose && <p>{purpose}</p>}
      </div>
      {actions && <div className="row page-head-actions">{actions}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- states
export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="stack-s" role="status" aria-live="polite">
      <span className="sr-only">{label}…</span>
      <div className="skeleton" style={{ width: "40%" }} />
      <div className="skeleton" style={{ width: "85%" }} />
      <div className="skeleton" style={{ width: "70%" }} />
    </div>
  );
}

const ERROR_TITLES: Partial<Record<ApiError["code"], string>> = {
  FORBIDDEN: "Not available to you",
  NOT_FOUND: "Not found",
  REVISION_CONFLICT: "Changed since you loaded it",
  GUARD_FAILED: "Can't do that yet",
  CAPABILITY_UNAVAILABLE: "Not connected yet",
  DEPENDENCY_UNAVAILABLE: "Didn't save",
  LIMIT_REACHED: "Demo limit reached",
  SESSION_EXPIRED: "Session expired",
  MALFORMED_INPUT: "Check your input",
};

export function ErrorNotice({ error, onRetry, onDismiss }: { error: ApiError; onRetry?: () => void; onDismiss?: () => void }) {
  const tone = error.code === "CAPABILITY_UNAVAILABLE" || error.code === "LIMIT_REACHED" ? "notice-info" : error.code === "GUARD_FAILED" || error.code === "MALFORMED_INPUT" ? "notice-warn" : "notice-error";
  return (
    <div className={`notice ${tone}`} role="alert">
      <span className="notice-title">{ERROR_TITLES[error.code] ?? "Something went wrong"}</span>
      <span>{error.message}</span>
      {(onRetry || onDismiss) && (
        <div className="row">
          {onRetry && error.retryable && (
            <button className="btn btn-small" onClick={onRetry}>
              Retry
            </button>
          )}
          {onRetry && error.code === "REVISION_CONFLICT" && (
            <button className="btn btn-small" onClick={onRetry}>
              Reload latest
            </button>
          )}
          {onDismiss && (
            <button className="btn btn-small btn-ghost" onClick={onDismiss}>
              Dismiss
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function StateView({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

/** Full-page error with the canonical code semantics (denied, expired, missing, unavailable). */
export function PageError({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  if (error.code === "SESSION_EXPIRED")
    return (
      <StateView title="Your preview session has ended" action={<Link className="btn btn-primary" href="/demo/">Choose a company</Link>}>
        {error.message}
      </StateView>
    );
  if (error.code === "FORBIDDEN")
    return (
      <StateView title="This isn't available to your persona" action={<Link className="btn" href="/home/">Back to home</Link>}>
        {error.message} Switch persona from the header if you&apos;re reviewing another role.
      </StateView>
    );
  return (
    <div className="panel">
      <ErrorNotice error={error} onRetry={onRetry} />
    </div>
  );
}

export function Unavailable({ capability, children }: { capability: string; children: ReactNode }) {
  return (
    <div className="notice notice-info">
      <span className="notice-title">{capability} isn&apos;t connected</span>
      <span>{children}</span>
    </div>
  );
}

// ---------------------------------------------------------------- dialog
export function Dialog({
  open,
  title,
  onClose,
  children,
  footer,
  dirty = false,
  variant = "dialog",
  labelId,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  dirty?: boolean;
  variant?: "dialog" | "drawer" | "sheet";
  labelId?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const [confirming, setConfirming] = useState(false);
  const id = labelId ?? `dlg-${title.replace(/\W+/g, "-").toLowerCase()}`;

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      returnFocus.current = document.activeElement as HTMLElement | null;
      d.showModal();
    } else if (!open && d.open) {
      d.close();
      returnFocus.current?.focus?.();
    }
  }, [open]);

  useOnChange(open, () => {
    if (!open) setConfirming(false);
  });

  const requestClose = () => {
    if (dirty) setConfirming(true);
    else onClose();
  };

  return (
    <dialog
      ref={ref}
      className={variant === "dialog" ? "dialog" : `dialog ${variant}`}
      aria-labelledby={id}
      onCancel={(e) => {
        e.preventDefault();
        requestClose();
      }}
    >
      {open && (
        <div className="dialog-inner">
          <div className="dialog-head">
            <h2 id={id}>{title}</h2>
            <button className="btn btn-ghost btn-small" onClick={requestClose} aria-label={`Close ${title}`}>
              Close
            </button>
          </div>
          <div className="dialog-body">
            {confirming && (
              <div className="notice notice-warn" role="alert">
                <span className="notice-title">Discard unsaved changes?</span>
                <div className="row">
                  <button className="btn btn-small btn-danger" onClick={onClose}>
                    Discard
                  </button>
                  <button className="btn btn-small" onClick={() => setConfirming(false)}>
                    Keep editing
                  </button>
                </div>
              </div>
            )}
            {children}
          </div>
          {footer && <div className="dialog-foot">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

export function Field({ label, hint, htmlFor, children }: { label: string; hint?: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && (
        <span className="hint" id={`${htmlFor}-hint`}>
          {hint}
        </span>
      )}
    </div>
  );
}

export function SavedState({ pending, label }: { pending: boolean; label?: string }) {
  return (
    <span className="small muted" role="status" aria-live="polite">
      {pending ? "Saving…" : label ?? ""}
    </span>
  );
}
