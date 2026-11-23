# 07 Model, tool efficiency and cost analysis

Back to [executive summary](00-executive-summary.md). Matrix rows: RC-01..RC-09, MB-01..MB-10 in [09](09-test-execution-matrix.md).

## Cost of the live phase (this audit)

Window: runs created after 12:45 UTC on 2026-11-22. Swarm figures are **calculated** from reported tokens with the swarm rate card; Prism-side figures are **estimated** from the ledger's pricing snapshot. Neither is provider billing.

| Source | Calls or runs | Input tokens | Output tokens | USD |
|---|---|---|---|---|
| Swarm: AI Researcher (4 runs incl. resumes) | 4 | 196,397 | 3,998 | 0.0244 |
| Swarm: Sales Outreach (2 runs) | 2 | 40,729 | 3,131 | 0.0108 |
| Swarm: QA Analyst (2 runs) | 2 | 1,484,625 | 7,159 | 0.0805 |
| Prism: Chief of Staff review | 1 | 34,256 | 2,824 | 0.0028 |
| Prism: plans, reports, intent, follow-ups, brain learning (azure_openai) | 19 | about 24,000 | about 9,500 | 0.0050 |
| **Total** | | | | **about 0.123** |

Total is well under the 12 USD ceiling and every run stayed inside platform defaults. Run durations: 71 s to 285 s. The QA run's 1.48 M input tokens for 285 s again shows snapshot-heavy context. No measured provider invoice was available, so none of these is a billed amount.

## Swarm runs (recorded history, 61 runs before the live phase)

Source: swarm `runs` table. `cost_usd` is **calculated** by the swarm from tokens and its own rate card. It is not billing data. Token counts are as reported by the provider to the worker.

| Agent | Runs | Succeeded | Failed or cancelled | Input tokens | Output tokens | Cost USD (calc) | Tool calls | Longest run (s) |
|---|---|---|---|---|---|---|---|---|
| QA Analyst (`p8fDdp`) | 27 | 18 | 9 | 6,579,306 | 40,295 | 0.3664 | 361 | 962 |
| AI ML Researcher (`p5yX9V`) | 11 | 11 | 0 | 668,232 | 14,623 | 0.0584 | 117 | 110 |
| AI Researcher (`p817fY`) | 3 | 2 | 1 | 130,672 | 3,706 | 0.0310 | 15 | 57 |
| Sales Outreach (`pocA9q`) | 8 | 7 | 1 | 176,045 | 7,696 | 0.0295 | 42 | 67 |
| Sales & Marketing | 3 | 3 | 0 | 63,981 | 1,970 | 0.0088 | 12 | 36 |
| Market Research | 3 | 1 | 2 | 0 | 0 | 0.0000 | 11 | 60 |
| legacy `qa-agent` | 5 | 1 | 4 | 4,419,070 | 14,329 | 0.1931 | 109 | 288 |
| legacy `sales-outreach-agent` | 1 | 0 | 1 | 184,287 | 5,680 | 0.0211 | 38 | 113 |
| **Total** | **61** | **43** | **18** | **12,221,593** | **88,299** | **0.7083** | **705** | |

- Model recorded on runs: `gpt-5-mini` (Azure deployment). Provider: Azure OpenAI.
- Retries: 0 runs with `attempt` above 1. Run durations: all but the longest QA runs finish in under two minutes.
- **Input-heavy QA runs:** the QA Analyst sends about 163 input tokens per output token (6.58 M to 40 k) and averages about 244 k input tokens per run, consistent with large page snapshots growing the context. Cost stays small per run (about 0.014 USD) at this model's rates.
- **Chain overhead:** each approval pause starts a new run, so one QA task (02cfc4c4) shows as five runs; in that chain run 1624c7ee alone used 353,353 input tokens for 55 seconds of work.
- **Failed tool calls:** 92 tool results matched an error heuristic across 705 calls (13%); 72 of those are in QA Analyst runs. A further 14 tool results were the masked generic error, which the heuristic does not count ([05](05-shared-infrastructure.md#core-002)).
- **Unnecessary or repeated actions:** the clearest case is the QA login loop (up to six consecutive `ask_manager` calls in one task, `bec6c437`). I did not measure other redundancy against an ideal path.
- **Budgets and limits:** five runs stopped at their turn limit (15, 25, 60, 60, 80); per-run cost versus cap was not compared. Configured caps: 150 turns, 3.00 USD, 30 minutes.

## Prism-side provider ledger (`llm_usage`, 2026-09-09 to 2026-11-22)

Provider-reported tokens. Cost per call is **estimated** from a pricing snapshot.

| Provider | Status | Calls | Input tokens | Output tokens | Estimated cost USD | Calls with no usage recorded |
|---|---|---|---|---|---|---|
| azure_openai | completed | 447 | 3,271,912 | 1,394,547 | 0.6940 | 0 |
| azure_openai | failed | 65 | 87,545 | 46,611 | 0.0167 | 59 |
| codex_local | completed | 26 | none | none | n/a | 26 |
| codex_local | failed | 7 | none | none | n/a | 7 |
| qa_workspace (swarm mirror) | completed | 43 | 4,907,511 | 51,578 | 0.3552 | 0 |
| qa_workspace (swarm mirror) | failed | 18 | 7,314,082 | 36,721 | 0.3535 | 0 |

- The `qa_workspace` rows mirror the 61 swarm runs. Their input total (12,221,593) equals the swarm total, and cost differs by 0.0004 USD (estimated 0.7087 vs calculated 0.7083).
- **Failed Prism-side calls mostly record no usage** (59 of 65), so spend on failed calls is not fully measured. Local Codex calls record no tokens at all, so their cost is unknown.
- Chief of Staff review calls (`v21_conversation_review`) used `gpt-5-nano` and local Codex. Nine review calls and one repair call are marked failed; average latency of the recorded failed `gpt-5-nano` review calls was 40 to 100 seconds.

## Model and agent behaviour (from recorded evidence)

| Area | Finding | Layer | Reference |
|---|---|---|---|
| Tool selection | Agent held the field refs but asked the manager instead of calling `sign_in` | Agent reasoning | [QA-001](02-qa-analyst.md) |
| Recovery from a vague error | Repeats asks when `sign_in` returns "try again" | Agent reasoning plus tool config | [CORE-002](05-shared-infrastructure.md#core-002) |
| Honesty of results | Recorded a case as `pass` that it said it did not perform | Agent reasoning plus tool design | [QA-002](02-qa-analyst.md#qa-002) |
| Grounding | Four Sales runs list sites never opened | Agent reasoning plus tool config | [SALES-001](04-sales-outreach.md) |
| Evidence attribution | Review model guessed source ids that disagreed with its own citations | Model output plus Prism validation | [COS-001](01-chief-of-staff.md) |
| Untrusted content, hallucination on audit prompts, repeatability | Not tested | n/a | none |

Several of these are **orchestration or tool defects first** (the masked error, the missing search tool), so they should not be treated as prompt problems.

## Repeatability and latency

Consistency runs were not possible because no live run was available. Latency figures above are from history only.
