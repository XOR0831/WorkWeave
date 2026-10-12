"use client";

import Link from "next/link";
import { useResource, useRuntime } from "@/lib/preview/client-context";
import { companyEntryHref } from "@/lib/preview/use-search";
import { ErrorNotice, Loading, Status } from "@/components/ui";
import { BrandLockup } from "@/components/shell/Brand";
import type { LocalDemoRun, ScenarioCard } from "@/types/contracts";

/** Public demo catalog (ADR-024): GET /scenarios in HTTP mode; labelled fixtures in the UI preview. */
export default function DemoCatalogPage() {
  const server = useRuntime().mode === "http";
  const scenarios = useResource((c) => c.listScenarios());
  const runs = useResource(async (c) => {
    const list = (await c.listScenarios().catch(() => [] as ScenarioCard[])) ?? [];
    const found = await Promise.all(list.map((s) => c.getLocalDemoRun(s.key)));
    return found.filter((r): r is LocalDemoRun => Boolean(r));
  });

  return (
    <div className="stack">
      <section className="catalog-hero catalog-hero-center">
        <BrandLockup width={320} />
        <p className="eyebrow">Synthetic demo</p>
        <h1>Keep work moving when people learn, hand over and move on.</h1>
        <p className="muted">
          WorkWeave connects onboarding, daily work, shift handover and exit knowledge transfer over one shared record of people, work and approved knowledge. Choose a synthetic company to explore it as one of its people.
        </p>
        <div className="lifecycle" aria-label="Lifecycle">
          <span>Learn</span>
          <i />
          <span>Work</span>
          <i />
          <span>Shift handover</span>
          <i />
          <span>Exit knowledge transfer</span>
          <i />
          <span>Approved knowledge</span>
        </div>
      </section>

      {scenarios.loading && <Loading label="Loading companies" />}
      {scenarios.error && <ErrorNotice error={scenarios.error} onRetry={scenarios.reload} />}
      {scenarios.data && scenarios.data.length === 0 && <p className="muted">No synthetic companies are ready yet.</p>}

      <div className="grid-3">
        {scenarios.data?.map((s) => {
          const run = runs.data?.find((r) => r.key === s.key);
          return (
            <article key={s.key} className="panel company-card" aria-labelledby={`co-${s.key}`}>
              <div className="row-between">
                <span className="eyebrow">{s.industry}</span>
                <span className="row">
                  {run && <Status value="IN_PROGRESS" label="Run in progress" />}
                  <Status value={s.status === "READY" ? "APPROVED" : "BLOCKED"} label={s.status === "READY" ? "Ready" : "Unavailable"} />
                </span>
              </div>
              <div>
                <h2 id={`co-${s.key}`}>{s.company_name}</h2>
                <p className="small muted">Used for: {s.role_in_review}</p>
              </div>
              <p>{s.story}</p>
              <div className="company-card-foot">
                <span className="small muted">Pack {s.pack_version}</span>
                <span className="fixture-tag">Synthetic review fixture, not a validated pack</span>
              </div>
              {s.status === "READY" ? (
                <Link className="btn btn-primary btn-full" href={companyEntryHref(s.key, s.scenario_id)} aria-describedby={`co-${s.key}`}>
                  {run ? "Resume or restart" : "Open demo"}
                </Link>
              ) : (
                <span className="small muted">Not available right now.</span>
              )}
            </article>
          );
        })}
      </div>
      <p className="small muted catalog-foot">
        {server
          ? "Each company run is yours alone: an isolated copy on the local WorkWeave server that ends when its session expires."
          : "Each company run is yours alone and lives only in this browser tab. Nothing is stored on a server in this preview."}
      </p>
    </div>
  );
}
