# OPS-SOP-001: Deployment and rollback reporting

| Document control | Value |
| --- | --- |
| Organization | Acme Infrastructure (synthetic demo organization) |
| Version | 1.2 |
| Document owner | Morgan Lee, synthetic fixture reviewer |
| Status | `APPROVED` / `CURRENT` in the Acme demo workspace (synthetic approval, product owner 2026-10-16) |
| Previous version | OPS-SOP-001 v1.1; retained as approved but superseded history |
| Scope | Choosing the current approved procedure; reporting a deployment; deciding on and reporting a rollback |
| Related documents | OPS-RB-007 v1.0 *Incident and maintenance runbook* (payment API timeouts, network latency, database maintenance) |
| Exclusions | Real hostnames, credentials, configuration values, deployment tooling commands and change approvals |

> **Synthetic test procedure.** This document is fictional. It describes how an Acme platform team reports deployments and rollbacks in the WorkWeave demo. It contains no real system names or settings and does not authorize a production change. Changes need the approval path in the team's change process.

## 1. Fundamentals

This procedure keeps three things apart during deployment work: **which instruction is currently approved, what is actually known about the change, and who must decide before production is touched.** A familiar old runbook, a colleague's memory or a similar past incident is not a substitute for the current approved procedure and real evidence.

### 1. Introduction

#### 1.1 What this procedure is for

Use this procedure when you prepare a deployment, report what a deployment did, decide whether to roll back, or hand deployment work to another shift. It is a **reporting and decision procedure**: it says what to check, what to record and who decides. It does not give deployment commands or settings; those live in the service's own approved runbook.

#### 1.2 Find the current approved version

1. Open the document library and search by the document code (OPS-SOP-001, OPS-RB-007), not by a title you remember.
2. Use only the version marked **approved** and **current**. Older versions stay visible as history so you can see what changed, but they are not instructions.
3. If you are working from a printed or saved copy, check its version against the library before you rely on it. A copy without a version is treated as unknown.
4. Note the code and version you used in the work item, for example "OPS-SOP-001 v1.2".

#### 1.3 When the source is missing or conflicting

If no current approved version exists, or two sources disagree, stop at that point. Record what you searched for and what you found, keep both references, and ask the document owner or the shift lead which instruction applies. Do not merge two procedures into your own version, and do not use an older version because it "always worked".

#### 1.4 Roles

- **Engineer:** prepares and runs the change, records evidence, reports results.
- **Shift lead:** reviews the plan, decides on go or stop when evidence is unclear, approves a rollback within the change process.
- **Change approver:** approves the change window before anything starts.
- **Document owner:** answers questions about which procedure applies.

### 2. Deployment Process

#### 2.1 Before the deployment

1. Confirm the change is approved in the change process, with its window, scope and rollback plan.
2. Write down the checks you will use to judge success (for example error rate and latency on the service dashboard) and their normal values **before** you deploy, so you can compare after.
3. Tell the affected teams the window and expected impact.

If the change is not approved, the work is **blocked** until it is. Mark it blocked in the incident system with what you are waiting for.

#### 2.2 Label every statement

Every statement in a deployment report carries one label:

| Label | Meaning | Example |
| --- | --- | --- |
| **Verified** | You checked it yourself in the system of record, with a time and source | "Error rate 0.2% on the payment API dashboard, 14:00–14:30" |
| **Reported** | Someone told you; not yet checked | "Partner says checkout is slow" |
| **Unknown** | Not established yet | "Cause of the 14:05 spike: unknown" |

Do not upgrade a reported fact to verified because it sounds likely, and do not write a cause until it is verified.

#### 2.3 During and right after the deployment

Record each step's result as you go. Compare the success checks with the values you wrote down before. If a check fails or a value moves outside its normal range, stop at the agreed point; do not try new fixes in production that are not in the plan.

#### 2.4 Reporting the outcome

A deployment report names: the change and its approval reference, the work item, the procedure version used, each check with its before and after values (verified), anything reported by others (reported), and what is still unknown. Post it in the incident system and tell your team in the Work Companion. Your message in the Work Companion is a report, not the system of record: the work item's status changes only in the incident system.

#### 2.5 History is not evidence

An earlier incident can tell you where to look, never what happened this time. "Last month's timeout was the gateway certificate" is a lead to check, not a cause. Write it as a lead and verify it before it appears in a report as the explanation.

### 3. Rollback

#### 3.1 When to consider a rollback

Consider a rollback when a success check fails after a deployment, when customers are affected and the change lines up in time with the problem, or when the shift lead asks for it. A change that lines up in time is still only a **lead** until the evidence after the rollback confirms it.

#### 3.2 Who decides

The engineer proposes; the shift lead decides within the change process. Before proposing, state:

1. The current work item and the procedure version you are following.
2. What is verified (the failing check, its values, the time range).
3. What is missing (for example, no data yet from the gateway provider).
4. The rollback the approved plan describes.

If the plan has no rollback for this change, do not invent one. Escalate to the shift lead and the change approver with the evidence and wait for a decision.

#### 3.3 After a rollback

Watch the same success checks for a full traffic cycle agreed with the shift lead and record the before and after values. A single successful test request is not enough. If the checks recover, record the rollback as **verified effective**; the root cause stays **unknown** until it is investigated.

#### 3.4 Reporting a rollback

Add a rollback note to the work item in the incident system: what was rolled back and when, who approved it, the evidence before and after, what is still unknown and the follow-ups. Tell your team and the next shift in the handover. Do not close the incident until the incident system shows it resolved.

## 2. Reference aids

### A. Deployment report checklist

- [ ] Change approval reference and window recorded.
- [ ] Procedure code and version recorded (for example OPS-SOP-001 v1.2).
- [ ] Success checks with before and after values, each labelled verified.
- [ ] Reports from others labelled reported.
- [ ] Unknowns listed, with who can answer them.
- [ ] Status updated in the incident system, not only in chat.

### B. Rollback proposal template

| Field | What to write |
| --- | --- |
| Work item | Incident or activity ID and title |
| Procedure | Code and version followed |
| Verified | Failing check, values, time range, dashboard |
| Reported | What others told you, and who |
| Unknown | What is missing and who can provide it |
| Proposed rollback | The rollback in the approved plan, or "no rollback in plan" |
| Decision | Shift lead's decision and time |
