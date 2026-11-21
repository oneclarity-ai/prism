# Changelog

All notable changes to Prism will be documented in this file.

The project intends to follow [Semantic Versioning](https://semver.org/) after its first tagged
release. Dates use ISO 8601.

## [Unreleased]

### Added

- Direct dashboard page/subpage URLs with refresh and Back/Forward support, including Spending,
  Run analytics, individual runs and Prism settings tabs. Each Prism receives a stable code such
  as `pA7xQ2` (lowercase `p` and five random mixed-case letters/digits) during creation, shown
  during onboarding and active chats. Migrations `20261122_0049` and `20261122_0050` backfill
  existing Prisms while preserving UUIDs, history and old sequential links as aliases.
  See `docs/guides/dashboard-navigation.md`.
- Shared workspace skill library for any business department and three private skills generated
  automatically from confirmed chat onboarding, with a saved chat notification and no repeated
  questionnaire. Separate Skills and Tools tabs provide editable cards and independent permissions.
  Skills never grant tool access. Migrations `20261121_0047` and `20261122_0048` preserve existing
  Prisms, history, shared skills and permissions. See
  `docs/guides/prism-skills.md`.
- Prism v2.2: multiple private Prisms with onboarding, working agreements, Teams monitoring,
  evidence-backed proactive updates, browser notifications, incident grouping, approval-gated
  drafts, feedback and tuning, budgets, health status, retention, v2.1 migration, and
  operator recovery commands. See `docs/releases/v2.2-release-runbook.md` and `docs/releases/v2.2-security-review.md`.
- Open-source repository documentation, contributor guidance, security policy, and support policy.
- Docker and Compose development path.
- Ruff, mypy, dependency auditing, and tracked-file secret scanning commands.
- GitHub issue/PR templates, CI, security workflows, and Dependabot configuration.

### Changed

- One kind of agent: creating a Prism uses a two-pane dialog (name, role, department, reports to, job
  description with Generate with AI and Write/Preview), then onboarding continues in its chat. Each Prism has
  its own Workspace page (Overview, Instructions, Tools with Allowed / Ask first / Off, Tasks), reached from
  **More settings** on the Prism in the sidebar, its chat menu or its card. Prisms own their tool grants,
  instructions and limits (migration `20261121_0046`) and sync them to the engine. Workspace > Prisms now
  lists every Prism (including ones still being set up) as redesigned cards with search and filters.
  Engine-only agents are adopted as Prisms once. New endpoints: `POST /api/v2/prisms/generate-description`,
  `POST /api/v2/prisms/adopt-engine-agents`, `GET /api/v2/prisms/{id}/tools`.
- Dashboard redesigned in a Notion style: new light/dark palette, 6px buttons with blue primary
  actions, Chats | Workspace | Search icon row in the sidebar (Home retired, Prisms page
  with Cards and Org chart views inside Workspace; the app opens on Chats), no top bar or page emoji, a profile menu at the bottom of the sidebar, and Settings as a modal with new
  Preferences, Notifications, Connections and Developer sections plus settings search.
- Added universal search (sidebar Search button or Ctrl/Cmd+K) across Prisms, chat messages, Workspace
  pages, Settings and quick actions. The message box no longer shows a blue focus box.
- Added a single Workspace **Spending** page for Prism, swarm and provider cost; it replaces the
  Home cost block and Settings → Usage. Workspace "Usage & analytics" is now "Run analytics".
- Whole dashboard is about 11% smaller by default (12.5px text); Preferences → Display size offers Compact,
  Default and Large (Large is the previous size). Touch screens keep full-size controls.
- Added browser-only preferences: High contrast, Enter-adds-a-new-line (Cmd/Ctrl+Enter sends), and
  hiding waiting-approval counts.

- Unified the dashboard's neutral surfaces, controls, typography, and focus styles across light
  and dark themes. Preserved the existing theme preference, added keyboard navigation and viewport
  placement for profile/theme menus, and aligned Workspace numeric columns. Manager approvals,
  source scopes, and delivery behavior are unchanged. See `docs/guides/prism-design-system.md`.
- Generalized organization- and manager-specific runtime names under the Prism identity.
- Production and publicly exposed API configurations now fail closed without an operator token.

### Security

- Replaced organization-specific example configuration with safe placeholders.
- Documented delegated-token, webhook, scheduler, and database security boundaries.
- Updated vulnerable runtime and test dependencies identified by `pip-audit`.
