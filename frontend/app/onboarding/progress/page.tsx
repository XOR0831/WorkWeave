"use client";

import { RequireSession } from "@/components/shell/AppShell";
import { useResource, useSession } from "@/lib/preview/client-context";
import { Loading, PageError, StateView, Status } from "@/components/ui";

export default function SupervisorProgressPage() {
  return (
    <RequireSession>
      <Progress />
    </RequireSession>
  );
}

function Progress() {
  const { session } = useSession();
  const rows = useResource((c) => c.getSupervisorProgress(), [session?.persona.employee_id]);
  if (rows.loading) return <Loading label="Loading team progress" />;
  if (rows.error) return <PageError error={rows.error} onRetry={rows.reload} />;
  const data = rows.data ?? [];
  const subNames = data[0]?.subtopics.map((s) => s.name) ?? [];
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Team onboarding progress</h1>
          <p>
            Progress by subtopic for assigned curricula. Learners&apos; conversations, questions and attempts stay private and aren&apos;t shown here. There are no rankings.
          </p>
        </div>
      </div>
      {data.length === 0 ? (
        <StateView title="No one on your team has assigned onboarding" />
      ) : (
        <section className="panel table-wrap" tabIndex={0} aria-label="Team progress table (scrolls horizontally)">
          <table>
            <caption className="sr-only">Onboarding progress by employee and subtopic</caption>
            <thead>
              <tr>
                <th scope="col">Employee</th>
                <th scope="col">Curriculum</th>
                {subNames.map((n) => (
                  <th key={n} scope="col">
                    {n}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.employee_name}>
                  <th scope="row">{r.employee_name}</th>
                  <td>
                    {r.curriculum_name} v{r.curriculum_version}
                  </td>
                  {r.subtopics.map((s) => (
                    <td key={s.name}>
                      <Status value={s.status} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <p className="small muted">Completing onboarding doesn&apos;t grant operational authorization; you confirm readiness separately.</p>
    </div>
  );
}
