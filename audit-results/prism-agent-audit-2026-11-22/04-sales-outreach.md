# 04 Sales Outreach (pocA9q)

Back to [executive summary](00-executive-summary.md). Tests: [09 matrix](09-test-execution-matrix.md) rows SAL-01..SAL-29.

**Scope note.** Run live on 2026-11-22 after the operator token was supplied: plan, start, one manager question, CSV download and the ranking follow-up. No outreach was sent, drafted outside the CSV, or attempted. The history section keeps the earlier recorded runs for context. Live artefacts: `evidence/live/sales-run.json`, `sales-file0.csv`, `sales-followup.txt`.

Prisms: Sales Outreach `pocA9q` (swarm `prism-cf3c8a04`) is the one audited. A second Prism `pN4qxx` "Sales Outreach Agent" and the legacy swarm agent `sales-outreach-agent` also exist ([PRISM-CORE-007](05-shared-infrastructure.md#core-007)).

## Live results (run 7640f93b)

| Measure | Value |
|---|---|
| Turns / time / cost | 8 of 120 / 69 s / 0.0108 USD (calculated) |
| Tool calls | `browser_navigate` (Google search, rate-limited 429), `ask_manager`, `save_file`, `complete_task` |
| Run status / `task_outcome` | succeeded / passed |
| Download | `GET /api/v2/qa/runs/{id}/files/0` returned 200, 6,128 bytes |
| Leads | 10 distinct, real, well-known India-linked companies (from model memory) |
| Decision-makers identified | 0 |
| Outreach messages | 10, every one containing the placeholder `[Name]` |
| Emails | none present (none invented) |
| Sizes | all labelled "(unverified)", none sourced |
| Validation status | rows say `partially_verified`; report claims partial verification of 5 results |
| Follow-up ranking | reused the same 10 leads; named BrowserStack, Postman and Razorpay first with generic reasons |

The agent asked one question (size band: mid-market or larger). I answered with "use the stored ICP; if none, any meaningful engineering organisation, size marked unverified". The run never opened a company or leader page, so no lead was verified.

## PRISM-SALES-002 (P1) The CSV is corrupt

- **Expected:** 15 aligned columns, valid escaping.
- **Actual:** one heading, "company size (estimate, unverified)", contains an unquoted comma, so the header has **16 cells**. Rows have 14 cells (4 rows), 15 cells (3 rows) or 16 cells (3 rows). No row has a consistent width. As a result values land under the wrong headings (for example prose in the decision-maker name column and URLs or message text in the email column).
- **Frequency:** 1 of 1 live CSV (and 1 of 5 historical files had a different defect, an appended `# Note` line).
- **Root cause (High):** the model writes the CSV text by hand through `save_file`; nothing builds or validates CSV (no writer tool, no parse check before `complete_task`). Layer: Agent reasoning plus Tool configuration.
- **Impact:** the downloadable deliverable cannot be imported reliably and silently mixes up fields.

## PRISM-SALES-003 (P1) Passed with unbacked verification claims

- **Actual:** `task_outcome: passed` and `partially_verified` labels, with one rate-limited Google page as the only browsing. Decision-makers are blank, outreach is a template, and nothing is sourced.
- **Expected:** a status that reflects what was checked, and blank or "unverified" values elsewhere.
- **Honest points:** the summary and `needs_attention` do say verification was partial and blocked by rate limits, and no email was fabricated.
- **Layer:** Agent reasoning plus Tool configuration. **Frequency:** 1 of 1 live run; the same pattern appears in 4 of 4 recorded runs ([PRISM-SALES-001](#prism-sales-001-lists-from-memory-presented-as-research-p1)).

## Summary matrix (live)

| Test case | Expected | Actual | Status | Bug |
|---|---|---|---|---|
| Exactly 10 distinct leads | 10 | 10, no duplicates | Passed | n/a |
| Real Indian companies | Real | Real and well known (not browsed) | Passed | n/a |
| Decision-makers | Named leaders | None | Failed | PRISM-SALES-003 |
| Contact/size sourcing | Sourced or blank | Unsourced; sizes marked unverified | Failed | PRISM-SALES-003 |
| No invented emails | None | None | Passed | n/a |
| Personalised outreach | Per company, no template | 10 x `[Name]` placeholder | Failed | PRISM-SALES-003 |
| CSV columns | 15 aligned | 16-cell header; rows 14/15/16 cells | Failed | PRISM-SALES-002 |
| CSV download | File served | 200, 6,128 bytes | Passed | n/a |
| Research traceable to browsing | Visited | 1 rate-limited search page | Failed | PRISM-SALES-001 |
| Follow-up reuses leads | Same leads | Same 10 | Passed | n/a |
| Outreach unsent | None sent | None sent | Passed | n/a |
| 6 failure scenarios | Per task | Not injected (search block occurred naturally: handled badly) | Failed / Not executed | PRISM-SALES-001 |

## History summary matrix

| Test case | Expected | Actual | Status | Bug |
|---|---|---|---|---|
| Research traceable to browsing | Cited sites were visited | 4 recorded runs cite 5 to 10 sites; 5 to 10 of them never visited | Failed | PRISM-SALES-001 |
| Failure: search blocked | Say so, stop or mark unverified | Google and Crunchbase rate-limited; run still `succeeded` with a memory-based list; summary admits it | Failed | PRISM-SALES-001 |
| CSV has the required 15 columns | All present | 2 to 3 columns in all 5 files | Failed | PRISM-SALES-001 |
| CSV parses cleanly | Yes | 4 of 5 clean; 1 has a blank line and an appended `# Note` line (2 ragged rows) | Passed (4) / Failed (1) | PRISM-SALES-001 |
| CSV download works | File served | Files exist on disk but API path logic cannot find 86 of 88 artifacts | Failed | PRISM-CORE-003 |
| Outreach stays unsent | No send | No outreach attempted by audit; `ask_manager` / `confirm_action` are ask-first | Analysed | n/a |

## PRISM-SALES-001 Lists from memory presented as research (P1)

- **Affected Prism:** Sales Outreach `pocA9q`. **Classification:** Agent reasoning plus Tool configuration. **Status:** Confirmed on 4 recorded runs; not run on the audit prompt.
- **Environment:** gpt-5-mini; grants `browser`, `save_file`, `ask_manager` (ask first), `complete_task`, etc.; no search tool.
- **Reproduction (recorded, not re-run):** ask the Prism for company lists.
- **Expected:** companies are looked up and opened; unverifiable fields are blank or marked unverified.
- **Actual:**

| Run (UTC) | Navigations | URLs cited | Cited sites never visited | What the single navigation was |
|---|---|---|---|---|
| ce6a2760 (11-02 18:00) | 2 | 5 | 5 | n/a |
| 79daddaa (11-03 00:51) | 1 | 10 | 9 | `miro.com` home page |
| d693bb55 (11-19 12:44) | 1 | 10 | 10 | Google search "OneClarity competitors" |
| 50b32766 (11-19 13:08) | 1 | 10 | 10 | Crunchbase employee-count search |

The three runs I inspected for tool names used `browser_navigate` and never a snapshot or read tool, so no page content was read. Run `50b32766`'s summary says Google and Crunchbase "were rate-limited ... so I relied on available public information and known vendor sites" and flags one entry as possibly wrong, yet the run status is `succeeded` and the CSV carries ten names and websites with no validation or confidence column.
- **Frequency:** 4 of 4 recorded runs that cited URLs.
- **Root cause (Medium to High):** the agent has no search or fetch tool, treats a rate-limited search page as acceptable end of research, and nothing checks cited sources against tool history. `succeeded` means "the model called `complete_task`", not "the work was verified".
- **Suspected code:** agent instructions and `GENERAL_NOTES` in `app/runtime/openai_agents.py` (no rule requiring page reads or marking unverified items); `complete_task` has no cross-check.
- **Impact:** a manager could act on invented or stale company data; the audit's own "no invented data" rule would not hold.
- **Unverified:** how the Prism behaves on the audit prompt with the stored OneClarity ICP.

## The five CSV files (parsed, contents not reproduced)

| Run | Columns | Data rows | Parse result |
|---|---|---|---|
| ce6a2760 `bangalore_fintechs.csv` | company, website, hq_city | 5 | clean |
| e822d579 `initial_candidates.csv` | Company, Website | 10 | clean |
| 79daddaa `initial_candidates.csv` | Company, Website | 10 | clean |
| d693bb55 `oneclarity_competitors.csv` | name, website, notes | 10 + blank line + `# Note: ...` line | 2 ragged rows for a strict parser |
| 50b32766 `oneclarity_competitors.csv` | name, website | 10 | clean |

None has industry, engineering signals, use case, decision-maker, title, profile link, public email, outreach, source links, validation status or confidence columns. A CSV with a trailing prose note is not safe for downstream import.

## Not verified

- Accuracy of each company's website, location and size (not browsed by the Prism, not checked by me), and the validity of any source link (the columns were misaligned).
- Download through the dashboard UI (only the API route was used).
- Whether `save_file` fails for CSVs on a fresh run (3 of 9 recorded calls were masked errors; see [PRISM-CORE-002](05-shared-infrastructure.md#core-002)).
