"use client";

import Link from "next/link";
import { RequireSession } from "@/components/shell/AppShell";
import { useResource, useSession } from "@/lib/preview/client-context";
import { Loading, PageHeader, Status, humanize } from "@/components/ui";
import { pathProgress } from "@/features/onboarding/LearningPath";

/** A module card whose data isn't available (e.g. its API slice isn't wired yet). Never shown as "nothing assigned". */
function NotConnected({ message }: { message: string }) {
  return (
    <>
      <p className="home-card-title home-card-title-quiet">Not connected yet</p>
      <p className="small muted" title={message}>
        This card&apos;s data isn&apos;t wired to the backend in this build.
      </p>
    </>
  );
}

export default function HomePage() {
  return (
    <RequireSession>
      <Home />
    </RequireSession>
  );
}

function Home() {
  const { session, nameOf } = useSession();
  const pid = session?.persona.employee_id;
  const onboarding = useResource((c) => c.getOnboarding(), [pid]);
  const items = useResource((c) => c.listWorkItems(), [pid]);
  const dash = useResource((c) => c.getWorkDashboard(), [pid]);
  const kt = useResource((c) => c.getExitKtCase(), [pid]);
  const inbox = useResource((c) => c.listNotifications(), [pid]);
  if (!session) return null;
  const p = session.persona;
  const t = session.scenario.terminology;
  const mine = (items.data ?? []).filter((i) => i.assignee_id === p.employee_id && !i.historical);
  const progress = pathProgress(onboarding.data?.topics ?? []);
  const isLead = p.grants.includes("handover.publish");
  const isReviewer = p.grants.includes("knowledge.review");

  const blocked = mine.filter((i) => i.status === "BLOCKED").length;
  const unread = (inbox.data ?? []).filter((n) => !n.read_at).length;
  const [next, ...later] = dash.data?.priorities ?? [];
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <div className="stack home">
      <PageHeader
        eyebrow={`${session.scenario.company_name} · ${p.team_name}`}
        title={`${greeting}, ${p.first_name}.`}
        purpose={
          <>
            {p.role_name}
            {dash.data?.shift_label ? `, ${dash.data.shift_label}` : ""}. {p.scenario_note}.
          </>
        }
        actions={
          <>
            <Status value={p.employment_status} />
            <span className="fixture-tag">Synthetic persona</span>
          </>
        }
      />

      {next && (
        <section className="next-band" aria-labelledby="h-next">
          <div>
            <h2 id="h-next" className="eyebrow">
              Next step
            </h2>
            <p className="next-band-title">{next}</p>
            {later.length > 0 && <p className="small muted">Also on your list: {later.join(" · ")}</p>}
          </div>
          <div className="row">
            {isReviewer && (
              <Link className="link-btn" href="/reviews/">
                Open the reviewer workspace
              </Link>
            )}
            <Link className="btn btn-primary" href="/companion/">
              Open Work Companion
            </Link>
          </div>
        </section>
      )}

      <div className="home-grid">
        <section className="panel home-card" aria-labelledby="h-learning">
          <h2 id="h-learning" className="eyebrow">
            Learning
          </h2>
          {onboarding.loading ? (
            <Loading />
          ) : onboarding.error ? (
            <NotConnected message={onboarding.error.message} />
          ) : onboarding.data ? (
            <>
              <p className="home-card-title">
                {progress.label}
              </p>
              <p className="small muted">
                {onboarding.data.curriculum_name} v{onboarding.data.curriculum_version} · {onboarding.data.saved_at ?? "Not started yet"}
              </p>
              <Link className="btn home-card-action" href="/onboarding/">
                Open onboarding
              </Link>
            </>
          ) : (
            <>
              <p className="home-card-title home-card-title-quiet">No onboarding assigned</p>
              <p className="small muted">Nothing is assigned to you.</p>
            </>
          )}
        </section>

        <section className="panel home-card" aria-labelledby="h-work">
          <h2 id="h-work" className="eyebrow">
            Your {t.workItems}
          </h2>
          {items.loading ? (
            <Loading />
          ) : items.error ? (
            <NotConnected message={items.error.message} />
          ) : (
            <>
              <p className="home-card-title">
                {mine.length} open · {blocked} blocked
              </p>
              {mine.length ? (
                <ul className="home-lines">
                  {mine.map((i) => (
                    <li key={i.work_item_id}>
                      <span className="mono-id">{i.external_id}</span> {i.title} <span className="muted">· {humanize(i.status)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="small muted">Nothing is assigned to you right now.</p>
              )}
            </>
          )}
          {!items.error && (
            <Link className="btn home-card-action" href="/companion/">
              Open Work Companion
            </Link>
          )}
        </section>

        <section className="panel home-card" aria-labelledby="h-shift">
          <h2 id="h-shift" className="eyebrow">
            Shift continuity
          </h2>
          {dash.loading ? (
            <Loading />
          ) : dash.error ? (
            <NotConnected message={dash.error.message} />
          ) : dash.data?.shift_label ? (
            <>
              <p className="home-card-title">{dash.data.shift_label}</p>
              {dash.data.incoming_continuity && <p className="small muted">Incoming: {dash.data.incoming_continuity}</p>}
              {isLead && (
                <>
                  <p className="small">You lead this shift and publish its handover directly.</p>
                  <Link className="btn home-card-action" href="/handover/">
                    Open Shift Handover
                  </Link>
                </>
              )}
            </>
          ) : (
            <>
              <p className="home-card-title home-card-title-quiet">Not on a shift roster</p>
              <p className="small muted">You aren&apos;t on a shift roster in this workspace.</p>
            </>
          )}
        </section>

        <section className="panel home-card" aria-labelledby="h-kt">
          <h2 id="h-kt" className="eyebrow">
            Knowledge transfer
          </h2>
          {kt.loading ? (
            <Loading />
          ) : kt.error && kt.error.code !== "NOT_FOUND" && kt.error.code !== "FORBIDDEN" ? (
            <NotConnected message={kt.error.message} />
          ) : kt.data ? (
            <>
              <p className="home-card-title">
                {humanize(kt.data.case_kind)} · {humanize(kt.data.status).toLowerCase()}
              </p>
              <p className="small muted">
                Case for {nameOf(kt.data.employee_id)} · Reviewer {nameOf(kt.data.reviewer_employee_id)} · Successor {nameOf(kt.data.package.successor_employee_id)}
              </p>
              <Link className="btn home-card-action" href="/exit-kt/">
                Open Exit KT
              </Link>
            </>
          ) : (
            <>
              <p className="home-card-title home-card-title-quiet">No active case</p>
              <p className="small muted">You aren&apos;t part of a knowledge-transfer case.</p>
            </>
          )}
        </section>
      </div>

      <p className="small muted home-foot">
        {inbox.error ? (
          "Notifications aren't connected yet"
        ) : unread > 0 ? (
          <Link href="/inbox/">
            You have {unread} unread notification{unread === 1 ? "" : "s"}
          </Link>
        ) : (
          "No unread notifications"
        )}
      </p>
    </div>
  );
}
