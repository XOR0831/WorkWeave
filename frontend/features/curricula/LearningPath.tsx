"use client";

import { useState } from "react";
import { Status } from "@/components/ui";
import type { Curriculum, CurriculumSubtopicDef, CurriculumTopicDef } from "@/types/contracts";
import { ObjectiveDialog, PathDialog } from "./dialogs";

/** Subtopics with confirmed coverage, by stage of the source that covers them. */
function coverage(c: Curriculum, subtopic_id: string) {
  const hits = c.sources.filter((s) => s.mappings_confirmed && s.sections.some((x) => x.mapping.kind === "SUBTOPIC" && x.mapping.subtopic_id === subtopic_id));
  if (hits.some((s) => s.stage === "APPROVED")) return { value: "APPROVED", label: "Approved source" };
  if (hits.length) return { value: "PENDING", label: "Source not yet approved" };
  return { value: "MISSING", label: "No source coverage" };
}

export function LearningPathPanel({ c }: { c: Curriculum }) {
  const draft = c.status === "DRAFT";
  const [objective, setObjective] = useState<CurriculumSubtopicDef | null>(null);
  const [editing, setEditing] = useState<CurriculumTopicDef[] | null>(null);
  return (
    <section className="panel" aria-labelledby="h-path">
      <div className="panel-head">
        <div>
          <h2 id="h-path">Learning path</h2>
          <p className="small muted">What employees must learn. Source headings are material, not curriculum IDs.</p>
        </div>
        {draft && c.topics.length > 0 && (
          <button className="btn btn-small" onClick={() => setEditing(c.topics)}>
            Edit path
          </button>
        )}
      </div>
      {c.topics.length === 0 ? (
        <div className="empty-inline">
          <p className="small muted">No learning path yet. Add topics yourself, or upload a source and propose a draft path from its H2/H3 outline.</p>
          {draft && (
            <button className="btn btn-small" onClick={() => setEditing([])}>
              Add topics
            </button>
          )}
        </div>
      ) : (
        <ol className="path-tree">
          {c.topics.map((t, ti) => (
            <li key={t.topic_id}>
              <h3>
                <span className="path-num">{ti + 1}</span> {t.name}
              </h3>
              <ol>
                {t.subtopics.map((s, si) => {
                  const cov = coverage(c, s.subtopic_id);
                  const hasObjective = Boolean(s.objective?.description && s.objective.assessment_criteria);
                  return (
                    <li key={s.subtopic_id} className="path-sub">
                      <span className="path-num path-num-small">
                        {ti + 1}.{si + 1}
                      </span>
                      <span className="stack-s" style={{ gap: 4 }}>
                        <b>{s.name}</b>
                        <span className="small muted">{hasObjective ? `Objective: ${s.objective!.description}` : "Objective and assessment criteria needed before publication"}</span>
                        <span className="row">
                          <Status value={hasObjective ? "COMPLETED" : "MISSING"} label={hasObjective ? "Objective reviewed" : "Objective missing"} />
                          <Status value={cov.value} label={cov.label} />
                        </span>
                      </span>
                      {draft && (
                        <button className="link-btn" onClick={() => setObjective(s)} aria-label={`${hasObjective ? "Edit" : "Add"} objective for ${s.name}`}>
                          {hasObjective ? "Edit objective" : "Add objective"}
                        </button>
                      )}
                    </li>
                  );
                })}
              </ol>
            </li>
          ))}
        </ol>
      )}
      <ObjectiveDialog c={c} subtopic={objective} onClose={() => setObjective(null)} />
      <PathDialog c={c} initial={editing} title={c.topics.length ? "Edit learning path" : "Add topics"} onClose={() => setEditing(null)} />
    </section>
  );
}
