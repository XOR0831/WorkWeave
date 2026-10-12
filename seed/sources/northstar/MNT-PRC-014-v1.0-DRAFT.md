# MNT-PRC-014: Machine inspection and work-record checks

| Document control | Value |
| --- | --- |
| Organization | Northstar Manufacturing (synthetic demo organization) |
| Version | 1.0 — synthetic draft for owner review |
| Document owner | Morgan Lee, synthetic fixture reviewer |
| Status | Draft; intended as `APPROVED` / `CURRENT` in the Northstar test workspace after owner review |
| Related documents | SOP-001 v3.4 *Calibration and evidence handling* (how to choose the current source and label evidence) |
| Related work | Ticket #829 (Machine #14 inspection), Ticket #910 (Machine #22 document check), Ticket #492 (historical Machine #14 incident) |
| Related competencies | Procedure control; Evidence reporting; Document review |
| Exclusions | Machine settings, vibration or torque limits, repair instructions, and permission to operate or isolate equipment |

> **Synthetic test procedure.** This document is fictional. It describes how a Northstar maintenance team organizes inspection and record-checking work in the WorkWeave demo; it does not contain real machine values or authorize physical work. Acceptance limits, isolation steps and repair actions come only from the machine's own controlled manual and the site's safety process. If those cannot be verified, stop and ask an authorized reviewer.

## 1. Vibration inspection tickets

This topic applies to inspection tickets raised after a reported abnormal vibration, such as **Ticket #829 on Machine #14**. It covers preparing the inspection, recording what was observed, and closing the ticket correctly. It does not define how to inspect a specific machine; the machine's controlled manual does.

### 1. Prepare the inspection

#### 1.1 Confirm the ticket and asset

1. Open the ticket in the Northstar ticket system and confirm the asset ID, location and the reported symptom. For Ticket #829 that is Machine #14 with a *reported* vibration; the cause is **unknown**.
2. Check the ticket's history. Steps already recorded as complete by an earlier shift are *reported* until you confirm them; do not repeat or skip a step only because an earlier note says so.
3. Note any related historical tickets. Ticket #492 recorded a loose mounting assembly on Machine #14 in an **earlier** incident. Treat it as history: it can suggest what to look at, but it does not establish today's cause (SOP-001 v3.4, *Separate history from evidence*).

#### 1.2 Find the controlled instruction

Locate the current approved inspection instruction for the machine model using SOP-001 v3.4, *Find the current procedure*. Record its document code, version and section in the ticket before starting. If no current instruction can be found, the ticket is **blocked**: mark it blocked in the ticket system with what you searched, and tell your shift lead.

#### 1.3 Make the work safe to start

Follow the site's isolation and permit process exactly as the controlled instruction and your authorization allow. This procedure does not describe isolation steps. If you are not authorized for a step, stop and ask the shift lead to reassign or support the ticket.

### 2. Record the inspection

#### 2.1 Write observations, not conclusions

Record each observation with what you checked, how, and the result, using the evidence labels from SOP-001 v3.4:

| Label | Example for Ticket #829 |
| --- | --- |
| Verified | "Mounting bolts on Machine #14 checked against the manual's torque sequence; all within the manual's limits." |
| Reported | "Night shift reported the vibration started after the 02:00 restart." |
| Historical | "Ticket #492 found a loose mounting assembly in an earlier incident." |
| Unknown | "Cause of today's vibration not yet established." |

Write the limit you compared against by citing the manual section, not by copying a number from memory.

#### 2.2 When the cause is still unknown

If the inspection does not establish the cause, say so plainly. Record what was ruled out, what remains, and the next step that needs a decision (for example, a specialist inspection). Keep the ticket **in progress** or mark it **blocked** with the reason; do not resolve a ticket whose cause is still unknown unless the controlled instruction allows closing on a completed inspection.

### 3. Close the ticket

#### 3.1 Resolve in the ticket system, then tell your team

The ticket's real status lives in the Northstar ticket system. When the inspection is complete under the controlled instruction:

1. Add a work note with the observations, the source used (document code, version, section) and any open questions.
2. Resolve the ticket in the ticket system.
3. Tell your team in the Work Companion what you did. Your report in the Companion does not close the ticket; WorkWeave matches it with the ticket system and the item leaves your list once the ticket shows as resolved.

If you report "done" in the Companion before resolving the ticket, the item stays on your list at lower priority until the ticket system catches up.

#### 3.2 Handing over an unfinished inspection

At the end of a shift, record exactly which steps were completed and verified, which were only reported, and what the next person must do first. The next shift should be able to continue from the ticket alone.

## 2. Document reference checks

This topic applies to tickets that ask for a work record's document reference to be confirmed, such as **Ticket #910 on Machine #22**.

### 1. Confirm the current reference

#### 1.1 Compare the record with the controlled registry

1. Open the work record and note the document code and version it cites.
2. Look the code up in the controlled document registry. Confirm the version is **approved and current**, not superseded or draft (SOP-001 v3.4, *Source-selection checklist*).
3. If the cited version is current, add a work note: "Reference confirmed: [code] v[version], current on [date]." Then resolve the ticket in the ticket system.

#### 1.2 What counts as confirmed

A reference is confirmed only by the controlled registry. A colleague's memory, a printed copy, or a file name containing a version number is *reported* information until checked.

### 2. Resolve a reference mismatch

#### 2.1 The record cites an old or unknown version

If the record cites a superseded version, or a document the registry does not contain:

1. Do not edit the historical record to make it look current. Add a work note with the cited reference, the current version found, and the date.
2. Ask the document owner (for SOP-001, Morgan Lee) whether work done under the old version needs review.
3. Keep the ticket **in progress** until the owner answers, or mark it **blocked** if nothing can continue without the answer.

#### 2.2 Two current entries disagree

If two documents both appear current and conflict, record both references and escalate to the document owner. This is a document-control gap, not something to resolve by choosing the more familiar text.
