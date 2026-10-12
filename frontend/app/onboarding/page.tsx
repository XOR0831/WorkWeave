"use client";

import { markFreshStart } from "@/lib/voice/prefs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { RequireSession } from "@/components/shell/AppShell";
import { useCommand, useResource, useRuntime, useSession } from "@/lib/preview/client-context";
import { ErrorNotice, Loading, PageError, StateView, Status } from "@/components/ui";
import { LearningPath, pathProgress } from "@/features/onboarding/LearningPath";

export default function OnboardingOverviewPage() {
  return (
    <RequireSession>
      <Overview />
    </RequireSession>
  );
}

function Overview() {
  const { session } = useSession();
  const router = useRouter();
  const pid = session?.persona.employee_id;
  const ov = useResource((c) => c.getOnboarding(), [pid]);
  const start = useCommand();
  const canSupervise = session?.persona.grants.includes("onboarding.supervise");
  // The preview scripts its tutor; in API mode the server says whether the tutor engine is connected.
  const api = useRuntime().mode === "http";
  const caps = useResource((c) => (api ? c.getCapabilities() : Promise.resolve(null)), [api]);
  const tutorConnected = !api || caps.data?.conversation_engine === "AVAILABLE";

  if (ov.loading) return <Loading label="Loading onboarding" />;
  if (ov.error) return <PageError error={ov.error} onRetry={ov.reload} />;
  if (!ov.data)
    return (
      <StateView
        title="No onboarding is assigned to you"
        action={
          canSupervise ? (
            <Link className="btn btn-primary" href="/onboarding/progress/">
              View team progress
            </Link>
          ) : (
            <Link className="btn" href="/companion/">
              Open Work Companion
            </Link>
          )
        }
      >
        Assigned curricula appear here once your organization assigns one.
      </StateView>
    );

  const o = ov.data;
  const subs = o.topics.flatMap((t) => t.subtopics);
  const progress = pathProgress(o.topics);
  const current = subs.find((s) => s.subtopic_id === o.current_subtopic_id);
  const allDone = progress.done === progress.required;
  const hasStarted = o.session_status !== "NONE" || subs.some((s) => s.status !== "NOT_STARTED");

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{o.curriculum_name}</h1>
          <p>
            Assigned curriculum v{o.curriculum_version}. Learn through one conversation; the tutor opens it, and progress counts only demonstrated objectives.
          </p>
        </div>
        {canSupervise && (
          <Link className="btn" href="/onboarding/progress/">
            Team progress
          </Link>
        )}
      </div>
      <div className="grid-2">
        <section className="panel stack-s" aria-labelledby="h-progress">
          <h2 id="h-progress">Your progress</h2>
          <p>
            {progress.label}. {o.saved_at ?? "Nothing saved yet."}
          </p>
          {current && !allDone && (
            <p>
              {current.status === "IN_PROGRESS" ? "In progress" : "Next"}: <b>{current.name}</b>
            </p>
          )}
          {allDone && <Status value="COMPLETED" label="Curriculum complete" />}
          {start.error && <ErrorNotice error={start.error} onRetry={() => void go()} />}
          {!allDone && (
            <div className="row">
              <button className="btn btn-primary" disabled={start.pending} onClick={() => void go()}>
                {start.pending ? "Opening…" : hasStarted ? "Resume conversation" : "Start conversation"}
              </button>
            </div>
          )}
          {!allDone && !tutorConnected && !caps.loading && (
            <div className="notice notice-info">
              <span className="notice-title">The tutor isn&apos;t connected yet</span>
              <span>You can open the conversation, take a break and resume; that&apos;s saved in the WorkWeave database. Replies arrive with the tutor integration.</span>
            </div>
          )}
          <p className="small muted">Your questions and answers stay private. Your supervisor sees progress by subtopic, not your conversation.</p>
        </section>
        <section className="panel" aria-labelledby="h-path">
          <h2 id="h-path" style={{ marginBottom: 12 }}>
            Learning path
          </h2>
          <LearningPath topics={o.topics} currentId={o.current_subtopic_id} expanded />
          <p className="small muted" style={{ marginTop: 8 }}>
            {o.source_versions.length
              ? `Sources: ${o.source_versions.map((v) => `${v.document_code} v${v.version} (${v.temporal_status.toLowerCase()})`).join(", ")}`
              : "Source documents aren't connected yet."}
          </p>
        </section>
      </div>
    </div>
  );

  async function go() {
    const r = await start.run((c) => c.startOnboardingSession());
    // A brand-new conversation (no learner message yet): its opening may be read aloud on arrival.
    if (r && !r.transcript.some((m) => m.sender === "EMPLOYEE")) markFreshStart(r.learning_session_id);
    if (r) router.push("/onboarding/session/");
  }
}
