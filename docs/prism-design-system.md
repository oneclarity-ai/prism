# Prism dashboard design system

Updated: 21 November 2026.

Prism's dashboard follows Notion's visual language: a grey sidebar beside a white (or #191919)
workspace, 6px neutral buttons with blue primary actions, 10px menus, a 12px Settings modal, and
quiet hairline rules. This replaces the earlier OpenCode-inspired palette. Prism keeps its own
brand, routes, and manager workflows.

## Shell and navigation

- The sidebar's top row has Chats and Workspace (the active one shows its label) and Search
  at the right edge. Home is retired when Prisms are on; the app opens on Chats. The sidebar has a fixed width (302 layout px, about 270px at the default display size). The top bar and page emoji/logo are retired.
- Workspace sections: Overview (Dashboard, Spending, Run analytics); Work (Tasks, Runs, Approvals,
  Bugs); Team (Prisms); Setup (Target apps, Secrets). The Prisms page has a Cards / Org chart view toggle.
- The profile menu opens upward from the sidebar's account row, as wide as that row: Settings,
  Theme, System status, Log out.
- Settings (`#settings-dialog`) is a native modal over the current page. `window.prism.openSettings(
  subtab)` / `closeSettings()` open it; `setActiveTab("settings")` still works and opens the modal.
  Sections: Account, Preferences, Notifications, General, People, Brain, Archived Prisms,
  Connections, AI provider, Access, Developer. The search box filters sections by name and content.
- Search (`js/command-palette.js`, Ctrl/Cmd+K or the sidebar button) is a dialog with a combobox and
  listbox: Prisms, Workspace pages, Settings sections and rows, quick actions, and chat messages from
  `/api/v2/prisms/search`. Arrow keys move, Enter opens, Escape closes and returns focus.
- Spending (`data-tab="spending"`) is the single cost page: Today / 7 days / month / total for Prism
  and swarm, a breakdown by feature or model, and provider totals.

## Display size

`html { zoom: var(--ui-zoom) }` scales the whole UI: Compact 0.786 (11px body), Default 0.893
(12.5px), Large 1 (14px, the original size). The choice is `prism-pref-ui-size`, applied in
`theme-init.js` before first paint (`window.prismUi`); touch devices (`pointer: coarse`) stay at 1.
Because zoom changes coordinate spaces, follow two rules: write `vh`, `dvh`, `vw` as
`calc(100vh / var(--ui-zoom))`, and divide values from `getBoundingClientRect`, `clientX` and
`innerWidth` by `window.prismUi.zoom()` before using them as CSS pixels (see the profile menu,
sidebar resizer and org chart).

## Browser preferences

`js/theme-init.js` also exposes `window.prismPrefs` (localStorage keys `prism-pref-*`):
`contrast` (system/on/off → `data-contrast`), `enter-newline` (Cmd/Ctrl+Enter sends in Prism chat),
and `notify-approvals` (hides waiting-approval count badges). These are per-browser only.

## Theme ownership

`app/static/prism-theme.css` is the one theme layer. Paired `--ds-*` values define chrome,
workspace, panels, inset surfaces, controls, readable text, focus, selection, and meaningful status.
Existing aliases such as `--bg`, `--callout`, `--text`, and `--tag-green-fg` map to these roles so
legacy and newer features consume the same theme. `styles.css` retains component geometry and
page layouts; its obsolete theme palettes and superseded gradient overrides were removed.

Use existing `.button`, `.mini-button`, `.icon-button`, `.setting-row`, `.workspace-panel`,
`.workspace-table`, `.workspace-status-tabs`, `.tag`, and dialog primitives. Extend those shared
rules before creating a local visual variant. Do not add a feature-specific light/dark palette.

| Primitive | Contract |
| --- | --- |
| Surfaces | Chrome surrounds the workspace; bounded panels use one outline and flat fill; code/segmented tracks use inset fill. |
| Type | Existing local Inter; system sans fallback; monospace for code and machine values; tabular numbers for metrics/tables. |
| Actions | 32px, 6px radius; primary `.button` is blue, `.secondary` neutral with faint edge; destructive actions use danger text. No hover translation. |
| Fields | Visible labels, 36px standard height, readable placeholders, stronger boundary, shared blue focus outline. |
| Selection | Neutral filled sidebar rows; thin horizontal tab underline; raised segment inside a recessed filter track; checked controls show position/check. |
| Status | Words and existing icons remain visible alongside color. Pending, failed, sent, rejected, and unconfirmed delivery remain distinct. |
| Tables | Raised header, flat rows, faint rules, right-aligned numeric columns, full task names; scrolling stays within the table wrapper. |
| Menus | Opaque fill, one outline, soft shadow, grouped rows; theme submenu shifts/flips into available viewport space. |
| Dialogs | Native focus containment and Escape; shared controls and footer alignment; focus returns to the origin. |
| Feedback | Quiet bounded loading, brief status announcements, persistent inline errors, readable unavailable and disabled states. |

Spacing uses a 4px base rhythm. Existing page layouts determine when a supporting rail is useful;
the shared system does not force a rail into conversations or settings. Panels use 8px corners,
controls 6px, floating menus 10px, dialogs 12px, with 1px borders. Touch controls expand under
`pointer: coarse`. Reduced motion removes nonessential animation and transitions.

## Theme preference and keyboard behavior

`app/static/js/theme-init.js` executes in the document head before stylesheets. It resolves the
existing `manager-agent-theme` preference and sets both `data-theme` and native `color-scheme`.
Explicit Light and Dark persist; System removes the explicit override and follows OS changes.
Storage errors leave a working in-memory preference. Storage events synchronize other open tabs.

Theme changes update tokens without rerendering the page, keeping drafts, selections, and scroll
containers. The Settings selector and profile submenu reflect the same preference. The profile
menu supports Enter/Space, arrow navigation, Home/End, nested-menu arrows, Escape, Tab dismissal,
and focus return. Settings tab lists support arrows and Home/End with a roving tab stop.

Primary blue is `#1C73CC` in both themes (white text 4.8:1; Notion's `#2383E2` measures only 3.9:1).
Focus rings use `#2383E2` light / `#4C9CED` dark. Token pairs were checked for 4.5:1 text and 3:1
focus/boundary contrast. Quiet panel rules stay subtle; text input edges and unchecked switch
boundaries use a stronger neutral (`--ds-control-edge`), while button edges follow Notion's faint rule.

## Surface inventory

| Existing dashboard surface | Shared treatment and retained behavior |
| --- | --- |
| Home/overview | Legacy (Prisms off) only; with Prisms on it redirects to Chats. Cost moved to Spending. |
| Prisms | Directory, create/edit dialogs, role/department/reporting controls, onboarding and private conversation. |
| Assistant/Prism chat | Composer, evidence, review details, exact-destination draft cards, edit/reject/regenerate/approve controls. |
| Work and approvals | Unified run cards, status, action approvals, navigation back to the owning Prism. |
| Workspace | Dashboard, Spending, Run analytics, Tasks, Runs, Approvals, Bugs, Prisms (Cards / Org chart), Target apps, Secrets. |
| Computer/QA | Plan, screen, URL, limits, steps, files, login/outward-action approvals, result and unavailable states. |
| Settings (modal) | Account, Preferences, Notifications, General, People, Brain, Archived Prisms, Connections, AI provider, Access, Developer. |
| Legacy gated views | Ask, management, journeys, knowledge, memory retain their markup/events and consume the same aliases. |

Feature flags and API behavior are unchanged. No schema changes, credential changes, real Graph
sends, engine actions, or migration are required for this visual update.

## Verification

Use the existing scratch-schema Chrome harness with fake Graph/model/engine boundaries:

```bash
PRISM_DESIGN_CAPTURES=/private/tmp/prism-design-system RUN_E2E=1 \
  .venv/bin/pytest -q tests/e2e/test_design_system.py
```

The matrix covers both themes at 1440px desktop, 900px tablet, 390px phone, and 320px small-screen
widths, plus 720px reflow (the CSS viewport of a 1440px window at 200% zoom). This checks reflow,
rather than automating Chrome's browser-toolbar zoom control. Captures include overview,
Teams approvals with expanded evidence, Settings with keyboard
focus, Workspace tables/empty states, menus, dialogs, loading, unavailable, failed, and uncertain
delivery. It checks document overflow and measures text-token contrast against workspace, panel,
inset, and selected surfaces; focus uses a 3:1 threshold and normal text uses 4.5:1.

Additional existing journeys exercise exact-text send/edit/reject and independent approvals,
reconnect/permission/throttling, hostile content, no duplicate sends, Prism onboarding, People,
and computer action approval. The E2E Graph fake now accepts the optional signature parameter
already supported by the real client; production sending rules were not changed.

See the latest entry in `design-qa.md` for executed checks, reviewed captures, and remaining limits.
The test matrix is not a claim of complete WCAG conformance or of a live Microsoft/Docker run.
