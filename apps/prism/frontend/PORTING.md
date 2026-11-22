# Porting the Prism dashboard to React + Vite + TypeScript

Old app: `apps/prism/app/static/` (index.html + vanilla ES modules in `js/`, CSS in `css/`). It keeps running and is the
behavioral spec. New app: this `frontend/` project. Cutover (deleting the old app) happens only after every feature is ported.

## Hard rules

1. **Same behavior.** Port line by line from the old file: same endpoints, request bodies, polling intervals/timers, localStorage
   keys, keyboard handling, focus management, aria attributes, empty/error texts, ordering, edge cases. If something looks like a bug,
   port it faithfully and mention it in your report; do not silently "fix" or redesign.
2. **DOM contract is frozen.** CSS (`src/styles/*.css`, copied unchanged) and the Playwright suite in `apps/prism/tests/e2e/`
   select by id, class, `data-*`, role and visible text. Reproduce the same element structure, ids, classes, data attributes,
   aria attributes and text. Do not edit the CSS files except for a React-only necessity (tell me if you do). Check
   `tests/e2e/*.py` for selectors touching your feature before you finish.
3. **TypeScript strict, no `any`** (eslint errors on `no-explicit-any`). Use generated API types:
   `import type { Schema } from "@/types"` then `Schema<"PrismCreate">` (names from `src/types/api.generated.ts`, regenerate with
   `npm run types` if the backend schema changed). Where the generated type is too loose/wrong (many responses are untyped dicts),
   define a precise local interface next to the feature instead of `any`/`unknown` casts everywhere.
4. **Network only via `agentApi`** from `@/lib/api` (`agentApi<T>(path, { method, ...jsonBody(x) })`). For blobs/binary use
   `fetch` with `operatorHeaders()`. Errors are `ApiError` (`.code`, `.status`); show messages with `errorMessage(e)`.
5. **Untrusted text (Teams/model/user content) is rendered as React text children, never `dangerouslySetInnerHTML`**, never
   built into HTML strings. Links: `rel="noopener noreferrer"`. Markdown goes through the shared `Markdown` component only.
6. **React idioms.** Function components + hooks; state in components/contexts; no `document.querySelector` to read/write app DOM
   (refs and `dialog.showModal()` for native `<dialog>`, focus management and scroll containers are fine). Keep native `<dialog>`
   elements (their `::backdrop`/modal CSS depends on them). All tab panels stay mounted and are toggled with `hidden` (the old app
   keeps every panel's state alive across tab switches; chat polling must keep working).
7. **Don't edit files you don't own.** Put new code under your feature folder. If you need a change in shared code
   (`src/lib`, `src/components/ui`, shell) write it down in your final report under "NEEDS" instead of editing.
8. **Quality gate (run from `apps/prism/frontend`):** `npm run typecheck && npm run lint && npm test`. Add vitest tests for pure
   logic and React Testing Library tests for important components (fake `fetch`, no live backend). Never claim a check passed
   without running it.
9. No new npm dependencies without asking (react, react-dom only at runtime).
10. Comments: only where the *why* is non-obvious. No planning docs.

## Shared building blocks (already written unless marked TODO)

- `@/lib/api` — `agentApi`, `ApiError`, `jsonBody`, `errorMessage`, `operatorHeaders`.
- `@/lib/storage` — `readStorage/writeStorage` (never throw), `STORAGE_KEYS`.
- `@/lib/prefs` — theme/prefs/display size: `usePref(name)`, `setPref`, `useThemeChoice`, `setTheme`, `uiZoom()`.
- `@/lib/events` — typed event bus replacing `document` CustomEvents (`emit`, `useBusEvent`). Table of events in that file. One-shot
  commands and refresh nudges only; shared *state* goes through contexts.
- `@/lib/app-context` — `useApp()`: shell API (active tab, sidebar section, modes v21/v22/v24, `setStatus` toast, `askDialog`,
  settings open/close, `refreshKey`, provider/Microsoft status, narrow layout, `go(path)`); replaces `window.prism`/`prismRoutes`.
- `@/features/prisms/PrismsContext` — `usePrisms()` shared Prism list (replaces `prism:list`). Provider owned by the Prism directory port.
- `@/components/ui/*` — shared primitives ported from `workspace-ui.js` (Icon, Button, Chip, Panel, Metric, Tabs, DataTable,
  FormDialog host, ...), `Markdown`, `PrismLogo` etc. Written by the foundation task; import from `@/components/ui`.
- `@/types` — `Schema<"Name">` generated API types.

## Ownership (old source -> new location)

| Owner | Old files | New folder |
|---|---|---|
| shell (lead) | `index.html` 1-117 (sidebar, profile menu, page head), settings dialog frame, confirm dialog, `navigation.js`, `theme-init.js`, `tab-identity.js`, mode gating from `app.js` | `src/App.tsx`, `src/shell/*`, `src/lib/*` |
| foundation | `workspace-ui.js`, `prism-logo.js`, `markdown.js`, `prism-organization.js` | `src/components/ui/*`, `src/lib/*` |
| chat | `agent-chat.js`, index.html `data-tab="agent"` view + `agent-source-dialog`, `prism-source-dialog` | `src/features/chat/*` |
| computers | `qa-tester.js` (+ computer panel markup inside the chat view) | `src/features/computers/*` |
| prisms | `prism-directory.js`, `prism-skills.js`, `prism-health.js`, `prism-updates.js`, `archived-prisms.js`, index.html `data-tab="prisms"` + prism-* dialogs | `src/features/prisms/*` |
| workspace | `workspace-controller.js`, `workspace-pages.js`, `operations.js`, `unified-work.js`, `brain.js`, `prism-detail.js`, `people-directory.js`, `person-edit-dialog` | `src/features/workspace/*`, `src/features/people/*` |
| legacy+settings | `app.js` (overview/ask/management/journey/knowledge/memory/spending views, settings panes, provider BYOK cards, record/revision dialogs), `today-prisms.js`, `command-palette.js`, `preferences.js` | `src/features/legacy/*`, `src/features/settings/*`, `src/features/search/*`, `src/features/spending/*` |

Each feature exports one top-level component per tab/dialog it owns (see your task brief); the shell mounts them.

## Final report format (keep short)

Files created; old files fully covered (list); behaviors intentionally deferred or deviating (and why); NEEDS from other owners;
exact commands run and their results; anything you could not verify.

## Shell mount points (stubs already exist; the owner replaces the stub file, keeping the export name and props)

The shell (`src/App.tsx`, `src/shell/*`) renders the layout wrappers: `<aside class="sidebar">`, section wrappers
(`<section class="view tab-panel" data-tab=... hidden=...>`), toast, confirm dialog, page head. Mounted components render the
*inner* content of those wrappers (so ids/classes inside are yours; ids/classes of the wrapper are the shell's). Gating by
feature flags (`modes.v21/v22/v24`) of the wrappers is done by the shell; gate anything inside the wrapper yourself with `useApp().modes`
using the same rules as the old `data-v21-only` / `data-v22-only` / `data-v24-only` / `data-hide-v22` attributes (keep the attributes too).

| Export | File | Owner | Renders |
|---|---|---|---|
| `PrismsProvider({children})` | features/prisms/PrismsProvider.tsx | prisms | provides `PrismsContext` (list, loading, selectedId, reload) |
| `PrismCreateButton()` | features/prisms/PrismCreateButton.tsx | prisms | `#prism-create-button` icon button in the sidebar head |
| `PrismSidebarSection()` | features/prisms/PrismSidebarSection.tsx | prisms | `.sidebar-section-head` ("Prisms" + `#prism-archived-button`) and `#prism-directory-list` |
| `PrismsPage()` | features/prisms/PrismsPage.tsx | prisms | inside `data-tab="prisms"`: `#prism-workspace` onboarding chat + all `prism-*` dialogs |
| `SkillLibrary()` | features/prisms/SkillLibrary.tsx | prisms | Settings > Skills body (`#settings-skills-library` content) |
| `ArchivedPrismsPane()` | features/prisms/ArchivedPrismsPane.tsx | prisms | Settings > Archived Prisms body |
| `AgentPage()` | features/chat/AgentPage.tsx | chat | inside `data-tab="agent"`: the whole chat workspace + `agent-source-dialog` |
| computers API | features/computers/index.ts | computers | see the file: same functions as qa-tester.js exports + `ComputerPanel` + `useComputersEnabled` |
| `WorkspaceSidebarPanel()` | features/workspace/WorkspaceSidebarPanel.tsx | workspace | everything inside `#sidebar-workspace-panel` (nav buttons, counts, legacy links) |
| `NotificationsSidebarPanel()` | features/workspace/NotificationsSidebarPanel.tsx | workspace | everything inside `#sidebar-notifications-panel` |
| `OperationsPage()` | features/workspace/OperationsPage.tsx | workspace | inside `data-tab="operations"` (workspace pages, run/prism detail, `#workspace-page-actions` content via `useApp().pageActionsRoot` portal) |
| `WorkPage()` / `ApprovalsPage()` | features/workspace/WorkPage.tsx / ApprovalsPage.tsx | workspace | inside `data-tab="work"` / `data-tab="approvals"` (unified-work.js) |
| `PeoplePane()` | features/people/PeoplePane.tsx | workspace | Settings > People body + `person-edit-dialog` |
| `SettingsDialog()` | features/settings/SettingsDialog.tsx | legacy+settings | the whole `<dialog id="settings-dialog">` incl. nav, search, all section bodies (uses `useApp().settings`); embeds SkillLibrary, ArchivedPrismsPane, PeoplePane |
| `CommandPalette()` | features/search/CommandPalette.tsx | legacy+settings | `<dialog id="search-dialog">`; opens on bus event `open-search` and Ctrl/Cmd+K |
| `OverviewPage/AskPage/ManagementPage/JourneyPage/KnowledgePage/MemoryPage()` | features/legacy/*.tsx | legacy+settings | inner content of `data-tab=overview/ask/management/journey/knowledge/memory` |
| `LegacyDataProvider({children})` | features/legacy/LegacyDataProvider.tsx | legacy+settings | loads the legacy dashboard data (the big Promise.all in `loadDashboard`) on mount and whenever `useApp().refreshKey` changes; shared by the legacy pages, the Connections pane and sidebar counts |
| `LegacyDialogs()` | features/legacy/LegacyDialogs.tsx | legacy+settings | `revision-dialog`, `record-dialog` |
| `SpendingPage()` | features/spending/SpendingPage.tsx | legacy+settings | inside `data-tab="spending"` (+ the topbar "Today's AI cost" value logic from today-prisms.js) |

Cross-feature calls: bus events in `src/lib/events.ts`; sidebar badges via `setNavCount(key, n)` from `@/lib/nav-counts`; Prism list via `usePrisms()`;
page heading via `useApp().setPageHeading`; toast via `useApp().setStatus`; confirm via `useApp().askDialog`.

Testing helper: `src/test/render.tsx` exports `renderWithApp(ui, { app?, prisms? })` that supplies a fake `AppApi`/`PrismsContext`.
Old `window.prism*` globals are re-installed by the shell for the e2e suite only; feature code must not use `window.prism*`.
