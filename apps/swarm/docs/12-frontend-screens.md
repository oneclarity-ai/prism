# 12 — Frontend Screens

Build in this order; each screen is usable on its own.

| # | Screen | Route | Contents |
| --- | --- | --- | --- |
| 1 | Login | `/login` | Email, password |
| 2 | Targets | `/targets`, `/targets/:id` | List + create/edit form: name, base URL, environment, test login (writes a secret), repo URL |
| 3 | Agents | `/agents`, `/agents/:id` | QA agent card: model, status, budget used this month, instructions editor, tool grants (Allowed / Ask first / Off per tool), pause/resume |
| 4 | Tasks | `/tasks` | Table or board by status; "New QA task" dialog: target, title, goal, scope (pages, acceptance criteria), schedule, allow bug filing |
| 5 | Task detail | `/tasks/:id` | Goal, scope, run history, "Run now" button, latest report |
| 6 | Run live view | `/runs/:id` | Left: timeline of agent steps (message, tool call, result) streaming over WebSocket; right: latest screenshot; header: status, elapsed time, tokens, cost, Cancel button |
| 7 | Run report | `/runs/:id/report` | Summary, test case table with pass/fail badges and evidence thumbnails (lightbox), bug drafts with "File bug" button, blocked cases |
| 8 | Approvals | `/approvals` | Pending list; each card shows action, payload preview (bug title, steps, screenshot), Approve / Reject with comment |
| 9 | Usage | `/usage` | Cost per agent per month, per run; budget bar |

## Key components

- `RunTimeline` — virtualised list of `run_events`; groups tool call + result; collapses long outputs (progressive disclosure: summary first, raw JSON on expand).
- `ScreenshotViewer` — thumbnails + full-size lightbox from `/artifacts/{id}/file`.
- `StatusBadge` — one colour per run/test status, used everywhere.
- `ApprovalCard` — reused in the Approvals page and inline in the run view when status is `waiting_approval`.
- `ToolGrantEditor` — table of tools with a 3-way toggle.

## UX rules (from Paperclip)

- Summary first, steps second, raw logs last.
- Work is done only when there is something to look at: a report, a screenshot, a filed bug link.
- Make waiting for approval obvious: banner on the run, badge in the sidebar.

## Done when

- A user can go from "new target" to "approved bug filed" without leaving the UI.
- The run view updates live without page refresh and survives a network blip.
