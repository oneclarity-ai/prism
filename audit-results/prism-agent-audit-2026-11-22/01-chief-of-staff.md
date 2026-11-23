# 01 Chief of Staff (p9o2FW)

Back to [executive summary](00-executive-summary.md). Tests: [09 matrix](09-test-execution-matrix.md) rows COS-01..COS-27. Bugs: [08 register](08-consolidated-bug-register.csv).

**Scope note.** Run live on 2026-11-22 after the operator token was supplied, using the Teams review workflow (`evidence/sync` then `review`), the same sequence the dashboard uses. Teams access was read-only on the authorised connection. **No message was sent and no message body appears in this report.** Job: `fc97bcff`. A later follow-up job was cancelled before it ran.

- Chief of Staff uses Prism's Teams review workflow (`ConversationReviewService`), not the swarm. It has no swarm agent.

## Summary matrix

| Test case | Expected | Actual | Status | Bug |
|---|---|---|---|---|
| Teams retrieval (live) | Authorised read | 129 messages, 3 of 5 sources | Passed | n/a |
| Date window | 7 days | 30-day retrieval; 33 of 129 older | Failed | PRISM-COS-005 |
| CEO draft | Draft to CEO, unsent | none produced | Failed | PRISM-COS-004 |
| Follow-up retains context | No new retrieval | New job created | Failed | PRISM-COS-006 |
| Citation validity | Real evidence | 17 of 17 valid | Passed | n/a |
| Review jobs succeed | Most jobs complete | 40 completed, 32 failed (29%) of 109 | Failed | PRISM-COS-001 |
| Source permissions | Out-of-scope evidence rejected | Rejected: 12 jobs failed on this check | Analysed | PRISM-COS-001 |
| No relevant messages in window | Clear message | 2 jobs ended `no_source_evidence` with a readable explanation | Analysed | n/a |
| Draft unsent / approval gate | No send without approval | 25 jobs `WAITING_FOR_APPROVAL`; Teams engine tools are draft-only; nothing sent by this audit | Analysed | n/a |
| Teams connection health | Connected | Token valid, `Chat.Read` granted; 27 webhook subscriptions FAILED | Passed / Failed | PRISM-COS-003 |

## Live results (job fc97bcff)

| Measure | Value |
|---|---|
| Sources attached | 5 auto-selected chats (the most recently active); 3 returned messages |
| Evidence retrieved | 129 messages, 2026-11-06 to 2026-11-22 |
| Messages older than the requested 7 days | 33 of 129 (26%) |
| Retrieval limits | 5 sources, `history_days` 30, 50 messages per source |
| Review result | completed; confidence 0.28; 3 attention items, 1 manager question, 2 limitations |
| Citations | 12 of 12 summary and 5 of 5 item citations point to real evidence of this job |
| Raw evidence ids in prose | 0 (the working-tree fix described below is present, so I cannot attribute this) |
| CEO draft | none: `proposed_reply` is empty; no recipient identified |
| Final job state | `waiting_for_approval`, nothing sent |
| Model cost | 34,256 input / 2,824 output tokens, estimated 0.0028 USD, 12.6 s |
| Follow-up ("which blockers first, and what evidence?") | `chat-reply` handled=false; posting it creates a new job (new auto scope, 5 sources, no link to the first job) |

## PRISM-COS-004 (P1) No CEO draft, no recipient

- **Expected:** a concise draft to the CEO, from authorised context, left unsent for review.
- **Actual:** the review returns a summary, three items and a question about a deployment plan. The CEO is never identified and no draft exists. The workflow only drafts a reply to the source chat when it decides one is needed, and a separate manual proposal API (`POST /agent/jobs/{id}/proposals`) requires destination and body to be supplied.
- **Layer:** Prism service (workflow design). **Confidence:** High for what the API returned; Medium that this is a gap versus intent, because the CEO-draft flow may be meant to be a separate user step.

## PRISM-COS-005 (P2) The 7-day window is not applied

The request says "past seven days" but retrieval uses fixed limits (`history_days` 30, 5 chats). 33 of 129 messages (26%) predate 15 Nov, and the limitations text only says older evidence was "omitted by the configured retrieval bounds". The job message schema accepts only content and source ids, so a date range cannot be requested.

## PRISM-COS-006 (P2) Follow-up restarts retrieval

The follow-up does not use the first job's evidence or review. It creates a new job that would re-read Teams and call the model again. I cancelled it before it ran. This is the behaviour the audit asked to avoid ("without restarting the entire retrieval").

## Other live observations

- **Grouping:** the output is a flat summary plus three items. There is no grouping by project or team.
- **Quality not graded:** I did not compare dates, owners or commitments to message bodies, so accuracy is not asserted. Confidence 0.28 shows the model itself was unsure.
- **Left in place:** job `fc97bcff` remains `waiting_for_approval` so you can inspect it. It has no draft to approve.
- **Mistake disclosed:** my first call used `POST /prisms/{researcher}/conversation/messages`, which created a Teams review job with 5 real chats attached to the **Researcher's** thread. I cancelled it before any evidence was read ([PRISM-CORE-010](05-shared-infrastructure.md#core-010)).

## Job outcomes (history) (109 jobs, Chief of Staff threads)

| Outcome | Jobs | Cause (stored `safe_error_detail`) |
|---|---|---|
| COMPLETED | 40 | n/a |
| WAITING_FOR_APPROVAL | 25 | awaiting manager |
| CANCELLED | 9 | manager |
| QUEUED | 3 | never claimed (all 10-28) |
| FAILED rule_violation | 18 | 10 "cited evidence outside this job's authorized Teams evidence"; 6 "attributed evidence to a Teams source it did not cite"; 2 "outside the selected Teams chat" |
| FAILED external_service_error | 12 | 6 local Codex process; 5 provider response invalid/failed after retries; 1 provider timeout |
| FAILED no_source_evidence | 2 | no messages in window |

Model use recorded in `llm_usage` for `v21_conversation_review`: azure_openai `gpt-5-nano` (the smallest listed model) plus `codex_local`. Nine review calls (6 with no usage data, 3 with) and one repair call are marked `failed`.

## PRISM-COS-001 Review fails on model-asserted source ids (P1)

- **Affected Prism:** Chief of Staff `p9o2FW`. **Classification:** Prism service plus model output. **Status:** Confirmed for the "did not cite" class; Suspected for the "outside authorized evidence" class.
- **Preconditions:** a request whose scope resolves to several chats that share one display label (scope mode `auto`).
- **Reproduction (recorded):** job 2026-11-22 17:19 `teams_chat`, scope `auto`: FAILED with "An insight attributed evidence to a Teams source it did not cite". The job had 5 sources all labelled with the same person name and 48 evidence messages from one of them.
- **Expected:** a review whose citations all point at real evidence in the job is accepted.
- **Actual:** the review fails after the single repair attempt.
- **Frequency:** 6 of 109 jobs fail this way, plus 12 more on the related out-of-scope checks.
- **Mechanism (High):** the model fills a redundant `source_external_ids` list per insight; with identical labels it guessed wrong; the validator compared that list with the sources of the cited evidence and raised `RuleViolationError`.
- **Code:** `app/services/management/conversation_review_service.py`, `_annotate_source_provenance` and `_validate_grounded_result`.
- **Unverified:** the 10+2 "outside evidence" failures were not traced. They may share the cause (model-written ids) or come from real scope errors.

### Working-tree caveat (important)

Before this audit started, in the same session, I changed `conversation_review_service.py` and `build-timeline.ts` (plus tests) to fix the three symptoms in your Chief of Staff screenshot. Those four files are **uncommitted** and I did not touch them during Phase 1. Consequences:

1. The offline, integration and e2e results above ran against that working tree.
2. The database shows the failure as it happened **before** the fix. I have not re-run a failing job with the fix, so I cannot confirm it works against the live model. Retrying the failed draft would show that.
3. The fix relaxes a rule an existing test used to assert (an uncited source claim now gets replaced by the real cited sources). Say if you want it reverted before Phase 2.

## PRISM-COS-002 Presentation defects in the same screenshot (P3)

Raw evidence id pasted by the model into the summary text, and a topic separator that printed the same label five times (the same person label x5). Both were reproduced from the screenshot and the failed job's data, and both have changes in the uncommitted working tree (id scrubbing in the review service; label grouping in `build-timeline.ts`). Status: Confirmed, fix unverified live.

## PRISM-COS-003 Failed Teams webhook subscriptions (P2)

`microsoft_teams_subscriptions`: 27 FAILED with "The object was not found", 68 STOPPED. Likely deleted or expired Graph subscriptions or chats (Medium). Effect: change notifications for those conversations are not delivered; the review path itself reads on demand. Not investigated further, because it needs Graph calls.

## What is not known

- Whether the summary's dates, owners and commitments are accurate, and whether important updates were missed (not graded).
- Whether the gpt-5-nano choice explains the invalid-response and repair failures (hypothesis only).
- Behaviour with injected instructions in Teams text.
