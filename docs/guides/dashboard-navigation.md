# Dashboard URLs and Prism codes

Prism keeps its existing sidebar and dashboard layout, with browser history for its pages.
Open a link directly, refresh it, or use Back and Forward to return to that view. The original
`/dashboard/` entry point and its static assets remain available.

## Page paths

| Page | Path |
| --- | --- |
| Chats | `/chats` (opens the selected Prism when available) |
| Prism chat and onboarding | `/prisms/pA7xQ2` |
| Prism settings | `/prisms/pA7xQ2/settings/overview` |
| Prism instructions, skills, tools and tasks | `/prisms/pA7xQ2/settings/{instructions,skills,tools,tasks}` |
| Workspace dashboard | `/workspace` |
| Tasks | `/tasks` |
| Runs | `/runs` |
| Individual run | `/runs/{run-uuid}` |
| Workspace approvals | `/approvals` |
| Bugs | `/bugs` |
| Prism directory | `/prisms` |
| Organization | `/organization` |
| Target apps | `/target-apps` |
| Secrets | `/secrets` |
| Spending | `/spending` |
| Run analytics | `/run-analytics` |
| Brain | `/brain` |
| Workspace skills | `/skills` |
| Global settings | `/settings/{section}` |

Settings sections include `account`, `preferences`, `notifications`, `general`, `teams`,
`archived`, `connections`, `provider`, `access`, `developer`, and `skills`, subject to the
existing feature flags. Settings opens as the existing modal. Closing it returns to the page
underneath; changing sections or themes does not discard an unsent chat draft.

Legacy views retain paths for compatibility: `/assistant`, `/work`, `/approvals-inbox`,
`/home`, `/ask`, `/management`, `/journeys`, `/knowledge`, and `/memory`. Disabled views
continue to follow the existing feature flags. Old `/dashboard/?thread=...` links still use
the legacy thread resolver. Existing OAuth query parameters are preserved.

Only explicitly supported document paths serve the dashboard shell. Unknown API paths, missing
static assets and arbitrary paths continue to return 404. The shell remains public, as before;
loading Prism data still requires the configured operator token. A code is an identifier, not
an access credential. Configure any reverse proxy to forward these paths to the Prism API.

## Stable Prism identity

Each Prism receives a code such as `pA7xQ2` when it is first saved, before onboarding finishes.
The format is a lowercase `p` followed by five random alphanumeric characters. Each suffix
contains at least one uppercase letter, one lowercase letter and one digit. Codes are case-sensitive.
The code appears beside its name in both onboarding and the active chat header. PostgreSQL
allocates codes with a bounded collision retry, serializes allocation within each schema, and
enforces uniqueness. Renaming, changing its role, archiving or restoring a Prism does not
change its code; codes cannot be edited through the create/update API.

The UUID remains the canonical database/API identity. Existing UUID chat links also open and
normalize to the shorter code URL. Old sequential codes such as `PR-12` remain saved as aliases
and also normalize to the new URL. `GET /api/v2/prisms/by-code/pA7xQ2` resolves a code under
the same feature flag and operator authentication as other Prism endpoints. Unknown codes
show an unavailable page rather than opening another cached Prism's conversation.

## Upgrade and verification

Stop the API, run `make migrate`, then restart the API and refresh the browser. Migration
`20261122_0049_prism_codes` introduced sequential codes; `20261122_0050_random_prism_codes`
replaces them with random codes and retains their old aliases without replacing UUIDs or
changing conversations, permissions or organization. Apply the migration before running the
updated application. Back up valuable data through the normal operator procedure first.

Downgrading 0050 to 0049 restores the exact saved sequential codes, including aliases assigned
to Prisms created after the upgrade. Random-code links are lost on downgrade and get new codes
on re-upgrade. Downgrading 0049 as well removes codes and the sequence, preserving Prism records.
Use the matching application version after rollback; do not run mixed application versions
against the changed schema.

UI checks:

- Open Spending and Run analytics; confirm `/spending` and `/run-analytics` in the address bar.
- Refresh a Workspace page and use Back/Forward across two pages.
- Create a Prism; check its code during onboarding and after activation.
- Switch Prisms, rename one, and paste its chat URL into another tab; the code stays the same.
- Open that Prism's Skills and Tools tabs; refresh their separate settings subroutes.
- Open global Settings, change sections, then close it; the chat draft remains.
- Open a run; refresh its `/runs/{uuid}` detail link.

Automated checks use disposable PostgreSQL and fake Graph/provider/engine boundaries:
`tests/test_dashboard_routes.py`, `tests/e2e/test_navigation.py`, and the existing dashboard,
chat, directory, skills and migration journeys. No live messages are sent by these checks.
