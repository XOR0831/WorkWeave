import type { Topic } from "@/types/contracts";
import { humanize } from "@/components/ui";

/** Completion counts required subtopics only; optional ones (e.g. SOP reference aids) are listed separately. */
export function pathProgress(topics: Topic[]) {
  const subs = topics.flatMap((t) => t.subtopics);
  const required = subs.filter((s) => !s.optional);
  const optional = subs.length - required.length;
  const done = required.filter((s) => s.status === "COMPLETED").length;
  const label = optional ? `${done} of ${required.length} required subtopics complete · ${optional} optional` : `${done} of ${required.length} subtopics complete`;
  const short = optional ? `${done} of ${required.length} required complete · ${optional} optional` : `${done} of ${required.length} complete`;
  return { done, required: required.length, optional, label, short };
}

export function LearningPath({ topics, currentId, expanded = false }: { topics: Topic[]; currentId?: string; expanded?: boolean }) {
  const subs = topics.flatMap((t) => t.subtopics);
  const current = subs.find((s) => s.subtopic_id === currentId);
  const list = (
    <ol className="path" aria-label="Subtopics">
      {subs.map((s, i) => (
        <li key={s.subtopic_id}>
          <span className={`knot ${s.status === "COMPLETED" ? "knot-done" : s.status === "IN_PROGRESS" ? "knot-progress" : ""}`} aria-hidden="true">
            {s.status === "COMPLETED" ? "✓" : i + 1}
          </span>
          <span className={s.subtopic_id === currentId ? "path-current" : undefined}>
            {s.name}
            <br />
            <span className="small muted">
              {s.subtopic_id === currentId ? `Current position · ${humanize(s.status)}` : humanize(s.status)}
              {s.optional ? " · Optional" : ""}
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
  if (expanded) return list;
  return (
    <details>
      <summary>
        <b>{current ? current.name : "All subtopics complete"}</b>{" "}
        <span className="small muted">
          ({pathProgress(topics).label}). Show full path
        </span>
      </summary>
      <div style={{ marginTop: 12 }}>{list}</div>
    </details>
  );
}
