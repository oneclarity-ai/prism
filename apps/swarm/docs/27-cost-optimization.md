# 27 — Cost Optimization (Azure OpenAI)

How the QA agent spends tokens, what history the model sees, and every cost control in the platform.

## 27.1 Is history kept? What does the model see?

| Where | What is kept | Sent to the model? |
| --- | --- | --- |
| **Inside one run** | The whole conversation: the prompt, every tool call and every tool result | **Yes, on every model call.** The Azure API is stateless, so each call re-sends the conversation. This is why long runs get expensive. |
| **Between runs** | Nothing, except a short `previous_run_summary` (the last run's summary on the same task, a few lines) | Only that summary, through `get_task_context` |
| **In the database** | Every event, test case, bug, screenshot and token count | No. This is for you (live log, reports, analytics) |

So history does not pile up across runs. The cost driver is the length of **one** run: every page snapshot the agent reads stays in the conversation and is paid for again on each later turn. The controls below attack exactly that.

## 27.2 What was measured

The first oneclarity.ai run (`136c4b6a`, before these changes), last 40 turns:

| | Per model call |
| --- | --- |
| Input (context) | 66,780 tokens on average, up to **92,000** |
| Output | **~1,540 tokens** (mostly hidden reasoning, billed at the output rate) |
| Time | 7–23 s |
| Cost | ~$0.02 |

Demo Shop parallel run after the changes (3 sub-agents, 2026-10-14), first turns:

| | Per model call |
| --- | --- |
| Input | ~4,000 tokens, of which **~90% cached** (billed at 10%) |
| Output | **~13 tokens** |
| Time | ~2 s |
| Cost | ~$0.0003 |

## 27.3 The controls

| # | Control | What it does | Setting (`backend/.env`) | Default |
| --- | --- | --- | --- | --- |
| 1 | **Reasoning effort** | gpt-5 models "think" before answering; those hidden tokens are billed as output (8× the input price on gpt-5-mini). Low effort is enough for clicking through a test plan. | `AZURE_REASONING_EFFORT` (`minimal`, `low`, `medium`, `high`; empty = model default `medium`) | `low` |
| 2 | **Verbosity** | Shorter replies from gpt-5 models. | `AZURE_VERBOSITY` | `low` |
| 3 | **Context trimming** | Before each model call, older large tool outputs (page snapshots) are cut to 300 characters; the last N stay in full. The agent can take a fresh snapshot when it needs one. | `CONTEXT_KEEP_RECENT_OUTPUTS` | `4` |
| 4 | **Fewer browser tools** | Every tool's description is re-sent on every call. Only 15 of Playwright's 25 browser tools are offered (no drag, resize, raw JS, network dumps, uploads). | code: `BROWSER_TOOLS` in `runtime/openai_agents.py` | — |
| 5 | **No automatic snapshots** | Browser actions return a short result; the agent reads the page with `browser_snapshot` only when it needs to, and uses `browser_find` to check for a text. | code: `--snapshot-mode none` | — |
| 6 | **Prompt caching** | Azure automatically re-uses a repeated prompt start (instructions, tools, early conversation) and bills it at ~10%. The platform keeps that start stable (trimmed outputs stay trimmed the same way). The cost estimate now counts cached tokens at the cached price. | `AZURE_PRICE_CACHED_INPUT_PER_1M` (empty = 10% of the input price) | 10% |
| 7 | **Stay in scope** | Agent instructions: test only the pages in scope, 2–6 cases per page, one `browser_fill_form` per form (no click-then-type), screenshots only for failures (max one per pass page), record each result right away. | code: `RUNTIME_NOTES` | — |
| 8 | **Choose pages per run** | Test one page or a few pages without editing the task ([25.9](25-setup-any-website.md#259-test-one-page-or-choose-pages-per-run)). | Run with options | all pages |
| 9 | **Parallel sub-agents** | Each sub-agent has a short, focused context instead of one agent carrying 12 pages ([26](26-parallel-agents-orchestration.md)). | Run with options → Parallel | — |
| 10 | **Hard limits** | Per-run max turns and budget (agent settings or per run), monthly budget per agent. A run that hits a limit stops; results recorded so far are kept. | Agents → Limits; Run with options | 150 turns / $3; sub-agent 80 turns / $1 |
| 11 | **Retry instead of fail on rate limits** | When parallel agents share the deployment's tokens-per-minute quota, HTTP 429 answers are retried with backoff. | `AZURE_MAX_RETRIES` | `6` |
| 12 | **Merge without the big model** | The parallel merge is rule based. It makes one small call (a few thousand tokens) for the executive summary, only on the Azure runtime. | — | — |

Settings are read when the worker starts: restart `./scripts/dev.sh` after changing them.

## 27.4 Where to see the cost

- Run page header: live tokens and cost / budget. For a parallel run, the total of all sub-agents.
- Worker log, one line per model call: `tokens_in`, `tokens_cached`, `tokens_out`, `run_cost_usd`.
- Usage & analytics page: cost per day, per agent, per model.
- Prices: set `AZURE_PRICE_INPUT_PER_1M`, `AZURE_PRICE_OUTPUT_PER_1M` (and optionally the cached price) to your Azure contract rates. Costs shown are estimates from these rates; the Azure bill is the source of truth.

## 27.5 If quality drops

Low reasoning is a trade-off. If the agent starts missing obvious bugs or misreading pages:

1. Set `AZURE_REASONING_EFFORT=medium` (expect ~5–10× more output tokens) and restart.
2. Or keep `low` and narrow the task (fewer pages per agent).
3. Keep gpt-5-mini; gpt-5-nano was measured as too weak ([23](23-testing-oneclarity-ai.md)).
