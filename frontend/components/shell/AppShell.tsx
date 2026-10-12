"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useClient, useCommand, usePreviewControls, useResource, useRuntime, useSession } from "@/lib/preview/client-context";
import { useUiPrefs } from "@/lib/preview/ui-prefs";
import type { FailureMode } from "@/lib/clients/preview/PreviewClient";
import { Dialog, ErrorNotice, humanize, Status } from "@/components/ui";
import { BrandHeader } from "@/components/shell/Brand";
import { companyEntryHref } from "@/lib/preview/use-search";
import { EvaluatorAccess, accessUntil } from "@/features/demo/EvaluatorAccess";
import { ModuleTour, replayTour } from "@/features/tour/ModuleTour";
import { tourFor } from "@/features/tour/tours";

const NAV = [
  { href: "/home/", label: "Home", icon: "⌂" },
  { href: "/onboarding/", label: "Onboarding", icon: "▦" },
  { href: "/companion/", label: "Work Companion", icon: "✧" },
  { href: "/handover/", label: "Shift Handover", icon: "⇄" },
  { href: "/exit-kt/", label: "Exit KT", icon: "↗" },
  { href: "/reviews/", label: "Reviews", icon: "✓" },
  { href: "/memory/", label: "Knowledge", icon: "▤" },
];
/** Coordinator tools. Shown to every persona so evaluators can find them; the page explains access. */
const COORD_NAV = [{ href: "/curricula/", label: "Curricula & sources", icon: "◫" }];

export function PreviewBand({ onTools, mode = "preview", limits = false }: { onTools?: () => void; mode?: "preview" | "http"; limits?: boolean }) {
  return (
    <div className="preview-band" role="note" aria-label="Preview notice">
      <span className="band-label">
        <i aria-hidden="true" />
        {mode === "http" ? "Synthetic demo · local backend" : "Interactive UI preview"}
      </span>
      <span className="band-text">
        {mode === "http" ? (
          <>
            <strong>Synthetic companies on the local WorkWeave backend.</strong> Every module uses PostgreSQL; the inbox is delivered through Firestore. AI replies come from the AI engineer&apos;s engines where this server connects them.
          </>
        ) : (
          <>
            <strong>UI preview with simulated data and responses.</strong> Synthetic data kept only in this browser tab; no backend, database or AI is connected, and conversations are scripted fixtures.
          </>
        )}
      </span>
      {limits && <EvaluatorAccess variant="band" />}
      {onTools && (
        <button className="band-btn" onClick={onTools} data-tour="demo-tools">
          {mode === "http" ? "Demo tools ↗" : "Review tools ↗"}
        </button>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { session, ready } = useSession();
  const controls = usePreviewControls();
  const runtime = useRuntime();
  const [tools, setTools] = useState(false);
  const [demoTools, setDemoTools] = useState(false);
  const [switcher, setSwitcher] = useState(false);
  const unread = ready && session ? runtime.unreadCount() : 0;
  // Entry pages (/, /demo/*, /app/) never show persona context; /app/ never shows demo controls (ADR-024).
  const appBoundary = Boolean(pathname?.startsWith("/app"));
  const isCatalog = pathname === "/" || Boolean(pathname?.startsWith("/demo")) || appBoundary;
  const inDemo = Boolean(session?.persona_selected) && !isCatalog;

  const current = [...NAV, ...COORD_NAV].find((n) => pathname?.startsWith(n.href)) ?? (pathname?.startsWith("/inbox") ? { label: "Inbox" } : undefined);
  // API mode: the Coordinator nav follows the authoritative workspace-scoped curriculum:read grant.
  // The preview keeps showing it to every persona (its pages explain who may use them).
  const showCoordinator = runtime.mode === "preview" || Boolean(session?.persona.grants.includes("curriculum.read"));
  const tour = tourFor(pathname);
  const initials = session ? `${session.persona.first_name[0] ?? ""}${session.persona.last_name[0] ?? ""}` : "";

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <PreviewBand
        mode={runtime.mode}
        limits={runtime.mode === "http" && inDemo && !appBoundary}
        onTools={controls && session && !appBoundary ? () => setTools(true) : runtime.mode === "http" && inDemo && !appBoundary ? () => setDemoTools(true) : undefined}
      />
      {session && inDemo ? (
        <div className="shell">
          <div className="sidebar">
            <header className="sidebar-brand">
              <Link className="brand" href="/home/">
                <BrandHeader />
              </Link>
            </header>
            <div className="sidebar-company">
              <span className="company-tile" aria-hidden="true">
                {session.scenario.company_name[0]}
              </span>
              <span className="company-text">
                <strong>{session.scenario.company_name}</strong>
                <small>{session.scenario.industry}</small>
              </span>
              <span className="synthetic-dot" role="img" title="Synthetic company" aria-label="Synthetic company" />
            </div>
            {session.access?.tier === "EVALUATOR" && (
              <p className="sidebar-access" data-testid="access-badge">
                <Status value="APPROVED" label="Evaluator access" />
                <small>until {accessUntil(session.access)}</small>
              </p>
            )}
            <Link className="change-company" href="/demo/">
              Change company
            </Link>
            <nav className="module-nav" aria-label="Modules">
              <p className="nav-label">Your workspace</p>
              <ul>
                {/* Shift Handover is only for shift leads (owner decision 2026-10-10). */}
                {NAV.filter((n) => n.href !== "/handover/" || session.persona.grants.includes("handover.publish")).map((n) => (
                  <li key={n.href}>
                    <Link href={n.href} className="nav-item" aria-current={pathname?.startsWith(n.href) ? "page" : undefined}>
                      <span className="nav-icon" aria-hidden="true">
                        {n.icon}
                      </span>
                      {n.label}
                    </Link>
                  </li>
                ))}
              </ul>
              {showCoordinator && (
                <>
                  <p className="nav-label nav-label-group">Coordinator</p>
                  <ul>
                    {COORD_NAV.map((n) => (
                      <li key={n.href}>
                        <Link href={n.href} className="nav-item" aria-current={pathname?.startsWith(n.href) ? "page" : undefined}>
                          <span className="nav-icon" aria-hidden="true">
                            {n.icon}
                          </span>
                          {n.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </nav>
            <div className="sidebar-foot">
              <p className="sidebar-tagline">Weaving Knowledge Into Every Work</p>
              <div className="person">
                <span className="avatar" aria-hidden="true">
                  {initials}
                </span>
                <span className="context" aria-label="Current persona">
                  <b>
                    {session.persona.first_name} {session.persona.last_name}
                  </b>
                  <small>
                    {session.persona.role_name}, {humanize(session.persona.team_role)}
                  </small>
                </span>
              </div>
              <button className="btn btn-small btn-full" onClick={() => setSwitcher(true)}>
                Switch persona
              </button>
            </div>
          </div>
          <div className="workspace">
            <div className="topbar">
              <nav className="breadcrumb" aria-label="Breadcrumb">
                <span className="crumb-company">{session.scenario.company_name}</span>
                <span aria-hidden="true" className="crumb-sep">
                  /
                </span>
                <strong aria-current="page">{current?.label ?? "Workspace"}</strong>
              </nav>
              <div className="topbar-right">
                <span className="saved-note">{runtime.mode === "http" ? "Saved on the local server" : "Saved in this browser tab only"}</span>
                {tour && (
                  <button className="btn btn-small" onClick={replayTour} data-tour="page-tour">
                    Page tour
                  </button>
                )}
                <Link className="btn btn-small" href="/inbox/" aria-label={`Inbox, ${unread} unread`}>
                  Inbox{unread > 0 && <span className="count">{unread}</span>}
                </Link>
              </div>
            </div>
            <main id="main" className="page" tabIndex={-1}>
              {tour && <ModuleTour key={tour} tour={tour} />}
              {children}
            </main>
          </div>
        </div>
      ) : (
        <>
          <header className="entry-header">
            <Link className="brand" href={appBoundary ? "/" : session?.persona_selected ? "/home/" : "/demo/"}>
              <BrandHeader />
            </Link>
            {!appBoundary && (
              <span className="entry-actions">
                <span className="entry-note">Synthetic demo</span>
                <EvaluatorAccess prompt={pathname === "/"} />
              </span>
            )}
          </header>
          <main id="main" className="page" tabIndex={-1}>
            {children}
          </main>
        </>
      )}
      <PersonaSwitcher open={switcher} onClose={() => setSwitcher(false)} />
      {controls && <ReviewTools controls={controls} open={tools} onClose={() => setTools(false)} />}
      {runtime.mode === "http" && demoTools && <DemoTools onClose={() => setDemoTools(false)} />}
    </>
  );
}

function PersonaSwitcher({ open, onClose }: { open: boolean; onClose: () => void }) {
  const client = useClient();
  const router = useRouter();
  const { session, personas } = useSession();
  const [busy, setBusy] = useState<string | null>(null);
  return (
    <Dialog open={open} title="Switch persona" onClose={onClose}>
      <p className="muted small">
        Synthetic demo personas from the {session?.scenario.company_name} pack. This isn&apos;t a login. Switching changes whose view and permissions you preview; each persona keeps a separate conversation, and you start again from Home.
      </p>
      <div className="persona-grid">
        {personas.map((p) => (
          <button
            key={p.employee_id}
            className="persona-btn"
            aria-pressed={session?.persona.employee_id === p.employee_id}
            disabled={busy !== null}
            onClick={async () => {
              setBusy(p.employee_id);
              // Always start the new persona from Home: a module page open for the old persona (a
              // draft, a ticket, a review) would otherwise act on state that isn't the new persona's.
              const switched = await client.switchPersona(p.employee_id).then(() => true, () => false);
              setBusy(null);
              onClose();
              if (switched && p.employee_id !== session?.persona.employee_id) router.push("/home/");
            }}
          >
            <b>
              {p.first_name} {p.last_name}
            </b>
            <span className="small">
              {p.role_name} · {humanize(p.team_role)}
            </span>
            <span className="small muted">{p.scenario_note}</span>
          </button>
        ))}
      </div>
    </Dialog>
  );
}

const FAILURES: { value: FailureMode; label: string; hint: string }[] = [
  { value: "none", label: "Normal", hint: "Requests succeed after a short simulated delay." },
  { value: "slow", label: "Slow responses", hint: "Shows loading and saving states." },
  { value: "fail_next", label: "Next save fails", hint: "Simulated outage; nothing commits and input is kept." },
  { value: "stale_next", label: "Next save is stale", hint: "Simulated revision conflict (409)." },
  { value: "deny_next", label: "Next action denied", hint: "Simulated permission denial (403)." },
  { value: "expire", label: "Expire session", hint: "Next request reports an expired session." },
];

function ReviewTools({ controls, open, onClose }: { controls: NonNullable<ReturnType<typeof usePreviewControls>>; open: boolean; onClose: () => void }) {
  const client = useClient();
  const router = useRouter();
  const { simulateVoice, setSimulateVoice } = useUiPrefs();
  const [mode, setMode] = useState<FailureMode>(controls.getFailureMode());
  const docs = useResource((c) => c.listDocumentVersions(), [open]);
  return (
    <Dialog open={open} title="Review tools" onClose={onClose} variant="drawer">
      <p className="small muted">For screen reviewers only. These simulate states; they don&apos;t exist in the product.</p>
      <fieldset>
        <legend>Request behaviour</legend>
        {FAILURES.map((f) => (
          <label key={f.value} className="choice">
            <input
              type="radio"
              name="failure"
              checked={mode === f.value}
              onChange={() => {
                setMode(f.value);
                controls.setFailureMode(f.value);
              }}
            />
            <span>
              <b>{f.label}</b>
              <br />
              <span className="small muted">{f.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Voice</legend>
        <label className="choice">
          <input type="checkbox" checked={simulateVoice} onChange={(e) => setSimulateVoice(e.target.checked)} />
          <span>
            <b>Show the tap-to-talk listening state</b>
            <br />
            <span className="small muted">Simulated: no microphone is accessed. Stopping fills in the next script prompt as a transcript draft you can edit.</span>
          </span>
        </label>
      </fieldset>
      <fieldset>
        <legend>Source revocation</legend>
        {(docs.data ?? []).map((d) => (
          <label key={d.document_version_id} className="choice">
            <input type="checkbox" checked={controls.isRevoked(d.document_version_id)} onChange={() => controls.toggleRevokedSource(d.document_version_id)} />
            <span>
              Revoke {d.document_code} v{d.version}
            </span>
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Shift clock</legend>
        <p className="small muted">Moves the handover forward one occurrence (Afternoon → Evening → next Morning) to walk the three-shift path.</p>
        <button className="btn btn-small" onClick={() => controls.advanceShift()}>
          Advance to next shift
        </button>
      </fieldset>
      <fieldset>
        <legend>Workspace</legend>
        <p className="small muted">To discard this company&apos;s run, use the confirmed &quot;Start fresh demo&quot; on the company page.</p>
        <div className="row">
          <button
            className="btn btn-small"
            onClick={async () => {
              await client.endSession();
              onClose();
              router.push("/demo/");
            }}
          >
            Leave to catalog
          </button>
        </div>
      </fieldset>
    </Dialog>
  );
}

/** Wraps module pages: shows a clear state instead of a blank page when there's no session. */
export function RequireSession({ children }: { children: ReactNode }) {
  const { session, ready } = useSession();
  const runtime = useRuntime();
  if (!ready) return null;
  const failed = runtime.loadError();
  if (failed && !session)
    return (
      <div className="state" role="alert">
        <h2>Can&apos;t reach the WorkWeave service</h2>
        <p>{failed.message}</p>
        <button className="btn btn-primary" onClick={() => window.location.reload()}>
          Try again
        </button>
      </div>
    );
  if (!session)
    return (
      <div className="state">
        <h2>{runtime.mode === "http" ? "No demo workspace is open" : "No preview workspace is open"}</h2>
        <p>Choose a synthetic company to start an isolated {runtime.mode === "http" ? "demo" : "preview"} workspace.</p>
        <Link className="btn btn-primary" href="/demo/">
          Choose a company
        </Link>
      </div>
    );
  if (!session.persona_selected)
    return (
      <div className="state">
        <h2>Choose who you want to be first</h2>
        <p>Pick a synthetic persona from {session.scenario.company_name} to open this screen.</p>
        <Link className="btn btn-primary" href={companyEntryHref(session.scenario.key, session.scenario.scenario_id)}>
          Choose a persona
        </Link>
      </div>
    );
  return <>{children}</>;
}

/** API mode, visitor runs only (ADR-042): the demo shift clock. An evaluator tool, never a business action. */
function DemoTools({ onClose }: { onClose: () => void }) {
  const q = useResource((c) => c.getShiftClock(), []);
  const cmd = useCommand();
  const [confirm, setConfirm] = useState(false);
  const [moved, setMoved] = useState<number | null>(null);
  const clock = q.data;
  return (
    <Dialog open title="Demo tools" onClose={onClose} variant="drawer">
      <fieldset className="stack-s">
        <legend>Shift clock</legend>
        <p className="small muted">
          Moves your demo run to the middle of the next shift, as if the clock had moved on. Ticket due times move with it; recorded history keeps its time. Only this run changes.
        </p>
        {q.loading ? (
          <p className="small muted">Loading shifts…</p>
        ) : q.error ? (
          <ErrorNotice error={q.error} onRetry={q.reload} />
        ) : (
          <>
            <dl className="case-rows">
              <div>
                <dt>In progress</dt>
                <dd>{clock?.current ? `${clock.current.name} · ${clock.current.window_label} · lead ${clock.current.lead_name || "not set"}` : "No shift in progress"}</dd>
              </div>
              <div>
                <dt>Next</dt>
                <dd>{clock?.next ? `${clock.next.name} · ${clock.next.window_label} · lead ${clock.next.lead_name || "not set"}` : "No later shift"}</dd>
              </div>
            </dl>
            {clock?.handover_unpublished && clock.current && clock.next && (
              <div className="notice notice-warn" role="note">
                <span className="notice-title">The {clock.current.name} handover isn&apos;t published</span>
                <span>
                  The {clock.next.name} shift receives nothing new, and only the lead of the shift in progress can publish, so the draft stays unpublished.
                </span>
                <label className="choice small">
                  <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /> Move on anyway
                </label>
              </div>
            )}
            {moved !== null && (
              <p className="small" role="status">
                Moved ahead {moved} h. Pages now show the new shift.
              </p>
            )}
            {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
            <div>
              <button
                className="btn btn-primary"
                disabled={!clock?.next || cmd.pending || (clock.handover_unpublished && Boolean(clock.current) && !confirm)}
                onClick={async () => {
                  const r = await cmd.run((c, k) => c.advanceShiftClock(confirm, { idempotency_key: k }));
                  if (r) {
                    setMoved(r.moved_hours ?? 0);
                    setConfirm(false);
                    q.reload();
                  }
                }}
              >
                {cmd.pending ? "Moving…" : clock?.next ? `Advance to ${clock.next.name}` : "Advance to next shift"}
              </button>
            </div>
          </>
        )}
      </fieldset>
    </Dialog>
  );
}
