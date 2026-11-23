# Prism agent audit, Phase 1: executive summary

Date: 2026-11-22. Scope: Chief of Staff, QA Analyst, AI Researcher, Sales Outreach, plus shared infrastructure. Phase 1 only: no source, schema, setting or dependency was changed and no fix is proposed. Stop point: awaiting your review before Phase 2.

Files: [01 Chief of Staff](01-chief-of-staff.md), [02 QA Analyst](02-qa-analyst.md), [03 AI Researcher](03-ai-researcher.md), [04 Sales Outreach](04-sales-outreach.md), [05 shared infrastructure](05-shared-infrastructure.md), [06 API and runtime failures](06-api-and-runtime-failures.md), [07 model and cost](07-model-and-cost-analysis.md), [08 bug register](08-consolidated-bug-register.csv), [09 test matrix](09-test-execution-matrix.md), `evidence/` (raw suite output, drift output, run metrics, live run artefacts, read-only scripts).

## Overall status

**All four Prisms were run live** after you supplied the operator token. In its first pass this audit was blocked by the 401; the live phase then ran each Prism once on its audit task (the Researcher twice), plus follow-ups. **None produced a correct, verifiable result.** Two limits remain: I had **no OneClarity password**, so authenticated QA is blocked and the repeated-question loop could not be reproduced live (it needs the accept-login path); and fault-injection scenarios were not run.

The token was used only as a per-command environment variable and is in no file or report.

## Primary task outcome

| Prism | Ran live | Result |
|---|---|---|
| Chief of Staff | Yes | Teams review completed (129 messages, citations valid, confidence 0.28). **No CEO draft.** 26% of messages outside the 7-day window. Follow-up restarts retrieval |
| QA Analyst | Yes, public site only | Partial run: 6 cases (1 fail, 5 skipped), no screenshots, no bug drafted. Login declined, no repeat. Authenticated tests blocked |
| AI Researcher | Yes, twice | **0 developments** both times; stopped at 18 and 10 of 120 turns; follow-up invented three unsourced trends |
| Sales Outreach | Yes | 10 real company names from memory; **CSV corrupt** (header split by a comma, no aligned rows); no decision-makers; placeholder messages; `partially_verified` labels without browsing |

## Counts

| Measure | Value |
|---|---|
| Matrix rows planned | 225 |
| Passed | 43 |
| Failed (defect confirmed by live run, data or code) | 64 |
| Blocked | 25 (no credential, or nothing to grade because the Prism delivered nothing) |
| Not executed | 44 (no fault-injection fixture, UI not driven) |
| Analysed only (no live pass/fail claim) | 49 |
| Existing suites, distinct tests executed | 610 (Prism 444, swarm 78, e2e 88); 14 failed, all in browser e2e |
| Tests collected | Prism 444, e2e 90, swarm 78 (matches documented 90 and 78) |
| Live runs | 4 swarm tasks (8 swarm runs including approval resumes: Researcher 2 tasks, Sales 1, QA 1) and 1 Chief of Staff job |
| Measured cost of the audit | about 0.12 USD (calculated/estimated, not billing); ceiling 12 USD |

## Bugs: 27 in [08](08-consolidated-bug-register.csv) (25 confirmed, 2 suspected)

| Severity | Count | IDs |
|---|---|---|
| P0 | 1 | PRISM-CORE-001 |
| P1 | 9 | CORE-002, QA-001, SALES-001, SALES-002, SALES-003, COS-001, COS-004, AIR-002, AIR-003 |
| P2 | 11 | CORE-003, -004, -005, -008 (suspected), -010, QA-003, COS-003, COS-005, COS-006, AIR-001 (suspected), AIR-004 |
| P3 | 6 | CORE-006, -007, -009, QA-002, QA-004, COS-002 |

### Systemic (more than one Prism)

- **CORE-001 (P0):** a password typed into an `ask_manager` answer is stored in plaintext, returned to the model and shown in Prism chat (2 of 17 recorded answers; values not read). Rotate if real.
- **CORE-002 (P1):** every tool error reaches the model as "An error occurred while running the tool. Please try again." `sign_in` failed 9 of 9 recorded calls.
- **Agents declare success without evidence (AIR-002, SALES-001/003, QA-002):** run status `succeeded` and `task_outcome: passed` do not reflect what was verified. Seen on the Researcher, Sales and QA Prisms.
- **CORE-003:** 86 of 88 older artifacts are not where the API looks (new runs download fine).
- **CORE-004, -005, -006, -007, -008, -009, -010:** stale approval; 14 React e2e failures; Alembic drift; duplicate Prisms and a missing grant; link-origin check reads the wrong argument; pause runs shown as `succeeded`; any Prism thread can start a Teams review.

### Single Prism

- **QA Analyst:** QA-001 repeated question (P1); QA-003 site API blocked in the browser; QA-004 evidence gaps.
- **Sales Outreach:** SALES-001/002/003 (P1).
- **Chief of Staff:** COS-001 review failures (29% historical), COS-004 no CEO draft, COS-005 date window, COS-006 follow-up.
- **AI Researcher:** AIR-002/003 (P1), AIR-004.

## The repeated-question defect (QA-001)

`sign_in` calls the browser tool with `ref`, but the installed Playwright MCP 0.0.83 requires `target`, so each call fails; the SDK hides the reason behind a fixed message; the model, with a login already "stored", asks the manager or calls `request_login` again; Prism asks for username and password every time; the manager sometimes types credentials into chat (CORE-001). 4 of 4 recorded login chains repeated. **Live:** declining the login did not repeat (n=1). The accept path needs a credential I did not have, so the `ref` versus `target` mismatch is from package inspection and recorded runs, not a live reproduction. Detail in [02](02-qa-analyst.md).

## Key model and agent weaknesses

Stopping early (Researcher, 10 to 18 of 120 turns); answering from model memory when a source is blocked, then reporting success (Sales, Researcher follow-up); asking the manager questions the task already answers; writing CSV by hand without validating it; marking unperformed work `pass`. Several are orchestration or tool defects first (masked errors, no search tool, no CSV writer), so they are not only prompt problems ([07](07-model-and-cost-analysis.md)).

## Cost and latency

Live phase about 0.123 USD (swarm calculated 0.116, Prism estimated 0.008). Longest run: QA 285 s with 1.48 M input tokens. Recorded history before the live phase: 61 swarm runs, 0.7083 USD calculated. Failed Prism-side calls mostly record no usage, so total spend is understated.

## Evidence gaps

- Authenticated QA and the accept-login path live; SSE, refresh, restart and recovery drills; the dashboard UI itself (API only).
- Whether the Chief of Staff summary is accurate (not graded against message bodies).
- Whether the 14 e2e failures are product defects or test drift.
- The real exception behind each `sign_in` and `save_file` failure (not logged).
- Whether the exposed credential-like text is real.

## Issues needing your review before Phase 2

1. **Credential for authenticated QA.** Provide the OneClarity login through the secure card if you want QA-001 reproduced live.
2. **CORE-001.** Decide whether to rotate the affected test credentials now.
3. **Uncommitted fix in the working tree** (four Chief of Staff files; [01](01-chief-of-staff.md#working-tree-caveat)). Keep, revert or commit? The live Chief of Staff review ran with it present.
4. **Is "no CEO draft" a defect or a separate user step (COS-004)?**
5. **Canonical Prisms.** Each tested role has a duplicate plus legacy agents.
6. **e2e failures:** triage first, since the React dashboard has no green browser run.

## Method and side effects

- Databases were read with `SET TRANSACTION READ ONLY`. Suites used the disposable `_test` and scratch-schema databases.
- **Data this audit created in the working database:** 4 swarm tasks and 8 runs including resumes (Researcher 2, Sales 1, QA 1), their plans/approvals/chat messages, 2 follow-up chat exchanges, Chief of Staff job `fc97bcff` (left `waiting_for_approval`, nothing to send), and two cancelled stray jobs (`e10373dc` from my wrong endpoint, `9f513970` the follow-up).
- No `.env` or credential store was read. No Teams message, outreach or external form was sent. Nothing was committed.
