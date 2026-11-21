# Changes since v2.4

Date: 22 November 2026
Baseline: the v2.4 documentation set ([runbook](v2.4-release-runbook.md),
[plan](v2.4-dynamic-prisms-and-computers-plan.md), [generic-execution audit](v2.4-generic-execution-audit.md))
and the [20 November current-stage audit](../guides/current-stage-audit.md).

v2.4 gave every Prism its own computer and kept the swarm's console as a separate operator tool. Since then
the product was unified under one interface, the dashboard was redesigned, and the two codebases were
merged into one repository. This page lists what is different. Schema changes are limited to the five
migrations at the end; nothing here is a breaking API change.

## 1. One kind of agent, one interface

| Before (v2.4) | Now |
| --- | --- |
| Prisms and engine "agents" were separate ideas; engine-only agents had their own console | **Prism and agent mean the same thing.** Engine-only agents are adopted as Prisms once (`POST /api/v2/prisms/adopt-engine-agents`) |
| Operators used the swarm React console for tasks, runs, approvals, bugs, agents, targets, secrets, usage | Those sections are inside Prism's **Workspace**; the manager never needs the swarm UI. The React console is a diagnostic tool and is no longer started by the launcher |
| Creating a Prism meant filling a long form | Two-pane create dialog (name, role, department, reports to, job description with **Generate with AI** and Write/Preview; `POST /api/v2/prisms/generate-description`), then **onboarding continues in the Prism's chat** in the swarm's questionnaire style |
| Tool grants and limits lived mostly in engine settings | Each Prism owns instructions, **Tools (Allowed / Ask first / Off)**, tasks and limits, and syncs them to the engine (`GET /api/v2/prisms/{id}/tools`) |

The org chart is derived from real Prisms: the connected user at the root, the Chief of Staff Prism, then
non-archived Prisms by `reports_to_prism_id`, including ones still being set up.

## 2. Dashboard redesign

- **Notion-style UI**: new light/dark palette, 6px controls, no top bar or page emoji, 11% smaller default
  size with a Display size preference (Compact / Default / Large).
- **Sidebar** is a tab row: **Chats | Workspace | Notifications**, plus Search. Home was retired; the app
  opens on Chats. The Notifications tab lists approvals and Brain facts waiting for you and links to
  notification settings.
- **Profile menu** at the bottom of the sidebar; the theme is a three-icon control (system, moon, sun) with
  keyboard support. The old theme selects in the menu and in Settings were removed.
- **Settings** is a modal: Preferences, Notifications, Connections, Developer, with settings search. **More
  settings** for a Prism moved into the chat's right drawer.
- **Universal search** (sidebar button or Ctrl/Cmd+K) across Prisms, chat messages, Workspace pages, Settings
  and quick actions.
- **Browser-only preferences**: high contrast, Enter-adds-a-new-line, hide approval counts.
- **Direct URLs** for pages and sub-pages with refresh and Back/Forward. Every Prism has a stable code such
  as `pA7xQ2`; old sequential links keep working as aliases. See
  [dashboard navigation](../guides/dashboard-navigation.md).
- Design tokens and component rules: [design system](../guides/prism-design-system.md).

## 3. Workspace pages

Workspace is now the home for everything that is not a chat:

- **Overview**: Dashboard, Spending (Prism, swarm and provider cost in one place; replaces the Home cost
  block and Settings, Usage) and **Run analytics** (formerly "Usage & analytics"). **Work**: Tasks, Runs,
  Approvals, Bugs. **Team**: Prisms, with Cards (search and filters) and Org chart views. **Setup**: Target
  apps, Secrets, Skills. Most Work and Team items need `PRISM_V24_ENABLED`; Spending and Brain follow `PRISM_V22_ENABLED`.
- **Knowledge, Brain** (moved out of Settings): stat tiles, an approval panel for facts Prisms learned from
  chats, a searchable fact grid, Prism work notes, and an Add to Brain dialog. A badge in the sidebar and
  Notifications tab counts facts waiting for approval. The Brain API is unchanged
  (`/api/v2/brain`, approve and reject endpoints).
- Backed by `GET /api/v2/operations/overview`, `/operations/analytics`, run detail and artifact routes, and
  task, position, target and secret writes under `/api/v2/operations/...`. Task starts, exact Teams sends and
  approval decisions still go through the existing Prism workflows, so scopes and approval rules are unchanged.

## 4. Skills and Tools

A shared skill library for any business department, plus three private skills generated automatically from a
confirmed chat onboarding (with a saved chat notification, no repeated questionnaire). Skills and Tools are
separate tabs with editable cards and independent permissions; **skills never grant tool access**. See
[Prism skills](../guides/prism-skills.md).

## 5. Website testing

QA plans default to **Discover pages automatically**: the Prism explores visible links and routes inside the
initial origin and reports tested pages, issues and discovered pages left untested. New sites and secure logins
need separate approvals. Details: [v2.4 runbook](v2.4-release-runbook.md#website-testing-automatic-page-discovery).

## 6. One repository, regrouped code

The swarm now lives in `apps/swarm` and Prism in `apps/prism`; Prism's services, models, schemas and routes
are grouped by domain; docs are split into `guides/` and `releases/`; one `make dev-all` or
`docker compose up` starts everything. Full account, verification table and rollback:
[monorepo layout and migration](../architecture/monorepo.md).

## 7. Database migrations added

| Revision | Purpose |
| --- | --- |
| `20261120_0045` | Prism organization: job role, department, reporting line, Chief of Staff |
| `20261121_0046` | Prism agent setup: instructions, tool grants and limits owned by the Prism |
| `20261121_0047` | Prism skills library, assignments and setups |
| `20261122_0048` | Private onboarding skills |
| `20261122_0049`, `20261122_0050` | Stable random Prism codes; UUIDs, history and old sequential links preserved |

Upgrade with `make migrate` (from the repository root or `apps/prism`). Take a database backup first.

## 8. Known limits and not yet verified

- The browser e2e suite was not run for the latest dashboard changes (collection works: 90 tests).
- The swarm backend has its own 78 tests but is not yet part of the repository's GitHub CI.
- Cross-service authentication, restart/recovery drills and a formal versioned contract between Prism and the
  swarm remain open items from the [unification plan](../guides/prism-swarm-unification-plan.md).
- `alembic check` reports model/database drift on a few constraints and indexes (for example
  `agent_source_messages`, `prism_external_events`, two onboarding index names). It predates the migration to the
  monorepo and should be reviewed before the next release.
