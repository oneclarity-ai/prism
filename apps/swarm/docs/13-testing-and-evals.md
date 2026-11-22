# 13 — Testing and Evals

## Platform tests

| Layer | Tool | What to cover |
| --- | --- | --- |
| Services | pytest | Queue claim (no double claim), budget checks, approval state changes, secret masking |
| API | pytest + httpx | Every endpoint: success, validation error, auth error |
| Worker | pytest with `FakeAdapter` | Lifecycle: succeed, fail, timeout, cancel, recovery after restart |
| Frontend | Vitest + Testing Library | Forms, status badges, timeline rendering |
| UI e2e | Playwright | Login → create target → create task → run (FakeAdapter) → report |

Use `FakeAdapter` in CI so tests are fast and free. Run real-model evals separately.

## Agent evals: the eval app

Build `eval-app/`: a small web app (e.g. a to-do or shop app with login, list, form, checkout) with **10 seeded bugs**, each switchable by an env flag. Examples:

1. Login accepts a wrong password for one specific user.
2. Required field can be submitted empty.
3. Price total wrong when quantity > 9.
4. Unicode name breaks the profile page.
5. Back button after submit creates a duplicate.
6. Error message missing on server 500.
7. Pagination skips the last item.
8. Max-length input truncates silently.
9. Logout link does nothing on mobile width.
10. Console error on the settings page.

Plus a **clean** build with no bugs to measure false positives.

## Eval runs

1. Script `scripts/run_eval.py` starts the eval app (bugs on), creates a task "Full regression of the app", runs the agent, and scores: bugs found (match by case/area), false bugs, blocked cases, cost, duration.
2. Run against the clean build to count false bug reports.
3. Store results in `eval_results/<date>.json`; compare against the previous run.
4. Run evals after every change to the skill, prompts, model or tools.

## Done when

- CI runs platform tests on every push in under 5 minutes.
- Eval script prints a score table; MVP targets from 01 are met.
