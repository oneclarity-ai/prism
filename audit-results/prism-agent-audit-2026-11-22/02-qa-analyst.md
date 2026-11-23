# 02 QA Analyst (p8fDdp) and the repeated-question defect

Back to [executive summary](00-executive-summary.md). Tests: [09 matrix](09-test-execution-matrix.md) (rows QA-01..QA-31, QAC-01..QAC-17). Bugs: [08 register](08-consolidated-bug-register.csv).

**Scope note.** One live QA run was made on 2026-11-22 after the operator token was supplied (run `3ad9f69e`, public site only, platform defaults of 60 turns and US$1). **I had no OneClarity password and did not obtain one, so I rejected the login card and the authenticated tests are Blocked.** That means the repeated-question loop could **not** be reproduced live: its accept-the-login path needs a credential. The explanation of that defect below still rests on recorded runs plus code and package inspection. Live artefact: `evidence/live/qa-run.json`.

Prism identifiers: Prism `p8fDdp` (QA Analyst), swarm agent `prism-ea6d9357`. A second Prism, `pS1tWy` "QA Agent", and the legacy swarm agent `qa-agent` also exist (see [PRISM-CORE-007](05-shared-infrastructure.md#core-007)). I audited the one named "QA Analyst".

## Live run 3ad9f69e (public site, login declined)

| Measure | Value |
|---|---|
| Turns / time / cost | 56 of 60 / 285 s / 0.0805 USD (calculated); 1.48 M input tokens |
| Approvals raised | 1 login card (rejected), 1 budget extension (rejected) |
| Repeats after declining the login | 0 (n=1) |
| Final state | `cancelled`, partial report kept |
| Cases recorded | 6: 1 fail, 0 pass, 5 skipped; **0 screenshots attached**; bugs list empty |
| Failed case | "No failing network requests": `ERR_BLOCKED_BY_CLIENT` on `api.oneclarity.ai` (cookie-consent endpoints), `fonts.googleapis.com`, `api.fontshare.com`, `accounts.google.com/gsi/client` |
| Skipped | responsive layouts ("not tested due to time/budget"), demo sandbox ("Manager declined more testing"), and others |

Observations:

- **Declined login handled cleanly in this one attempt.** The agent did not ask again and carried on with public pages. One attempt is not a frequency.
- **The browser computer blocks the site's own API.** The run's notes attribute it to the test environment. The same `ERR_BLOCKED_BY_CLIENT` appears in recorded task `cb31e611` when `/login` would not load. If `api.oneclarity.ai` is blocked, the login and consent flows cannot work even with a correct `sign_in` ([PRISM-QA-003](#prism-qa-003-p2)). The runbook documents that allowed origins are exact, so this may be by design, but it makes the login test unreliable. Not confirmed as a cause of the earlier loops.
- **"Finish with partial report" is shown as `cancelled`.** Rejecting the budget card ended the run as `cancelled` (swarm: "Testing stopped by the manager at the approved limit. Partial results were kept."). Right after the decision the Prism state still read `waiting_approval` with no pending approval until the watcher synced (under about a minute).
- **Low coverage:** with 60 turns, 5 of 6 planned cases ended skipped. Coverage is bounded by the cap, as designed, and reported as partial.

<a id="prism-qa-003-p2"></a>
### PRISM-QA-003 (P2) Computer blocks the site's own API origin
Browser computer, configuration. Confirmed block in 1 of 1 live run and 1 recorded task. Impact on login suspected, not shown.

### PRISM-QA-004 (P3) Evidence and state gaps
No screenshots on cases, no bug drafted for the failed case, and a partial finish recorded as `cancelled`. Prism service plus agent behaviour. 1 of 1 live run.

## Summary matrix

| Test case | Expected | Actual | Status | Bug |
|---|---|---|---|---|
| Login once, run resumes, no repeat | One login card, then `sign_in` works | Login stored, then agent asked again in 4 of 4 chains | Failed | PRISM-QA-001 |
| `sign_in` after `request_login` | Form filled and submitted | 0 of 9 recorded `sign_in` calls succeeded; each returned `An error occurred while running the tool. Please try again.` | Failed | PRISM-CORE-002 |
| Credentials stay out of chat, model and events | Never | 2 of 17 `ask_manager` answers match a password-assignment pattern; echoed to model, events and Prism chat | Failed | PRISM-CORE-001 |
| Prior approval recognised | Stored login reused | Prism demands username and password again on every login card | Failed | PRISM-QA-001 |
| Live public QA of oneclarity.ai | Executed | Run 3ad9f69e: 6 cases, 1 fail, 5 skipped, 0 screenshots | Failed | PRISM-QA-004 |
| Authenticated QA (login, dashboard, chatbot, settings) | Executed | No credential available | Blocked | n/a |
| Decline login, no repeat | No repeat | 1 request, 0 repeats | Passed | n/a |
| Secure-card hand-off | Secret stored | Tool result `A login for https://oneclarity.ai is stored` in all 5 `request_login` calls | Analysed | n/a |

## The execution sequence behind the repeated question

Task `02cfc4c4`, 2026-11-21 (UTC). One task, five swarm runs. Each approval pause ends a run and a new resume run continues it.

| Time | Run | Event |
|---|---|---|
| 12:23:50 | 1d69e0a9 | Run starts. 12:24:05: `request_site_access` approval raised. |
| 12:39:52 | 1d69e0a9 | Run ends (15 min waiting for the manager). |
| 12:40:20 | 05fc0845 | `request_login` approval for `https://oneclarity.ai`. Approved. |
| 12:40:34 | 8d1a7f6a | Resumed. `request_login` result: *A login for https://oneclarity.ai is stored. Use sign_in with the refs of the username and password fields.* |
| 12:40:37 to 12:41:04 | 8d1a7f6a | Agent clicks the Login link, snapshots the page and records three test results. Its notes say it captured the username and password refs "for potential sign_in". The third note says submission was not performed yet marks the case `pass` (PRISM-QA-002). **It never calls `sign_in`.** |
| 12:41:08 | 8d1a7f6a | `ask_manager`: "Approve use of stored credentials to sign in...? (I will use sign_in API; no credentials shown in chat)". The manager had approved the login card 48 seconds earlier. |
| 12:41:08 | n/a | The manager's answer (44 characters) contains the substring `pass`. |
| 12:41:36 | c746858d | `request_login` approval **again**: "Confirm secure approval to use stored login via sign_in API (I will not use credentials provided in chat)". Approved. |
| 12:41:50 | 1624c7ee | `request_login` result: stored. |
| 12:41:54 and 12:41:57 | 1624c7ee | `sign_in` (refs e1023 and e1029) fails twice with the generic masked error. |
| 12:42:01 | 1624c7ee | `browser_click` on a stale ref fails (`Ref e996 not found`). The run continues without authentication and calls `complete_task` at 12:42:24 and again at 12:42:45. |

Three older chains show the same shape, in worse form:

| Task (date UTC) | Sequence of approvals | Notes |
|---|---|---|
| bec6c437 (11-03 02:13 to 02:20) | `request_login`, then `ask_manager` x6 | Four `sign_in` calls fail with the masked error. The questions repeat "Please provide the secure login card ... (do NOT paste credentials in the chat)". Four of the six manager answers contain secret-related words. |
| cb31e611 (11-03 19:15 to 19:16) | `request_login`, `ask_manager`, `ask_manager` (rejected) | Site load blocked (`ERR_BLOCKED_BY_CLIENT`). Agent asks whether the manager already submitted the login. |
| 88ad53f7 (11-03 19:28 to 19:29) | `request_login`, `ask_manager` | Target was `beta.oneclarity.ai`. Three `sign_in` calls fail. The manager answered "alreayd prvided" (already provided). |

**Frequency: 4 of 4 chains that used `request_login` repeated a question or login request (1 to 6 repeats).** Each repeat has its own approval id (24 Prism approvals map 1:1 to 24 swarm approvals), so this is not duplicate delivery of one approval.

## Root cause, ordered by earliest incorrect event

1. **`sign_in` cannot work against the installed browser tool (earliest, High confidence).** `apps/swarm/backend/app/runtime/openai_agents.py:598-606` calls `browser_type` with `{"element", "ref", "text"}`. The pinned `@playwright/mcp@0.0.83` (`app/core/config.py:55`, same version inside `mcr.microsoft.com/playwright/mcp:latest`) defines `typeSchema = elementSchema.extend(...)` where `elementSchema` requires `target` and has no `ref`. I read this in the installed package's `coreBundle.js`. The model's own `browser_click` events in the database also use `target`. Every `sign_in` call therefore fails schema validation. Evidence: 9 of 9 recorded `sign_in` calls failed and none ever succeeded. **Not reproduced live.** A live check is listed under "Unverified" below.
2. **The error is hidden from the model.** `@function_tool` with no `failure_error_function` uses the SDK's `default_tool_error_function`, which returns the fixed string `An error occurred while running the tool. Please try again.` (verified in openai-agents 0.23.1; `openai_agents.py` sets none). The detailed `ToolError` messages written in `sign_in` ("Approve site access before signing in.", "The current page does not match the approved login site.") are never shown to the model either. The real exception is not in `worker.log` (119 lines from 02:08 to 10:04 on 11-22), so the per-call exception text cannot be recovered. See [PRISM-CORE-002](05-shared-infrastructure.md#core-002).
3. **The agent has no recovery rule for a failed `sign_in`.** `GENERAL_NOTES` (lines 110-125) says to call `ask_manager` when stuck. With a vague "try again" error and a login that is "stored", the model asks the manager, or calls `request_login` again. Chain 02cfc4c4 also shows the model choosing not to call `sign_in` at all in run 8d1a7f6a.
4. **Prism makes each repeat expensive.** `qa_run_service.py:1262-1265` requires a username and password on **every** login approval and never checks whether a login for that site is already stored, so each repeated `request_login` re-prompts for credentials.
5. **Nothing stops credentials landing in chat.** The question card accepts up to 1000 free-text characters (`qa_run_service.py:1257-1261`). `ask_manager` returns `The manager answered: {t.mask(answer)}` (`openai_agents.py:527-532`), and `mask()` (`tools.py:404-408`) only replaces values already stored as secrets. A password typed into chat before it is stored is not masked. See [PRISM-CORE-001](#core-001).

Layer attribution: primary **Worker/execution runtime** (1, 2); contributing **Agent reasoning** (3), **Prism service** (4, 5).

## Candidate causes you listed (verdicts)

| Candidate | Verdict | Basis |
|---|---|---|
| Onboarding or chat information not persisted | Ruled out | Answers persisted in swarm approvals |
| Incorrect question-state management | Not supported | 24/24 approvals correlate; distinct ids per repeat |
| Repeated `ask_manager` calls | **Confirmed contributing** | 1 to 6 per chain |
| Duplicate `request_login` calls | **Confirmed contributing** | Second call in 02cfc4c4 after "stored" |
| Approval decisions not reaching worker | Ruled out | Every approved decision produced a resume run |
| Failed approval-to-run correlation | Ruled out for the loop | One unrelated stale approval ([CORE-004](05-shared-infrastructure.md#core-004)) |
| Repeated event delivery | Ruled out (swarm side) | `seq` unique per run; 705 tool calls vs 705 results |
| SSE reconnect duplicating cards | **Not tested** | UI not driven |
| Run not moving waiting to working | Ruled out | Resume runs start `running` |
| Worker retries duplicating prompts | Ruled out | 0 of 61 runs have `attempt` above 1 |
| Loss of context after a tool call | Not supported | State carried by `saved_state` |
| Failed secure credential hand-off | Ruled out | "is stored" in all 5 calls |
| Browser authentication failing silently | **Confirmed root cause** | Points 1 and 2 |
| Cookies or session not persisting | Cannot evaluate | Login never completed |
| Wrong login origin or domain | Possible secondary | `beta.oneclarity.ai` vs `oneclarity.ai`; blocked load in cb31e611 |
| Instructions encouraging clarification | Contributing | No rule for a failed `sign_in` |
| Question dedup or idempotency | **Gap confirmed** | No semantic dedup; each ask is a new approval |

## PRISM-QA-001 (full report)

- **Title:** QA Prism repeatedly asks for the same login or approval and re-requests a login that is already stored.
- **Affected Prism:** QA Analyst, `p8fDdp` (swarm `prism-ea6d9357`).
- **Severity:** P1. **Classification:** Worker/execution runtime (primary), Prism service, Agent reasoning. **Status:** Confirmed from recorded runs; live reproduction blocked.
- **Environment:** local development, flags v21/v22/v24 on, `@playwright/mcp@0.0.83`, model `gpt-5-mini`, Docker computers (exited when audited).
- **Preconditions:** QA task against a site that needs login, with `request_login` and `sign_in` granted.
- **Reproduction (recorded, not re-run):** assign "test oneclarity.ai", approve site access, approve the login card, watch the resumed run.
- **Expected:** the stored login is used once via `sign_in`; the run continues authenticated.
- **Actual:** `sign_in` fails with a generic error; the agent asks the manager again or re-requests the login; each repeat re-prompts for credentials; the manager sometimes types credentials into chat.
- **Frequency:** 4 of 4 chains with `request_login`; 9 of 9 `sign_in` calls failed.
- **Evidence:** swarm `approvals`, `run_events` for runs 1d69e0a9, 05fc0845, 8d1a7f6a, c746858d, 1624c7ee (task 02cfc4c4) and tasks bec6c437, cb31e611, 88ad53f7. Queries are reproducible with the read-only helpers described in [06](06-api-and-runtime-failures.md).
- **Suspected code:** `openai_agents.py:598-606` (`ref` vs `target`), `openai_agents.py:110-125` (no `sign_in` recovery rule), `qa_run_service.py:1262-1269`.
- **Confidence:** High for mechanism points 1 to 5 (static plus recorded data); Medium that nothing else also breaks `sign_in`.
- **Impact:** authenticated QA never happens; the manager is nagged repeatedly and pushed to share credentials.
- **Unverified:** the exact exception text for any one call (not logged); behaviour of a live run today.

<a id="core-001"></a>
## PRISM-CORE-001 Credentials in chat answers (P0)

- **What:** a manager's reply to `ask_manager` can contain a password. It is stored in swarm `approvals.payload.decision`, returned to the model, written to `run_events`, and shown in Prism chat.
- **Evidence (counts only, contents not read):** 2 of 17 swarm answers match `(pass(word)?|pwd)\s*[:=]`; 2 `tool_result` events match; 2 Prism `agent_thread_messages` match; 0 Prism `qa_approvals` payloads match.
- **Whether the exposed values are real credentials is unknown.** If they are, rotate them. I did not open the rows.
- **Layer:** Swarm runtime and Prism service. **Status:** Confirmed. **Confidence:** High that the pipeline stores and echoes free text; Medium on how many are real secrets.
- **Why it matters:** it is provoked by [PRISM-QA-001](#prism-qa-001-full-report); fixing the loop reduces exposure but does not remove it.

<a id="qa-002"></a>
## PRISM-QA-002 (P3)

Run `8d1a7f6a` seq 33: `record_test_result` status `pass` for "Attempt login with empty credentials", while the note says submission was not performed. The tool accepts a status with no evidence check. Single instance. Layer: Agent reasoning plus tool design.

## Not verified

- Authenticated QA, recovery cases and SSE behaviour; the accept-login path live.
- That `ref` versus `target` alone explains every `sign_in` failure. **Evidence to close:** start `npx @playwright/mcp@0.0.83` locally against a disposable local page and call `browser_type` with `ref` and with `target` (no external site, no credentials).
- Whether the OneClarity landing page's "14 console errors" (seen in one snapshot header) reproduce.
