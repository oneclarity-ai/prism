# 03 AI Researcher (p817fY, also p5yX9V)

Back to [executive summary](00-executive-summary.md). Tests: [09 matrix](09-test-execution-matrix.md) rows AIR-01..AIR-26.

**Scope note.** Run live on 2026-11-22 after the operator token was supplied (two runs, plus the follow-up). Both runs stayed inside the platform defaults (120 turns, US$2, 30 minutes); I did not raise any limit. **The Prism did not complete the task: it delivered no developments.** Live artefacts: `evidence/live/researcher-run1.json`, `researcher-run2.json`.

## Live results

| Run | Turns used | Duration | Cost (calc) | Run status | `task_outcome` | Developments delivered |
|---|---|---|---|---|---|---|
| 1 (6f04eb16) | 18 of 120 | 102 s | 0.0119 USD | succeeded | blocked | 0 |
| 2 (30c69493) | 10 of 120 | 71 s | 0.0125 USD | succeeded | blocked | 0 (4 unverified headline topics) |

What happened:

- **Run 1:** searched Google (429), tried openai.com (403), loaded arXiv search, DeepMind and Anthropic pages, then asked "Shall I request login access for OpenAI and Google...?" about public sites. I answered no (public pages only). The resumed run took one snapshot and called `complete_task` with 102 turns unused. Its report says no announcement was extracted or verified. **Tool history matches the report** (5 navigations to the sites it names), so the report is honest, but empty.
- **Run 2:** asked a different question (official only, or include reporting?) that the task text already answers. After I answered, it opened a Google News aggregator page and summarised four headline topics, saying two were "confirmed" from that snapshot. Primary sources were not opened.
- **Follow-up** ("three most relevant developments... use only the verified information"): the Prism answered with three generic trends (retrieval re-rankers, graph memory, low-bit inference), with no source, date or link. Nothing was verified, so this is invented from model memory against the user's explicit constraint.
- **Consistency:** the two runs asked different questions and used different sources, but both ended `blocked` early.

## Summary matrix (live)

| Test case | Expected | Actual | Status | Bug |
|---|---|---|---|---|
| Searches for current information | Searches | Both runs searched (Google 429; Google News) | Passed | n/a |
| Visits relevant sites | Opens official sources | Anthropic, DeepMind, arXiv opened; OpenAI 403 | Passed | n/a |
| Opens real sources, not snippets | Reads articles | Run 1 read none; run 2 used an aggregator | Failed | PRISM-AIR-002 |
| At least 5 developments with dates and links | 5 or more | 0 | Failed | PRISM-AIR-002 |
| Recovers from blocked sites | Alternatives | Stopped at 403/429 | Failed | PRISM-AIR-002 |
| Facts vs speculation | Labelled | Aggregator items called "confirmed" | Failed | PRISM-AIR-004 |
| Report matches tool history | Yes | Yes (both runs) | Passed | n/a |
| Follow-up uses only verified research | Verified only | Three unsourced generic trends | Failed | PRISM-AIR-003 |
| Titles, dates, specs, benchmarks, links | Accurate | No content to grade | Blocked | PRISM-AIR-002 |
| Five other recovery scenarios | Per task | No fixture | Not executed | n/a |

## PRISM-AIR-002 (P1) Stops after reconnaissance, reports `succeeded`

- **Affected Prism:** AI Researcher `p817fY` (swarm `prism-07a6dfa4`). **Layer:** Agent reasoning plus Tool configuration. **Status:** Confirmed, 2 of 2 live runs.
- **Reproduction:** send the research prompt in the Prism chat, start the plan, answer its question.
- **Expected:** at least five sourced developments, or a clear explanation after real attempts.
- **Actual:** 10 to 18 of 120 turns used; no developments; Prism run status `succeeded` while the report says `blocked`.
- **Root cause (Medium):** no search or fetch tool (so one blocked search page ends research), a clarification question that invites the model to stop, and `complete_task` accepted with no minimum evidence. External blocks (OpenAI 403, Google 429) are an **external limitation**, but stopping instead of trying other public sources is Prism's handling.
- **Unverified:** whether a different network or a pre-warmed browser avoids the 403/429.

## PRISM-AIR-003 (P1) Follow-up invents instead of using verified research

Expected: "no verified information exists" or a list of what was verified. Actual: three unsourced items. 1 of 1 attempts. Layer: Agent reasoning and the chat follow-up path (`QaRunService._follow_up`, not traced in detail).

## PRISM-AIR-004 (P2) "Confirmed" from an aggregator

Run 2 calls items confirmed on the strength of a Google News snapshot, with no primary source. 1 of 2 runs.

## Which Prism

Two researcher Prisms exist:

| Prism | Code | Swarm agent | Recorded runs | Notes |
|---|---|---|---|---|
| AI Researcher | `p817fY` | `prism-07a6dfa4` | 3 (2 succeeded, 1 failed) | **No `save_file` grant** |
| AI ML Researcher | `p5yX9V` | `prism-17372fa4` | 11 (all succeeded) | Has `save_file` |

I treated "AI Researcher" as `p817fY` (exact name match) and analysed both.

## Summary matrix (history and configuration)

| Test case | Expected | Actual | Status | Bug |
|---|---|---|---|---|
| Search capability | A way to find current news | Grants contain `browser` only; no search tool. Search would mean navigating to a search page (Google and Crunchbase were rate-limited in recorded Sales runs) | Blocked | PRISM-AIR-001 |
| Report matches browsing (prior small runs) | Cited sites were visited | 14 recorded runs: 7 cite no URL, 3 cite only visited pages, 4 cite one host never visited (`iana.org` x3, `mem.ai`). Not the audit task | Analysed | n/a |
| Grant parity between researcher Prisms | Same | `p817fY` lacks `save_file` | Failed | PRISM-CORE-007 |

## Recorded activity (not the audit task)

Runs on 2 November and 19 November asked small questions, not a week-long survey. Across 14 runs: 132 tool calls, 17 `browser_navigate` calls, at most 4 navigations in any run, total calculated cost 0.0894 USD. No run had five or more sources, so these runs say nothing about the five-development requirement.

## PRISM-AIR-001 No search tool for a research Prism (P2, Tool configuration, Suspected)

- **Evidence:** swarm `agents.tool_grants` for both researcher agents: `browser`, `computer`, `sign_in`, `add_note`, `ask_manager`, `complete_task`, `confirm_action`, `get_task_context`, `request_login`, `update_checklist` (+`save_file` on one). No web-search or fetch tool.
- **Why it matters:** the task asks the Prism to "search for current information" and "open the actual sources". Without a search tool it depends on a search-engine web page. Recorded Sales runs show those pages rate-limiting, after which the agent produced a list from memory (see [04](04-sales-outreach.md)).
- **Confidence:** Medium. It is an inference from grants and recorded behaviour, not from a researcher run on the audit prompt.
- **To confirm:** run the research prompt once with the operator token and compare tool history to the report, as the audit plan describes.

## Not verified

Research accuracy, dates and links (nothing was delivered to grade); five recovery scenarios; whether the blocks are specific to this network.
