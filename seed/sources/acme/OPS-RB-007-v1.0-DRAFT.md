# OPS-RB-007: Incident and maintenance runbook

| Document control | Value |
| --- | --- |
| Organization | Acme Infrastructure (synthetic demo organization) |
| Version | 1.0 — synthetic draft for owner review |
| Document owner | Morgan Lee, synthetic fixture reviewer |
| Status | Draft; intended as `APPROVED` / `CURRENT` in the Acme test workspace after owner review |
| Related documents | OPS-SOP-001 v1.1 *Deployment and rollback reporting* (approved sources, reported vs verified facts) |
| Related work | INC-203 (payment API timeout), INC-221 (network latency), ACT-101 (production database maintenance) |
| Related competencies | Payment gateway; Incident response; Network diagnostics; Database operations; Maintenance procedures |
| Exclusions | Real hostnames, credentials, configuration values and change approvals |

> **Synthetic test runbook.** This document is fictional. It describes how an Acme platform team works incidents and maintenance in the WorkWeave demo. It contains no real system names or settings and does not authorize a production change. Changes need the approval path in the team's change process.

## 1. Payment API timeouts

This topic applies to incidents where payment requests time out, such as **INC-203**.

### 1. Assess the impact

#### 1.1 Confirm what is failing

1. Open the incident in the Acme incident system and note when timeouts started and which requests are affected.
2. Check the payment API's dashboards for error rate and latency since the start time. Record what you see as **verified** with the dashboard and time range.
3. Note customer or partner reports separately as **reported**.

#### 1.2 Decide the severity

If payments are failing for most customers, follow the incident response process for a major incident and tell the shift lead immediately. Otherwise keep working the incident at its current priority.

### 2. Investigate the cause

#### 2.1 Check recent changes first

List deployments and configuration changes to the payment API and its gateway in the window before the timeouts started (OPS-SOP-001 v1.1, *Deployment Process*). A change that lines up in time is a **lead to check**, not a confirmed cause.

#### 2.2 Check the gateway and its dependencies

1. Compare gateway timeouts with the payment provider's status and response times.
2. Check connection limits and retries between the API and the gateway.
3. Record each check with its result: confirmed, ruled out, or unknown.

If a change is the likely cause and a rollback is available, follow OPS-SOP-001 v1.1, *Rollback*, including who must approve it.

### 3. Verify and close

#### 3.1 Prove the fix

After a fix or rollback, watch the error rate and latency for a full traffic cycle agreed with the shift lead. Record the before and after values with the dashboard reference. A single successful test transaction is not enough to close the incident.

#### 3.2 Resolve in the incident system

The incident's real status lives in the Acme incident system. Add a resolution note (cause if known, fix, verification, follow-ups), then resolve it there. Tell your team in the Work Companion what you did; your report does not close the incident, and it stays on your list until the incident system shows it resolved.

## 2. Network latency incidents

This topic applies to incidents about slow network paths between services, such as **INC-221**.

### 1. Gather diagnostic evidence

#### 1.1 Measure before changing anything

1. Identify the affected path: which services, which direction, since when.
2. Collect latency and packet-loss measurements for the path from the approved monitoring tools, with time ranges.
3. Compare with the same path's normal baseline.

#### 1.2 When the evidence isn't available

If the approved diagnostic data cannot be collected (for example, a monitoring gap or missing access), the incident is **blocked**. Mark it blocked in the incident system with what is missing and who can provide it. Do not substitute a guess about the network for missing measurements.

### 2. Act on the evidence

#### 2.1 Narrow down and hand off

Use the measurements to narrow the problem to a segment, then hand it to the owner of that segment with the evidence attached. Record the handoff in the incident.

#### 2.2 Close the incident

Once latency is back within its baseline and stays there, resolve the incident in the incident system with the measurements attached, and tell your team in the Work Companion.

## 3. Database maintenance windows

This topic applies to planned maintenance on production databases, such as **ACT-101**.

### 1. Before the window

#### 1.1 Confirm the approved window

1. Confirm the maintenance window is approved through the change process, with its start and end time, before doing anything.
2. Check that a current backup exists and that someone has verified it can be restored.
3. Tell affected teams the time and expected impact.

If the window is not approved, the activity is **blocked** until it is.

#### 1.2 Prepare the steps

Write the planned steps, the check after each step, and the point at which you will stop and roll back if a check fails. Get the shift lead to review the plan.

### 2. During and after the window

#### 2.1 Run the plan

Follow the plan step by step and record each step's result as you go. If a check fails, stop at the agreed point and roll back; do not improvise new steps in production.

#### 2.2 Close the activity

After the window, confirm the service is healthy, record the outcome and any follow-ups, then resolve the activity in the incident system and tell your team in the Work Companion.
