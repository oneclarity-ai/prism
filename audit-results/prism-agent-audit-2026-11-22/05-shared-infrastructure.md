# 05 Shared infrastructure

Back to [executive summary](00-executive-summary.md). Related: [02 QA](02-qa-analyst.md), [06 runtime failures](06-api-and-runtime-failures.md), [09 matrix](09-test-execution-matrix.md) (groups Shared, 9.1 to 9.6).

## Baseline (observed 2026-11-22 12:17 UTC)

| Item | Observation |
|---|---|
| Branch / tree | `monorepo`; 4 uncommitted files from a fix made **before** this audit (see [01](01-chief-of-staff.md#working-tree-caveat)); the audit changed no tracked file |
| Prism API | `:8000` healthy; `/api/v2` routes returned 401 until the user supplied the operator token, then 200 |
| Swarm API | `:8080`; `/api/v1/health` 200 (`/health` is 404) |
| PostgreSQL | listening on 5432; Prism DB at `20261122_0051` (head); swarm DB at `d4f6a8b0c2e4` (head) |
| Migrations asked about | `0045` to `0050` present in the chain and below the DB head. The DB head is `0051` (BYOK `base_url`/`api_version`), one revision beyond your list |
| Flags | `PRISM_V21/V22/V24` all true; `app_env=development`; QA caps: 150 turns, 3.0 USD, 30 minutes |
| Worker | one worker, heartbeat within 1 minute of audit start |
| Docker | daemon 29.9.2; six `prism-computer-*` containers; before the live runs all `Exited`; the three tested Prisms' containers started for their runs and idle-stopped again |
| Teams | 1 connection, token valid at audit time, `Chat.Read` granted; 27 webhook subscriptions FAILED, 68 STOPPED |
| Prisms | 16 Prisms, all `ACTIVE`; 3 role pairs duplicated (QA, Researcher, Sales) |

## Test suites

| Suite | Collected | Executed | Passed | Failed | Skipped |
|---|---|---|---|---|---|
| Prism offline | 444 | 273 | 273 | 0 | 171 |
| Prism PostgreSQL (disposable `_test` DB) | 444 | 444 | 444 | 0 | 0 |
| Swarm backend | 78 | 78 | 78 | 0 | 0 |
| Prism e2e | 90 | 88 | 74 | 14 | 2 |

The collection counts match the documented figures (90 and 78). The e2e suite had never been run on the React dashboard before this audit.



## PRISM-CORE-002 Tool exceptions are masked from the model (P1, Worker/execution runtime, Confirmed)

- **Actual:** any exception inside a `@function_tool` reaches the model as `An error occurred while running the tool. Please try again.`
- **Evidence:** swarm `run_events`: `sign_in` 9 of 9 calls, `save_file` 3 of 9, `record_test_result` 1 of 71, `get_test_login` 1. No `failure_error_function` in `openai_agents.py`; SDK `default_tool_error_function` returns the fixed string (openai-agents 0.23.1).
- **Root cause (High):** SDK default plus no per-tool error policy. The descriptive `ToolError` messages in the repo's tools are dropped.
- **Why** `sign_in` **itself fails:** see [02](02-qa-analyst.md) (`ref` versus `target`).
- **Test gap:** swarm tests use a fake browser, and the one test that mentions `ref` is a guard unit test. No test calls the real MCP schema.
- **Unverified:** the underlying exception for `save_file` failures; not logged.



## PRISM-CORE-003 Artifacts unreachable through the API (P2, Infrastructure, Confirmed by code and filesystem)

- **Actual:** `GET /api/v1/artifacts/{id}/file` resolves `Path(art.path)` against the API process directory and requires it to sit under `artifacts_dir` (`routers/runs.py:253-259`). The API runs from `apps/swarm/backend`, so the root is `backend/var/artifacts`.
- **Evidence:** of 88 artifact rows, **86 have their files only under** `backend/var/var/artifacts/...` (including 16 created since 11-19, e.g. the Sales CSVs); 2 resolve. HTTP download was **not exercised** (swarm API needs a login I do not have).
- **Probable cause (Medium):** a `var/` directory was copied one level deeper while the stored path stayed `var/artifacts/<run>/...`, likely during the monorepo move. Not confirmed.
- **Impact:** reports, CSVs and screenshots from earlier runs would show "Artifact file is missing".



## PRISM-CORE-004 Stale pending approval (P2, Prism service, Confirmed)

Prism `qa_approvals` has 1 `pending` question approval on a cancelled QA run (2026-11-03 19:16). The swarm approval with the same id is `rejected`. 23 of 24 approvals agree. Likely effect: a phantom pending card or notification count. Cause not traced (sync path on cancel).



## PRISM-CORE-005 React dashboard e2e failures (P2, Frontend/UI, failures confirmed, causes open)

14 of 90 fail (desktop and narrow variants). Clusters, with what I verified:

| Cluster | Tests | Observation |
|---|---|---|
| Theme menu focus and system preference | `test_design_system` (2) | Expected focus after keyboard open not met |
| Workspace surfaces | `test_design_system` (2) | `[data-workspace-page='approvals']` matches 2 elements (strict-mode violation). The old `index.html` also had two (lines 45 and 66), so the test may rely on visibility |
| Workspace navigation URL | `test_navigation` (3) | After a `prism:workspace-navigate` event the URL stays `/workspace` instead of `/tasks`. A forwarding listener exists at `AppProvider.tsx:375`; why it does not navigate is open |
| Create-Prism dialog | `test_prism_directory` (4) | Test waits for label "What is this Prism responsible for?". `PrismEditorDialog.tsx:393` shows "What does this Prism do?" when creating in one-step mode. Whether the old app showed that text in the same mode is not established |
| Narrow profile menu / People | `test_opencode_theme` (2), `test_people_directory` (1) | Click timeouts at narrow width |

I did not open the failing screenshots or reproduce each in a debugger. Some may be test-expectation drift, not product defects.



## PRISM-CORE-006 Alembic drift (P3, Database, Confirmed, pre-existing)

`alembic check` reports 6 distinct operations (each printed twice): unique constraint on `agent_source_messages (job_id, external_conversation_id, external_message_id)`, unique constraint on `prism_external_events (prism_id, dedupe_key)`, and two onboarding indexes (`ix_prism_onboarding_answers_session_id`, `ix_prism_onboarding_questions_session_id`). This matches [post-v2.4-changes.md §8](../../docs/releases/post-v2.4-changes.md). Not introduced by the audit; nothing was migrated. Release risk: low data risk but a guaranteed noisy `alembic check` and uncertain constraint names for future migrations. Evidence: `evidence/alembic-check-prism.txt`.



## PRISM-CORE-007 Duplicate Prisms and inconsistent grants (P3, Tool configuration, Confirmed)

- Role pairs: QA Analyst `p8fDdp` and QA Agent `pS1tWy`; AI ML Researcher `p5yX9V` and AI Researcher `p817fY`; Sales Outreach `pocA9q` and Sales Outreach Agent `pN4qxx`. Legacy swarm agents `qa-agent` and `sales-outreach-agent` also exist.
- Grants: `prism-07a6dfa4` (AI Researcher `p817fY`) has no `save_file`; `prism-17372fa4` (AI ML Researcher) does. A researcher without `save_file` cannot produce a downloadable file.
- Grants common to the three swarm-backed tested Prisms (Chief of Staff has no swarm agent): `browser`, `computer`, `sign_in` allowed; `ask_manager`, `request_login`, `confirm_action` ask first. No search tool is granted.



## PRISM-CORE-008 Link-origin pre-check keys on `ref` (P2, Worker runtime, Suspected)

`computer_mcp.py:100-104` looks up a click's destination with `self.links.get(args.get("ref"))`. The installed MCP and the model's recorded `browser_click` calls use `target`, so the lookup returns nothing and the destination check is skipped for clicks. The proxy-level `--allowed-origins` still applies. **Not run live**, so I do not know whether another layer blocks the click first. Evidence to close: a disposable local page with a cross-origin link, click via MCP, observe whether `reason()` fires.



## PRISM-CORE-009 Pause runs recorded as `succeeded` (P3, Swarm state, Confirmed)

A run that ends at an approval pause gets status `succeeded` with no result. 17 of the 20 succeeded runs with no result/summary have an approval. The other 3 have none (a true gap). Risk: any consumer that treats `succeeded` as "has a final report" misreads the chain.



## PRISM-CORE-010 Any Prism thread can start a Teams review (P2, Prism API, Confirmed; intent unverified)

`POST /api/v2/prisms/{prism_id}/conversation/messages` always creates a Teams review job. On the Researcher Prism (which should do web research) it created job `e10373dc` with `scope_mode: auto` and 5 real Teams chats attached, even though the message was a web-research request. I cancelled it while still `queued`, before evidence was read, so no Teams content was retrieved by that call. AGENTS.md calls for per-Prism privacy boundaries; whether non-Chief-of-Staff Prisms are meant to hold Teams sources is not stated in what I read. The dashboard routes web work through `/qa/plan` first, so this is reachable only by calling the endpoint directly. **My own wrong first call triggered it.**

## Other shared observations

- **Prism to swarm state:** 33 Prism runs against swarm runs: 0 terminal-state mismatches; 5 legacy rows have no swarm link.
- **Retries:** 0 of 61 swarm runs have `attempt` above 1; none stuck in a non-terminal state.
- **Environment failures:** 4 runs failed with `Docker is not available` (2 on 11-05, 1 on 11-02, 1 on 11-19). That is an environment fault, not a product defect.
- **Max-turn stops:** 5 runs ended at their turn limit; these are expected limit behaviour.
- **Not tested:** worker-kill recovery, browser restart, origin allowlist at runtime, profile isolation at runtime, SSE behaviour, Off-tool enforcement, skill/grant independence.
