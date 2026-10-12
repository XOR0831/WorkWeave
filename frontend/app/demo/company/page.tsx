"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useCommand, useResource, useRuntime } from "@/lib/preview/client-context";
import { useSearch } from "@/lib/preview/use-search";
import { Dialog, ErrorNotice, Loading, StateView, Status, humanize } from "@/components/ui";
import { limitOf, resetTime } from "@/lib/limits";
import type { ApiError, DemoSession, LocalDemoRun, ScenarioCard, ShowcaseModule } from "@/types/contracts";

/** The daily new-workspace cap: say when it resets, in the visitor's time zone. */
function withReset(error: ApiError, suffix: string): ApiError {
  const limit = limitOf(error, "DEMO_RUN");
  const reset = limit ? ` New demo workspaces are available again at ${resetTime(limit.resets_at)}.` : "";
  return { ...error, message: `${error.message}${reset}${suffix}` };
}

/**
 * Fixed, static-export-compatible company entry: /demo/company/?company_key=…&scenario=…
 * The keys only select catalog content; in the backend phase the server resolves the active
 * pack and issues scope (ADR-024, blueprint/02-frontend).
 */
export default function CompanyEntryPage() {
  const search = useSearch();
  if (!search) return <Loading label="Loading company" />;
  return <Entry companyKey={search.get("company_key") ?? ""} scenario={search.get("scenario") ?? ""} />;
}

function Entry({ companyKey, scenario }: { companyKey: string; scenario: string }) {
  const scenarios = useResource((c) => c.listScenarios());
  const card = scenarios.data?.find((s) => s.key === companyKey && s.scenario_id === scenario);

  if (scenarios.loading) return <Loading label="Loading company" />;
  if (scenarios.error) return <ErrorNotice error={scenarios.error} onRetry={scenarios.reload} />;
  if (!card)
    return (
      <StateView title="This company isn't in the demo catalog" action={<Link className="btn btn-primary" href="/demo/">Choose a company</Link>}>
        The link may be out of date, or the company isn&apos;t available right now.
      </StateView>
    );
  if (card.status !== "READY")
    return (
      <StateView title={`${card.company_name} isn't available right now`} action={<Link className="btn" href="/demo/">Back to the catalog</Link>} />
    );
  return <RunGate card={card} />;
}

/** Looks up this browser's run only once the company is known, so "no run yet" is never inferred early. */
function RunGate({ card }: { card: ScenarioCard }) {
  const run = useResource((c) => c.getLocalDemoRun(card.key), [card.key]);
  if (run.loading) return <Loading label="Checking for an existing run" />;
  if (run.error) return <ErrorNotice error={run.error} onRetry={run.reload} />;
  return <EntryFlow card={card} run={run.data ?? null} reloadRun={run.reload} />;
}

function EntryFlow({ card, run, reloadRun }: { card: ScenarioCard; run: LocalDemoRun | null; reloadRun: () => void }) {
  const server = useRuntime().mode === "http";
  const router = useRouter();
  const init = useCommand();
  const fresh = useCommand();
  const pick = useCommand();
  const [entered, setEntered] = useState<DemoSession | null>(null);
  const [confirmFresh, setConfirmFresh] = useState(false);
  const [freshDone, setFreshDone] = useState(false);
  const autoStarted = useRef(false);

  // First entry (no run yet) or a run without a chosen persona: create or resume the workspace.
  const needsInit = !entered && (!run || !run.persona_selected);
  const start = async () => {
    const s = await init.run((c) => c.startDemoSession(card.key, false));
    if (s) setEntered(s);
  };
  useEffect(() => {
    if (needsInit && !autoStarted.current) {
      autoStarted.current = true;
      void start();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsInit]);

  const choosePersona = async (employee_id: string) => {
    const ok = await pick.run(async (c) => {
      if (!entered) await c.startDemoSession(card.key, false);
      return c.switchPersona(employee_id);
    });
    if (ok) router.push("/home/");
  };
  const showPicker = async () => {
    const s = await init.run((c) => c.startDemoSession(card.key, false));
    if (s) setEntered(s);
  };
  const doFresh = async () => {
    const s = await fresh.run((c) => c.startDemoSession(card.key, true));
    if (s) {
      setConfirmFresh(false);
      setFreshDone(true);
      setEntered(s);
      reloadRun();
    }
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="small muted">
            <Link href="/demo/">Demo catalog</Link> › {card.company_name}
          </p>
          <h1 style={{ marginTop: 6 }}>{card.company_name}</h1>
          <p>{card.story}</p>
        </div>
        <div className="row">
          <span className="fixture-tag">Synthetic company</span>
          <span className="fixture-tag">{server ? "Isolated server-side run" : "Browser-local preview run"}</span>
        </div>
      </div>

      {init.pending && !entered && (
        <section className="panel" role="status" aria-live="polite">
          <h2>Preparing your workspace</h2>
          <p className="muted" style={{ marginTop: 6 }}>
            {server
              ? `Creating your own isolated copy of ${card.company_name} (pack ${card.pack_version}) on the WorkWeave server. Shared company data isn't changed.`
              : `Creating an isolated run of ${card.company_name} (pack ${card.pack_version}) in this browser tab. No server or database is involved in this preview.`}
          </p>
          <div style={{ marginTop: 12 }}>
            <Loading label="Preparing workspace" />
          </div>
        </section>
      )}

      {init.error && !entered && (
        <section className="panel stack-s">
          <ErrorNotice error={withReset(init.error, run ? " Your existing run is unchanged." : "")} />
          <div className="row">
            {!limitOf(init.error) && (
              <button className="btn btn-primary" onClick={() => void start()}>
                Retry
              </button>
            )}
            <Link className="btn" href="/demo/">
              Back to the catalog
            </Link>
          </div>
        </section>
      )}

      {!entered && run?.persona_selected && !init.pending && !init.error && (
        <section className="panel run-strip" aria-labelledby="h-resume">
          <div className="stack-s">
            <div className="row">
              <h2 id="h-resume">You have a run in progress</h2>
              <Status value="IN_PROGRESS" label={server ? "Saved on the server" : "In this browser tab"} />
            </div>
            <span className="small muted">
              Last persona: <b>{run.persona ? `${run.persona.first_name} ${run.persona.last_name}, ${run.persona.role_name}` : "Not chosen"}</b> · Pack {run.pinned_pack_version}
            </span>
          </div>
          <div className="row">
            <button className="btn btn-primary" disabled={pick.pending} onClick={() => run.persona && void choosePersona(run.persona.employee_id)}>
              Resume as {run.persona?.first_name}
            </button>
            <button className="btn" disabled={init.pending} onClick={() => void showPicker()}>
              Choose another persona
            </button>
            <button className="btn btn-danger" onClick={() => setConfirmFresh(true)}>
              Start fresh demo
            </button>
          </div>
          {pick.error && <ErrorNotice error={pick.error} onDismiss={pick.clearError} />}
        </section>
      )}

      {entered && <PersonaPicker session={entered} fresh={freshDone} pending={pick.pending} onPick={choosePersona} error={pick.error} />}

      {entered && run?.persona_selected && !freshDone && (
        <div className="row">
          <button className="btn btn-danger btn-small" onClick={() => setConfirmFresh(true)}>
            Start fresh demo
          </button>
        </div>
      )}

      <Dialog
        open={confirmFresh}
        title="Start a fresh demo?"
        onClose={() => {
          fresh.clearError();
          setConfirmFresh(false);
        }}
        footer={
          <>
            <button
              className="btn"
              onClick={() => {
                fresh.clearError();
                setConfirmFresh(false);
              }}
            >
              Keep my current run
            </button>
            <button className="btn btn-danger" disabled={fresh.pending} onClick={() => void doFresh()}>
              {fresh.pending ? "Preparing new run…" : "Start fresh demo"}
            </button>
          </>
        }
      >
        <p>
          {server ? (
            <>
              This closes <b>your {card.company_name} run</b> and starts a new isolated workspace: every change you made, for all personas in this company, stays with the old run.
            </>
          ) : (
            <>
              This discards <b>your {card.company_name} run in this browser tab</b>: conversations, drafts you haven&apos;t submitted, assignments, handovers and every other change you made, for all personas in this company.
            </>
          )}
        </p>
        <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
          <li>Runs for other companies {server ? "are" : "in this tab are"} kept.</li>
          <li>
            {server
              ? "Nobody else's demo and the shared company data aren't affected; only your run for this company is replaced."
              : "Nobody else's demo and nothing on a server is affected; this preview stores runs only in your browser."}
          </li>
          <li>
            The new run uses the current pack, {card.pack_version}
            {run && run.pinned_pack_version !== card.pack_version ? ` (your current run uses ${run.pinned_pack_version})` : ""}.
          </li>
        </ul>
        <p className="small muted">If the new run can&apos;t be prepared, your current run is kept as it is.</p>
        {fresh.error && <ErrorNotice error={withReset(fresh.error, " Your current run is unchanged.")} />}
      </Dialog>
    </div>
  );
}

// Modules connected to the backend in the live demo; the others are marked "coming soon" there.
const CONNECTED: ShowcaseModule[] = ["ONBOARDING", "COMPANION", "HANDOVER", "EXIT_KT", "REVIEWS", "CURRICULA"];
const MODULE_NAME: Record<ShowcaseModule, string> = {
  ONBOARDING: "AI Onboarding",
  COMPANION: "Work Companion",
  HANDOVER: "Shift Handover",
  EXIT_KT: "Exit KT",
  REVIEWS: "Reviews",
  CURRICULA: "Curricula",
};

function PersonaPicker({ session, fresh, pending, onPick, error }: { session: DemoSession; fresh: boolean; pending: boolean; onPick: (id: string) => void; error: ReturnType<typeof useCommand>["error"] }) {
  const personas = useResource((c) => c.listPersonas(), [session.workspace_id]);
  const api = useRuntime().mode === "http";
  const [all, setAll] = useState(false);
  const everyone = personas.data ?? [];
  // The pack's featured personas showcase the product; the rest stay one click away (and switchable inside WorkWeave).
  const featured = everyone.filter((p) => p.featured);
  const shown = all || featured.length === 0 ? everyone : featured;
  return (
    <section className="panel stack" aria-labelledby="h-pick">
      {fresh && (
        <div className="notice notice-ok" role="status">
          <span>Fresh run ready. Your previous {session.scenario.company_name} run was discarded.</span>
        </div>
      )}
      <div className="stack-s">
        <h2 id="h-pick">Who do you want to be?</h2>
        <p className="muted">
          These are synthetic people from the {session.scenario.company_name} pack. Choosing one isn&apos;t a login; you can switch persona at any time from the header.
        </p>
      </div>
      {personas.loading && <Loading label="Loading personas" />}
      {personas.error && <ErrorNotice error={personas.error} onRetry={personas.reload} />}
      <div className="persona-grid" role="list">
        {shown.map((p) => (
          <div role="listitem" key={p.employee_id} className={`persona-card${p.showcase ? " has-showcase" : ""}`}>
            <button
              className="persona-btn"
              style={{ width: "100%", height: "100%" }}
              disabled={pending}
              onClick={() => onPick(p.employee_id)}
              aria-describedby={p.showcase ? `show-${p.employee_id}` : undefined}
            >
              <span className="persona-top">
                <span className="avatar" aria-hidden="true">
                  {p.first_name[0]}
                  {p.last_name[0]}
                </span>
                <span className="stack-s" style={{ gap: 2 }}>
                  <b>
                    {p.first_name} {p.last_name}
                  </b>
                  <span className="small muted">{p.showcase?.label ?? `${p.role_name}, ${humanize(p.team_role)}`}</span>
                </span>
              </span>
              <span className="small persona-note">{p.scenario_note}</span>
            </button>
            {p.showcase && (
              <div className="persona-show" id={`show-${p.employee_id}`}>
                <b className="small">{p.showcase.headline}</b>
                <ul>
                  {p.showcase.features.map((f, i) => (
                    <li key={i} className="small">
                      <span className="fixture-tag">{MODULE_NAME[f.module]}</span> {f.text}
                      {api && !CONNECTED.includes(f.module) && <span className="muted"> (coming soon)</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
      {featured.length > 0 && featured.length < everyone.length && (
        <button className="link-btn small" style={{ justifySelf: "start" }} aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show the main personas only" : `Show all ${everyone.length} personas`}
        </button>
      )}
      {error && <ErrorNotice error={error} />}
    </section>
  );
}
