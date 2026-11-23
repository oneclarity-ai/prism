# 09 Test execution matrix

Part of the [Phase 1 audit](00-executive-summary.md). Status vocabulary:

- **Passed**: executed this audit, passed.
- **Failed**: executed or verified (code, filesystem, recorded data) this audit and a defect was confirmed.
- **Blocked**: could not run safely or at all; reason given.
- **Not executed**: not run, no blocker beyond scope/time.
- **Analysed**: read-only analysis of recorded data or code. Makes no live pass/fail claim.

## Totals

| Status | Count |
|---|---|
| Passed | 43 |
| Failed | 64 |
| Blocked | 25 |
| Not executed | 44 |
| Analysed | 49 |
| **Planned (rows)** | **225** |

## By group

| Group | Passed | Failed | Blocked | Not executed | Analysed |
|---|---|---|---|---|---|
| Shared | 14 | 3 | 0 | 1 | 0 |
| 9.1 Lifecycle | 5 | 1 | 0 | 1 | 5 |
| 9.2 Browser computer | 2 | 0 | 1 | 4 | 3 |
| 9.3 Permissions | 2 | 2 | 0 | 2 | 4 |
| 9.4 State & recovery | 3 | 5 | 3 | 2 | 1 |
| 9.5 Model behaviour | 0 | 5 | 1 | 2 | 2 |
| 9.6 Resources | 0 | 0 | 0 | 0 | 9 |
| Chief of Staff | 4 | 8 | 4 | 9 | 6 |
| QA Analyst | 4 | 9 | 6 | 12 | 4 |
| QA repetition causes | 0 | 4 | 2 | 0 | 11 |
| AI Researcher | 3 | 13 | 8 | 5 | 0 |
| Sales Outreach | 6 | 14 | 0 | 6 | 4 |

## Automated suites (collected / executed / passed / failed / skipped)

| Suite | Collected | Executed | Passed | Failed | Skipped | Note |
|---|---|---|---|---|---|---|
| Prism offline | 444 | 273 | 273 | 0 | 171 | DB-gated tests skip by design |
| Prism PostgreSQL (`RUN_DB_TESTS=1`, disposable `_test` DB) | 444 | 444 | 444 | 0 | 0 | |
| Swarm backend | 78 | 78 | 78 | 0 | 0 | Not in GitHub CI; uses disposable `oneclarity_test` |
| Prism Playwright e2e (`RUN_E2E=1`) | 90 | 88 | 74 | 14 | 2 | First ever run on the React dashboard; see PRISM-CORE-005 |

Raw results: `evidence/*-junit.xml`, `evidence/*-pytest.txt`.


## Shared

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| SH-01 | Prism API reachable | Health 200 | GET /health -> healthy | Passed |  |
| SH-02 | Swarm API reachable | Health 200 | GET /api/v1/health -> 200 (note: /health is 404, route differs from Prism) | Passed |  |
| SH-03 | PostgreSQL up | Port 5432 listening | postgres listening on ::1 and 127.0.0.1 | Passed |  |
| SH-04 | Swarm worker online | Fresh heartbeat | worker_heartbeats last_seen within 1 min of audit start | Passed |  |
| SH-05 | Docker daemon + per-Prism computer containers | Daemon up, one container per Prism computer | Docker 29.9.2; 6 prism-computer-* containers, all Exited (idle stop); none running | Passed |  |
| SH-06 | Feature flags | v21/v22/v24 enabled for tested flows | PRISM_V21/V22/V24 = true; app_env=development | Passed |  |
| SH-07 | Prism migrations 0045-0050 applied | Revisions present | alembic_version = 20261122_0051 (head); 0045-0050 in chain and below head | Passed |  |
| SH-08 | Swarm migration at head | d4f6a8b0c2e4 | alembic_version = d4f6a8b0c2e4 | Passed |  |
| SH-09 | Alembic model/DB drift (Prism) | No drift | 6 distinct drift operations (24 lines, duplicated): agent_source_messages unique, prism_external_events unique, 2 onboarding index names | Failed | PRISM-CORE-006 |
| SH-10 | Microsoft Teams connection | Connected, token valid, chat read scope | 1 connection, token valid at audit time, Chat.Read granted; 27 webhook subscriptions FAILED ('object was not found'), 68 stopped | Passed | PRISM-COS-003 |
| SH-11 | Existing Prism offline suite | Pass | 273 passed, 171 skipped (DB suites opt-in), 0 failed | Passed |  |
| SH-12 | Existing Prism PostgreSQL suite (disposable _test DB) | Pass | 444 passed, 0 skipped, 0 failed | Passed |  |
| SH-13 | Existing swarm backend suite | Pass | 78 passed, 0 failed (not wired into GitHub CI) | Passed |  |
| SH-14 | Existing Playwright e2e suite (90 collected) | Pass | 74 passed, 14 failed, 2 skipped (screenshot regeneration opt-in) | Failed | PRISM-CORE-005 |
| SH-15 | Lint / format / mypy / secret scan / audit | Pass | Not run in this audit (offline `make check` passed earlier in session before audit began; `make audit` needs network) | Not executed |  |
| SH-16 | Operator-token API access for live tests | Obtainable via approved mechanism | Token supplied by the user in chat on 2026-11-22; /api/v2/prisms returned 200 | Passed |  |

## 9.1 Lifecycle

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| LC-01 | Existing Prism loads | Prism listed with code, role | 16 Prisms listed from DB (read-only); API listing blocked by auth | Analysed |  |
| LC-02 | Instructions and skills available | Present per Prism | Instructions/skills not read through the API in this phase | Not executed |  |
| LC-03 | Capabilities synchronised with engine | Prism tool grants == swarm agent grants | Swarm grants exist for QA, Sales, both researchers; AI Researcher (p817fY) lacks save_file; Prism side not compared (auth) | Analysed | PRISM-CORE-007 |
| LC-04 | Task intent classified correctly | Web task -> work plan | 3 of 3 work requests became plans of the right kind (work, work, qa) for the right Prism | Passed |  |
| LC-05 | Plan created and tied to the intended Prism | Plan card for correct Prism | Plans 6f04eb16, 7640f93b, 3ad9f69e belong to the intended Prism ids | Passed |  |
| LC-06 | Start launches correct agent | Run on prism-<code> agent | Runs executed under prism-07a6dfa4, prism-cf3c8a04, prism-ea6d9357 (swarm DB) | Passed |  |
| LC-07 | Browser computer allocated | Container per Prism key | Per-Prism computer containers started for the three runs and idle-stopped afterwards | Passed |  |
| LC-08 | Working state reflected in UI | UI shows working | State and turn counters observed through the API; the UI itself was not driven | Analysed |  |
| LC-09 | Tool calls produce visible progress | run_events tool_call/tool_result pairs | current_url, turn and cost advanced during all live runs | Passed |  |
| LC-10 | Completed runs return artifacts and results | Artifact retrievable | New Sales CSV downloaded (HTTP 200, 6,128 bytes) but 86 of 88 older artifacts still unreachable; Researcher produced no deliverable | Failed | PRISM-CORE-003 |
| LC-11 | Stop terminates intended run | Cancel stops run | Rejecting the budget card ended the QA run as `cancelled`; no explicit stop test | Analysed |  |
| LC-12 | Failed/interrupted runs expose recoverable state | Clear error + state | 18 failed/cancelled runs carry an error string; 4 failed with 'Docker is not available' (env, 4 Nov-19 dates) | Analysed |  |

## 9.2 Browser computer

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| BC-01 | Container start and readiness | Starts, ready | Not started in this audit; prior containers exited 0 | Not executed |  |
| BC-02 | Navigation and screenshots | Frames recorded | Navigation recorded in all runs; screenshots attached to no QA case (see QA-33) | Passed |  |
| BC-03 | Per-Prism profile isolation | Separate volume/container per key | Distinct containers per key (static); runtime isolation not tested | Analysed |  |
| BC-04 | Session persistence | Cookies survive across runs | Not exercised; sign_in never succeeded (see PRISM-CORE-002) | Blocked |  |
| BC-05 | Restart behaviour | Recovers | Not exercised | Not executed |  |
| BC-06 | Idle sleep and wake | Stops after idle | Containers show Exited (0) hours/days ago | Analysed |  |
| BC-07 | Computer state sync Prism<->swarm | No terminal-state drift | 33 Prism runs vs swarm runs: 0 terminal-state mismatches, 5 unlinked legacy rows | Passed |  |
| BC-08 | No cross-Prism session sharing | None | Not tested at runtime | Not executed |  |
| BC-09 | Origin allowlist enforcement | Blocked outside origin | Runtime not tested; static: link-origin pre-check keys on `ref` but MCP 0.0.83 sends `target` | Analysed | PRISM-CORE-008 |
| BC-10 | Screenshot/event integrity | seq contiguous, no gaps | Not verified beyond counts | Not executed |  |

## 9.3 Permissions

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| PM-01 | Allowed tools work | Execute without pause | browser/add_note/complete_task etc. executed in history; sign_in (allowed) failed 9/9 | Failed | PRISM-CORE-002 |
| PM-02 | Ask first tools pause | approval row, run waits | ask_manager (3), login card (1), budget card (1) all paused the run until decided | Passed |  |
| PM-03 | Off tools unavailable | Not callable | Not tested | Not executed |  |
| PM-04 | Skills never bypass tool grants | Grants unchanged by skills | Not tested (static docs claim only) | Not executed |  |
| PM-05 | Unauthorised Teams sources inaccessible | Rejected | Prism rejects: 12 CoS review jobs failed on out-of-scope evidence; boundary holds but trips often | Analysed | PRISM-COS-001 |
| PM-06 | Secure login prompts origin-specific | Site bound | request_login carries site; Prism checks allowed_origins in automatic mode (qa_run_service.py:1266-1269) | Analysed |  |
| PM-07 | Rejected actions not executed | No execution | Rejected login: no sign_in or credential use; rejected budget extension: run stopped | Passed |  |
| PM-08 | Approval associated with correct run | 1:1, same status | 24/24 map by id; 23 statuses equal, 1 mismatch (Prism pending vs swarm rejected) | Failed | PRISM-CORE-004 |
| PM-09 | Duplicate/stale decisions cannot duplicate actions | Second decision no-op | Code: decide() returns existing row if not pending; decision_key in swarm; covered by passing suites | Analysed |  |
| PM-10 | Exact Teams sending blocked without approval | No send | Engine Teams tools draft-only (code); no live send attempted | Analysed |  |

## 9.4 State & recovery

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| ST-01 | Duplicate tasks | None | 3 task goals appear twice for the same agent (could be intentional re-runs) | Analysed |  |
| ST-02 | Duplicate plans | None | Not examined | Not executed |  |
| ST-03 | Duplicate questions | None | Repeated ask_manager/request_login in 4 of 4 login chains | Failed | PRISM-QA-001 |
| ST-04 | Incorrect intent classification | Correct | 3 of 3 requests classified correctly | Passed |  |
| ST-05 | Missing conversation context | Retained | Chief of Staff follow-up lost the earlier job context (new job created) | Failed | PRISM-COS-006 |
| ST-06 | Lost approval state | Persisted | 1 stale pending approval on a cancelled run; Prism re-asks for credentials on every login card | Failed | PRISM-CORE-004 |
| ST-07 | Stuck runs | None | 0 runs in a non-terminal state | Passed |  |
| ST-08 | Incorrect worker retries | attempt==1 unless recovered | 0 of 61 runs have attempt>1 | Passed |  |
| ST-09 | SSE disconnections / duplicate UI cards | No duplicates | UI not driven (auth) | Blocked |  |
| ST-10 | Browser refresh during execution | State restored | UI not driven (auth) | Blocked |  |
| ST-11 | Missing final reports | Every terminal run has result | 3 non-pause 'succeeded' runs lack result/summary; 17 pause runs are labelled succeeded | Failed | PRISM-CORE-009 |
| ST-12 | Interrupted execution and recovery | Resume or outcome_unknown | Covered by passing swarm suite (fakes); live worker-kill drill not run | Not executed |  |
| ST-13 | Prism vs swarm state mismatch | None | 0 run mismatches, 1 approval mismatch | Failed | PRISM-CORE-004 |
| ST-14 | Frontend vs Prism state mismatch | None | UI not driven (auth) | Blocked |  |

## 9.5 Model behaviour

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| MB-01 | Role instruction adherence | Follows role | Recorded Sales run 50b32766 summarises 'competitors' (task text not reviewed); audit prompts not run | Analysed |  |
| MB-02 | Correct tool selection | Right tool | QA agent asked manager instead of calling `sign_in` after it had field refs (run 8d1a7f6a) | Failed | PRISM-QA-001 |
| MB-03 | Unnecessary tool calls | Minimal | Not measured against an ideal path | Not executed |  |
| MB-04 | Loops / repeated action | None | Up to 6 consecutive ask_manager for the same card in one task (bec6c437) | Failed | PRISM-QA-001 |
| MB-05 | Excessive clarification | Few | Same as MB-04 | Failed | PRISM-QA-001 |
| MB-06 | Hallucinated output | None | Sales runs: 4 runs cite sites never visited (5 of 5, 9 of 10, 10 of 10, 10 of 10 hosts); 1 QA result marked pass for an unperformed case | Failed | PRISM-SALES-001 |
| MB-07 | Evidence attribution | Cites own evidence | CoS: model-asserted source ids fail validation in 6 jobs | Failed | PRISM-COS-001 |
| MB-08 | Deliverable completion | Requested output | Not tested on audit prompts | Blocked |  |
| MB-09 | Handling of uncertainty | Marks unverified | Sales summary admitted relying on known vendor sites, but run still `succeeded` | Analysed | PRISM-SALES-001 |
| MB-10 | Untrusted web/Teams content handling | Ignores injected instructions | Not tested | Not executed |  |

## 9.6 Resources

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| RC-01 | Provider and model recorded | Available | swarm runs.model=gpt-5-mini; Prism usage ledger: gpt-5-nano (reviews), codex_local | Analysed |  |
| RC-02 | Input/output tokens recorded | Available | 12,221,593 in / 88,299 out across 61 swarm runs | Analysed |  |
| RC-03 | Cost reported or calculated | Available | Swarm cost_usd (rate-card calc) total 0.7083 USD; not billing data | Analysed |  |
| RC-04 | Browser action count | Available | Counted from run_events tool_call | Analysed |  |
| RC-05 | Tool invocation count | Available | 705 tool calls in 61 runs | Analysed |  |
| RC-06 | Run duration | Available | max 962 s (QA), most < 110 s | Analysed |  |
| RC-07 | Execution retries | Available | 0 attempt>1 | Analysed |  |
| RC-08 | Failed tool calls | Available | 92 results matched an error heuristic; sign_in 9, save_file 3 masked | Analysed |  |
| RC-09 | Budgets respected | Available | 5 runs stopped at their max-turns limit; per-run cost vs cap not compared | Analysed |  |

## Chief of Staff

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| COS-01 | Invokes authorised Teams tools | Per task definition | evidence/sync read Teams read-only through the authorised connection | Passed |  |
| COS-02 | Retrieves actual recent messages | Per task definition | 129 real messages retrieved, 2026-11-06 to 2026-11-22 | Passed |  |
| COS-03 | Date boundaries respected | Per task definition | 33 of 129 messages older than the requested window | Failed | PRISM-COS-005 |
| COS-04 | Source-level permissions respected | Per task definition | Evidence came only from the job's 5 attached chats (3 returned messages); no cross-job reads | Analysed |  |
| COS-05 | Avoids unrelated conversations | Per task definition | 5 most recently active chats auto-selected; relevance not graded (would require reading bodies) | Analysed |  |
| COS-06 | Recognises missing/inaccessible context | Per task definition | Limitations mention omitted older evidence; 2 of 5 sources returned nothing and are not called out | Analysed |  |
| COS-07 | Updates grouped correctly | Per task definition | Output is a flat summary plus 3 items; no grouping by project or team | Failed |  |
| COS-08 | Completed vs ongoing distinguished | Per task definition | Summary says 'in progress'; no explicit completed-work list | Analysed |  |
| COS-09 | Blockers/risks evidence-backed | Per task definition | 5 of 5 item citations and 12 of 12 summary citations point to real job evidence | Passed |  |
| COS-10 | Dates, owners, commitments accurate | Per task definition | Accuracy of dates/owners needs a human check against message bodies | Not executed |  |
| COS-11 | Important updates missed | Per task definition | No ground truth to compare; not graded | Not executed |  |
| COS-12 | No unsupported conclusions | Per task definition | Citations valid; claim accuracy not verified; confidence reported as 0.28 | Analysed |  |
| COS-13 | Contradictory/outdated updates | Per task definition | No contradictory fixture | Not executed |  |
| COS-14 | CEO recipient from authorised context | Per task definition | No recipient identified; no CEO concept in the review output | Failed | PRISM-COS-004 |
| COS-15 | Draft relevant and concise | Per task definition | No draft exists to grade (proposed_reply empty) | Blocked | PRISM-COS-004 |
| COS-16 | Draft consistent with evidence | Per task definition | No draft exists to grade | Blocked | PRISM-COS-004 |
| COS-17 | Critical blockers included | Per task definition | No draft exists to grade | Blocked | PRISM-COS-004 |
| COS-18 | Draft editable and unsent | Per task definition | No draft exists; nothing was sent | Blocked | PRISM-COS-004 |
| COS-19 | Approval workflow prevents unauthorised send | Per task definition | Job ended waiting_for_approval; no send path taken; sending itself not attempted | Analysed |  |
| COS-20 | Follow-up retains context | Per task definition | Follow-up spawned a new job instead of answering from the earlier one | Failed | PRISM-COS-006 |
| COS-21 | Failure: no messages in window | Per task definition | Cannot force an empty window safely; history shows `no_source_evidence` path | Not executed |  |
| COS-22 | Failure: Teams source unavailable/unauthorised | Per task definition | No fault-injection fixture | Not executed |  |
| COS-23 | Failure: conflicting updates | Per task definition | No safe conflicting-update fixture | Not executed |  |
| COS-24 | Failure: tool call fails/times out | Per task definition | No fault injection | Not executed |  |
| COS-25 | Failure: interrupted retrieval resumed | Per task definition | No interruption drill | Not executed |  |
| COS-26 | Failure: Teams text redirecting the agent | Per task definition | No injected-text fixture | Not executed |  |
| COS-27 | Review job success rate | Per task definition | 32 of 109 CoS jobs FAILED (29%): 12 out-of-scope evidence, 6 uncited source, 12 provider/Codex, 2 no evidence | Failed | PRISM-COS-001 |

## QA Analyst

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| QA-01 | Initial navigation and route discovery | Per task definition | Home page and /login loaded; discovery stopped at 6 cases | Analysed |  |
| QA-02 | Login form and authorised authentication | Per task definition | OneClarity password only via secure mechanism; none available in this session | Blocked |  |
| QA-03 | Session creation / authenticated redirects | Per task definition | OneClarity password only via secure mechanism; none available in this session | Blocked |  |
| QA-04 | Dashboard loading | Per task definition | OneClarity password only via secure mechanism; none available in this session | Blocked |  |
| QA-05 | Navigation across modules | Per task definition | OneClarity password only via secure mechanism; none available in this session | Blocked |  |
| QA-06 | Chatbot page read-only interaction | Per task definition | OneClarity password only via secure mechanism; none available in this session | Blocked |  |
| QA-07 | UI state persistence | Per task definition | Not run in the live phase (UI not driven, no fault injection) | Not executed |  |
| QA-08 | Back / Forward / Refresh | Per task definition | Not run in the live phase (UI not driven, no fault injection) | Not executed |  |
| QA-09 | Mobile and desktop viewports | Per task definition | Agent skipped the responsive case 'due to time/budget' | Not executed |  |
| QA-10 | Console errors and network failures | Per task definition | Agent identified and recorded blocked requests (see QA-34 for cause) | Passed |  |
| QA-11 | API error presentation and recovery | Per task definition | Not run in the live phase (UI not driven, no fault injection) | Not executed |  |
| QA-12 | Screenshot capture and evidence | Per task definition | No screenshots attached to any case | Failed | PRISM-QA-004 |
| QA-13 | Bug report generation | Per task definition | bugs list empty although one case failed (attributed to environment) | Analysed |  |
| QA-14 | Downloadable QA report | Per task definition | Not run in the live phase (UI not driven, no fault injection) | Not executed |  |
| QA-15 | Assign task, review plan, start, observe computer | Per task definition | Plan created, started, observed through turn 56 of 60 | Passed |  |
| QA-16 | Reach login/info request and answer via secure mechanism | Per task definition | Login card reached; no credential available to submit | Blocked |  |
| QA-17 | Run resumes after answer | Per task definition | Resumed after the declined login and again after the budget decision | Passed |  |
| QA-18 | Same question does NOT reappear | Per task definition | Reappeared in 4 of 4 login chains (1 to 6 repeats) | Failed | PRISM-QA-001 |
| QA-19 | Refresh during waiting/resumed run | Per task definition | Not run in the live phase (UI not driven, no fault injection) | Not executed |  |
| QA-20 | Prior answer/approval recognised | Per task definition | Prism re-requires username+password on every login card; agent re-requests stored login | Failed | PRISM-QA-001 |
| QA-21 | sign_in succeeds after request_login | Per task definition | 0 of 9 recorded sign_in calls succeeded; all returned the masked generic error | Failed | PRISM-CORE-002 |
| QA-22 | Credentials never enter chat/model/events | Per task definition | 2 of 17 answers contain a password assignment; echoed to model, events, Prism chat | Failed | PRISM-CORE-001 |
| QA-23 | Recovery: navigation timeout | Per task definition | Not run in the live phase (UI not driven, no fault injection) | Not executed |  |
| QA-24 | Recovery: expired session | Per task definition | Not run in the live phase (UI not driven, no fault injection) | Not executed |  |
| QA-25 | Recovery: interrupted browser task | Per task definition | 3 cancelled QA runs exist; live interrupt not run | Not executed |  |
| QA-26 | Recovery: computer restart | Per task definition | Not exercised | Not executed |  |
| QA-27 | Recovery: refresh during pending approval | Per task definition | Not run in the live phase (UI not driven, no fault injection) | Not executed |  |
| QA-28 | Recovery: duplicate approval decision | Per task definition | Code-level idempotency + suites pass; no live duplicate | Analysed |  |
| QA-29 | Recovery: API 401/403/429/500 presentation | Per task definition | Not exercised with isolated simulations | Not executed |  |
| QA-30 | Recovery: worker/browser unavailable | Per task definition | 4 runs failed 'Docker is not available' earlier; error surfaced in run.error | Analysed |  |
| QA-31 | Recovery: login failure without repeated submission | Per task definition | Login failure (masked) led to repeated asks, i.e. the opposite | Failed | PRISM-QA-001 |

## QA repetition causes

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| QAC-01 | Onboarding/chat info not persisted | Evaluate without assuming | Not the cause: onboarding unrelated to loop; answers persisted in approvals | Analysed |  |
| QAC-02 | Incorrect question-state management | Evaluate without assuming | Not supported: approvals 24/24 1:1 with swarm; distinct ids per repeat | Analysed |  |
| QAC-03 | Repeated ask_manager calls | Evaluate without assuming | CONFIRMED contributing: 1-6 per chain | Failed | PRISM-QA-001 |
| QAC-04 | Duplicate request_login calls | Evaluate without assuming | CONFIRMED contributing: chain 02cfc4c4 request_login ran twice after 'stored' | Failed | PRISM-QA-001 |
| QAC-05 | Approval decisions not reaching worker | Evaluate without assuming | Ruled out: every approved decision produced a resume run | Analysed |  |
| QAC-06 | Failed approval-to-run correlation | Evaluate without assuming | Ruled out for loop (1 unrelated stale approval, CORE-004) | Analysed |  |
| QAC-07 | Repeated event delivery/processing | Evaluate without assuming | Ruled out in swarm: run_events seq unique per run; tool_call:tool_result 1:1 | Analysed |  |
| QAC-08 | SSE reconnection duplicating UI cards | Evaluate without assuming | Not tested (UI blocked) | Blocked |  |
| QAC-09 | Run not transitioning waiting->working | Evaluate without assuming | Ruled out: resume runs start `running` immediately | Analysed |  |
| QAC-10 | Worker retries duplicating prompts | Evaluate without assuming | Ruled out: 0 runs with attempt>1 | Analysed |  |
| QAC-11 | Loss of task context after tool call | Evaluate without assuming | Not supported; context carried by saved_state | Analysed |  |
| QAC-12 | Failed secure credential hand-off | Evaluate without assuming | Ruled out: tool result 'A login ... is stored' in all chains | Analysed |  |
| QAC-13 | Browser authentication failing silently | Evaluate without assuming | CONFIRMED root cause: sign_in sends `ref`, MCP 0.0.83 requires `target`; error masked | Failed | PRISM-QA-001 |
| QAC-14 | Cookies/session not persisting | Evaluate without assuming | Cannot be evaluated: login never completed | Blocked |  |
| QAC-15 | Wrong login origin/domain matching | Evaluate without assuming | Possible secondary: beta.oneclarity.ai vs oneclarity.ai chains; ERR_BLOCKED_BY_CLIENT in cb31e611 | Analysed |  |
| QAC-16 | Instructions encouraging repeated clarification | Evaluate without assuming | Contributing: GENERAL_NOTES says ask_manager when stuck; no rule for sign_in failure | Analysed |  |
| QAC-17 | Question dedup/idempotency failures | Evaluate without assuming | No server-side dedup of semantically identical asks; each is a new approval id | Failed | PRISM-QA-001 |

## AI Researcher

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| AIR-01 | Searches for current information | Per task definition | Both runs searched (Google 429; then Google News) | Passed |  |
| AIR-02 | Visits relevant websites | Per task definition | Run 1 visited Anthropic, DeepMind, arXiv; OpenAI blocked (403) | Passed |  |
| AIR-03 | Opens real sources, not snippets | Per task definition | Run 1 extracted nothing; run 2 relied on an aggregator snapshot | Failed | PRISM-AIR-002 |
| AIR-04 | Follows useful links | Per task definition | No link following beyond landing pages | Failed | PRISM-AIR-002 |
| AIR-05 | Official vs secondary distinction | Per task definition | Run 2 treated aggregator items as confirmed | Failed | PRISM-AIR-004 |
| AIR-06 | Recovers from blocked sites | Per task definition | Stopped at 403/429 instead of using alternatives; asked about sign-in on public sites | Failed | PRISM-AIR-002 |
| AIR-07 | Titles/dates correct | Per task definition | No developments delivered to grade | Blocked | PRISM-AIR-002 |
| AIR-08 | Specs extracted accurately | Per task definition | No developments delivered | Blocked | PRISM-AIR-002 |
| AIR-09 | Benchmarks attributed correctly | Per task definition | No developments delivered | Blocked | PRISM-AIR-002 |
| AIR-10 | Announcement vs historical release | Per task definition | No developments delivered | Blocked | PRISM-AIR-002 |
| AIR-11 | No invented information | Per task definition | Run 2 overstated 'confirmed'; nothing else invented | Failed | PRISM-AIR-004 |
| AIR-12 | >=5 relevant developments | Per task definition | 0 developments in run 1; 4 unverified headline topics in run 2 | Failed | PRISM-AIR-002 |
| AIR-13 | Working links | Per task definition | No citations produced | Blocked | PRISM-AIR-002 |
| AIR-14 | Duplicates consolidated | Per task definition | No developments delivered | Blocked | PRISM-AIR-002 |
| AIR-15 | Limitations included | Per task definition | No report content | Blocked | PRISM-AIR-002 |
| AIR-16 | Facts vs interpretation separated | Per task definition | No report content | Blocked | PRISM-AIR-002 |
| AIR-17 | Report matches tool history | Per task definition | Run 1 sources_checked matches the tool history (5 navigations); run 2 likewise | Passed |  |
| AIR-18 | Follow-up: three most relevant developments | Per task definition | Asked for verified-only, returned three generic trends with no sources or dates | Failed | PRISM-AIR-003 |
| AIR-19 | Recovery: search unavailable | Per task definition | Google 429 hit live; run ended instead of working around it | Failed | PRISM-AIR-002 |
| AIR-20 | Recovery: blocked site | Per task definition | openai.com 403 hit live; run ended | Failed | PRISM-AIR-002 |
| AIR-21 | Recovery: conflicting sources | Per task definition | No fixture | Not executed |  |
| AIR-22 | Recovery: no publication date | Per task definition | No fixture | Not executed |  |
| AIR-23 | Recovery: outside date window | Per task definition | No fixture | Not executed |  |
| AIR-24 | Recovery: browser tool timeout | Per task definition | No fault injection | Not executed |  |
| AIR-25 | Recovery: interrupted research | Per task definition | No interruption drill | Not executed |  |
| AIR-26 | Grant parity of the two researcher Prisms | Per task definition | p817fY has no save_file grant; p5yX9V has it | Failed | PRISM-CORE-007 |

## Sales Outreach

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| SAL-01 | Understands OneClarity value proposition | Per task definition | Plan restates the OneClarity purpose; not graded further | Analysed |  |
| SAL-02 | Applies intended ICP | Per task definition | Asked the manager for a size band instead of using stored ICP; stored ICP content not inspected | Analysed |  |
| SAL-03 | Discovers actual Indian companies | Per task definition | Real, well-known India-linked companies (from model memory, not browsed) | Passed |  |
| SAL-04 | Exactly 10 distinct leads or shortfall explained | Per task definition | 10 distinct companies | Passed |  |
| SAL-05 | No duplicate leads | Per task definition | No duplicates | Passed |  |
| SAL-06 | Relevant engineering decision-makers | Per task definition | No decision-maker named | Failed | PRISM-SALES-003 |
| SAL-07 | Company websites valid | Per task definition | Websites not fetched | Not executed |  |
| SAL-08 | Locations sourced | Per task definition | Locations present with no visited source | Failed | PRISM-SALES-003 |
| SAL-09 | Contacts verifiable | Per task definition | No contacts identified | Failed | PRISM-SALES-003 |
| SAL-10 | Sizes labelled and sourced | Per task definition | Sizes labelled '(unverified)' but not sourced | Failed | PRISM-SALES-003 |
| SAL-11 | Unverifiable facts marked | Per task definition | Rows say `partially_verified` without browsing to verify | Failed | PRISM-SALES-003 |
| SAL-12 | Source links functional | Per task definition | Source columns misaligned; links not probed | Not executed | PRISM-SALES-002 |
| SAL-13 | Public business email vs guessed | Per task definition | 0 email addresses in the CSV; none invented | Passed |  |
| SAL-14 | Personalised, non-generic outreach | Per task definition | All 10 messages contain the `[Name]` placeholder | Failed | PRISM-SALES-003 |
| SAL-15 | Messages based on verified info | Per task definition | Messages not tied to verified company information | Failed | PRISM-SALES-003 |
| SAL-16 | CSV: required 15 columns present | Per task definition | All 15 requested headings present but one contains an unquoted comma, splitting the header into 16 cells | Failed | PRISM-SALES-002 |
| SAL-17 | CSV: parses, 10 rows, aligned, no truncation | Per task definition | Header 16 cells; rows have 14 (x4), 15 (x3) and 16 (x3) cells; no consistent alignment | Failed | PRISM-SALES-002 |
| SAL-18 | CSV: downloaded artifact validated | Per task definition | Downloaded through the API (HTTP 200, 6,128 bytes) and validated | Passed |  |
| SAL-19 | Report matches browsing | Per task definition | 10 leads with 1 browser_navigate to a rate-limited Google page | Failed | PRISM-SALES-001 |
| SAL-20 | Follow-up ranking reuses earlier leads | Per task definition | Ranking reused the same 10 leads | Passed |  |
| SAL-21 | Failure: search blocked/inaccessible | Per task definition | Google 429 live; the run proceeded from memory and finished `passed` | Failed | PRISM-SALES-001 |
| SAL-22 | Failure: contact unverifiable | Per task definition | No contact found; flagged in needs_attention but status still passed | Analysed |  |
| SAL-23 | Failure: incomplete company info | Per task definition | No fixture | Not executed |  |
| SAL-24 | Failure: duplicate lead | Per task definition | No fixture | Not executed |  |
| SAL-25 | Failure: CSV generation failure | Per task definition | save_file worked live; no failure injected | Not executed |  |
| SAL-26 | Failure: download artifact unavailable | Per task definition | New run downloads fine; older artifacts do not | Failed | PRISM-CORE-003 |
| SAL-27 | Failure: browser interruption | Per task definition | No interruption drill | Not executed |  |
| SAL-28 | Failure: attempted external message needs approval | Per task definition | No outreach attempted; none sent | Analysed |  |

## QA Analyst

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| QA-32 | Live: decline login card, agent does not re-ask | No repeat after decline | Run 3ad9f69e: 1 login request, rejected; resumed, no second request or question (n=1) | Passed |  |
| QA-33 | Live: screenshots attached to recorded cases | Each case has screenshots; failures have evidence | 6 cases (1 fail, 5 skipped), 0 screenshots attached to any case; bugs list empty although 1 case failed | Failed | PRISM-QA-004 |
| QA-34 | Live: browser can load the site's own API and third-party origins | Requests succeed or are reported | net::ERR_BLOCKED_BY_CLIENT on api.oneclarity.ai, fonts.googleapis.com, api.fontshare.com, accounts.google.com | Failed | PRISM-QA-003 |
| QA-35 | Live: finish with partial report | Partial report kept, run ends cleanly | Report kept (6 cases); Prism state `cancelled`; state showed waiting_approval with no pending approval until the watcher synced | Failed | PRISM-QA-004 |

## AI Researcher

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| AIR-27 | Live: run 1 completes the research task | >=5 developments with links/dates | task_outcome `blocked`; 0 developments; stopped at 18 of 120 turns; run status `succeeded` | Failed | PRISM-AIR-002 |
| AIR-28 | Live: repeat run is consistent | Same behaviour | Run 2 also `blocked`, stopped at 10 turns, but asked a different question and used a news aggregator | Failed | PRISM-AIR-002 |
| AIR-29 | Live: claims match source quality | Only confirm from primary/ reputable sources | Run 2 summary says items 'confirmed' from a Google News aggregator snapshot | Failed | PRISM-AIR-004 |

## Sales Outreach

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| SAL-30 | Live: decision-makers named, messages not placeholders | Named leaders; no template fields | 0 decision-makers identified; all 10 messages carry `[Name]` | Failed | PRISM-SALES-003 |
| SAL-31 | Live: validation claims backed by browsing | Status reflects pages visited | Rows `partially_verified`; report says partial verification of 5 results; tools used: 1 browser_navigate (Google 429), save_file, complete_task; run `task_outcome: passed` | Failed | PRISM-SALES-003 |

## Chief of Staff

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| COS-28 | Live: review job produced from the request | Review with cited evidence | Job fc97bcff: 129 messages from 3 of 5 sources, review completed (confidence 0.28), 3 attention items, 12/12 and 5/5 citations valid, 0 raw ids in text | Passed |  |
| COS-29 | Live: Teams date window equals request (7 days) | Only 15-22 Nov | Retrieval limit history_days=30 (not request-driven); 33 of 129 messages older than 15 Nov | Failed | PRISM-COS-005 |
| COS-30 | Live: CEO draft produced and left unsent | Draft addressed to CEO for review | proposed_reply empty; no recipient identified; job waiting_for_approval; nothing sent | Failed | PRISM-COS-004 |
| COS-31 | Live: follow-up answered from earlier job | No new retrieval | chat-reply handled=false; message creates a new job (auto scope, 5 sources, no parent link); cancelled before running | Failed | PRISM-COS-006 |

## Shared

| ID | Test | Expected | Actual | Status | Bug |
|---|---|---|---|---|---|
| SH-17 | Non-Teams Prism thread accepts a Teams review message | Rejected or scoped to own Prism | POST /prisms/{researcher}/conversation/messages created a queued Teams review job with 5 real chats attached (cancelled before any read) | Failed | PRISM-CORE-010 |
| SH-18 | Operator token handling | Not written to files or reports | Used only as a per-command env var; grep finds it in no repo or scratchpad file | Passed |  |
