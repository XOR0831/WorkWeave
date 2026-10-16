# BPO-PRC-004: Billing disputes and support-team follow-ups

| Document control | Value |
| --- | --- |
| Organization | Harbor Support (synthetic demo organization) |
| Version | 1.0 |
| Document owner | Ravi Patel, synthetic fixture reviewer |
| Status | `APPROVED` / `CURRENT` in the Harbor demo workspace (synthetic approval, product owner 2026-10-16) |
| Related documents | BPO-SOP-001 v1.1 *Customer account escalation* (approved sources, reported vs verified facts, private data) |
| Related work | CASE-104 (billing clarification), ACT-105 (account escalation refresher) |
| Related competencies | Account escalation; Customer privacy; Case documentation |
| Exclusions | Refund amounts, billing system configuration, and any authority to change a customer's charges |

> **Synthetic test procedure.** This document is fictional. It describes how a Harbor support queue handles billing-clarification cases and team follow-ups in the WorkWeave demo. It does not define real refund rules or authorize changing a customer's account. Decisions about money stay with the authorized billing reviewer.

## 1. Billing dispute cases

This topic applies to cases where a customer disputes an amount, such as **CASE-104**. The goal is a clear, verified record and the right decision-maker, not a guess about whose fault the charge is.

### 1. Verify before you discuss the account

#### 1.1 Confirm identity and access

1. Confirm the caller is an authorized contact on the account using the queue's identity checks. If they are not, do not discuss charges; record the attempt.
2. Share only what the customer needs for this case. Do not read out other charges, payment details or notes from unrelated cases (BPO-SOP-001 v1.1, *Escalate without exposing private data*).

#### 1.2 Record the dispute as reported

Write the customer's account of the problem in their terms, labelled as **reported**: the amount disputed, the date, and why they think it is wrong. Do not write "billing error" or "overcharge" until it is verified; for CASE-104 the fault is **not confirmed**.

### 2. Establish the facts

#### 2.1 Compare against the account record

1. Find the charge in the account record and note its reference, date and description.
2. Compare it with the customer's plan or agreement as recorded in the approved account guide.
3. Record what matches and what does not, each labelled **verified** (checked in the record) or **unknown** (not established).

#### 2.2 Ask for what is missing

If something cannot be verified from the record (for example, a promised discount that is not on the account), ask the customer for what they have, such as a reference number or message, and record it as reported evidence. Keep the case **in progress** while you wait, or mark it **blocked** in the case system with what you are waiting for.

### 3. Resolve or escalate

#### 3.1 Decide who can resolve it

- If the record shows the charge is correct, explain it to the customer with the reference and resolve the case.
- If the record shows a mismatch, you do not change the charge yourself. Escalate to the authorized billing reviewer with the case ID, the verified facts, the reported facts and what is still unknown.

#### 3.2 Close the case in the case system

The case's real status lives in the Harbor case system. Add a final note with the outcome and the sources used, then resolve the case there. Tell your team in the Work Companion what you did; your report does not close the case, and the item stays on your list until the case system shows it resolved.

## 2. Support-team follow-ups

This topic applies to internal activities for the support queue, such as **ACT-105**, the account escalation refresher.

### 1. Confirm a scheduled refresher

#### 1.1 Settle the time and audience

1. Confirm the session time with the trainer and the shift lead, and check it does not leave the queue understaffed.
2. List who must attend and who can join optionally. Record the confirmed time in the activity.

#### 1.2 Prepare the material

Use the current approved escalation guide (BPO-SOP-001 v1.1) as the reference. Do not use an older copy someone saved locally. If the guide is about to change, ask the document owner which version to teach.

### 2. Close the activity

#### 2.1 Record the outcome

After the session, note who attended and any questions that need the document owner's answer. Resolve the activity in the case system and tell your team in the Work Companion.
