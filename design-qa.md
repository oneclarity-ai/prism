# Workspace interface QA

Date: 20 November 2026

## Findings

No actionable P0/P1/P2 findings remain in the checked layouts and interactions.
The scope is the swarm interface inside Prism's existing theme, rather than the swarm's purple
palette or separate application shell. This is the user's explicit visual requirement.

## Visual sources and comparison

- Source visual truth: the ten images attached to the Workspace request in this conversation,
  plus the earlier Organization chart reference. These attachments are not repository files.
- Source images: sidebar 442 × 1190; page images normalized by the conversation viewer to about
  2048 × 942–1027 from about 2940 × 1352–1472. Original device pixel ratio is not specified.
- Implementation: Google Chrome, 1440 × 1000 CSS pixels, device scale factor 1; mobile 390 × 844,
  device scale factor 1. Both light and dark Prism themes were rendered.
- Captures: `/private/tmp/prism-workspace-qa/overview.png`, `tasks.png`, `runs.png`,
  `approvals.png`, `bugs.png`, `agents.png`, `positions.png`, `targets.png`, `secrets.png`,
  `usage.png`, `light.png`, and `mobile.png` in that same directory. These are temporary
  session artifacts containing synthetic data only.
- Full-view comparison: reviewed the captures against the attached references for sidebar group
  order, dashboard grids, table columns, date groups, approval tabs, bug columns, agent cards,
  setup inventories, and usage panels. The existing Prism shell and theme are intentional.
- Focused-region comparison: reviewed navigation active states, task/run filters and row density,
  agent card headers/footers, secret masking, chart controls, and approval controls. Small controls
  are readable in the 1440-pixel captures. Source density is unspecified, so this review does not
  claim an exact pixel-difference score between the images.

## Required fidelity surfaces

| Surface | Review |
| --- | --- |
| Typography | Uses Prism's existing local Inter font, compact 12–14px controls, 28px workspace titles, 28px metrics, and existing fallbacks. Ellipsis preserves long row labels. This retains the requested Notion hierarchy. |
| Spacing/layout | Grouped Workspace sidebar; four dashboard metrics; two dashboard panels; three-column agent cards; date-grouped runs; three-column bug details; six usage metrics; responsive grids and table scrolling. |
| Colors/tokens | Existing `--bg`, `--sidebar`, text, border, input, button, and semantic colors. No theme or global button-color replacement. Department accents remain small markers and chart edges. |
| Assets | Retains Prism's existing branding and page-heading emoji convention. Navigation and controls use the same official Lucide icon family as the swarm source, copied with its ISC license. Charts render actual data. No generated raster assets are needed for these interfaces. |
| Copy/content | Uses live API fields in the implementation; only the isolated browser run supplies synthetic records. Page titles, columns, counts, filters, and form labels correspond to their sections. |

## Comparison and correction history

1. **P2, active navigation:** the initial section-state attribute collided with sidebar selectors.
   Renamed the section attribute; Chrome verifies exactly ten navigation buttons and one active
   page entry after switching pages.
2. **P2, narrow tables:** the first mobile capture compressed secret names to only a few letters.
   Set a minimum table width and kept scrolling inside the table wrapper. Rechecked document and
   sidebar overflow across all ten pages at 390 CSS pixels.
3. **P2, org controls/state:** ensured node controls extend below cards, ResizeObserver is cleaned
   up when leaving the chart, and dragging stops after releasing the pointer. Verified pan, zoom,
   fit, department dimming, and collapse/expand in Chrome.
4. **P2, navigation context:** run details now select Runs and its heading; department active
   styling is limited to Organization. Verified run detail/back navigation and the final page captures.

## Interaction and engineering verification

- All ten pages rendered through the real static dashboard modules with intercepted synthetic APIs.
- Verified task search, list/board switching, task form submission, secret creation and masking,
  run details/back, approval confirmation and Approved history, org interactions, and mobile overflow.
- Chrome reported zero uncaught page errors in the final run.
- API regression/security suite: `pytest -q tests/test_operations.py tests/test_security.py`:
  **7 passed**. Coverage includes input allowlists, blocked arbitrary actions, feature gates,
  analytics bounds, sensitive-field removal, and existing artifact/event protections.
- Ruff checks and formatting passed for the changed Python components; JavaScript syntax checks
  passed for the changed modules; mypy passed for the new Workspace schemas.
- The browser used synthetic data and intercepted mutations. Live engine saves, real approval
  execution, actual secrets, and PostgreSQL integration were not exercised.

## Expected differences and follow-up polish

- Prism's theme, branding, emoji headings, and Create Prism flow remain the intended shell.
- New task saves a task without starting a run; computer work still starts through a Prism.
- Bug email/Jira/manager integrations are unfinished in the swarm source. Matching controls are
  explicitly disabled here; Open run and existing approved bug workflows remain available.
- Tests used a small synthetic organization; very large real organizations may need further
  chart spacing and pagination work. Task/run tables currently show the latest 200 records.
- No unresolved clarification is required for this implementation.

## Implementation checklist

- [x] Grouped Workspace sidebar and department navigation.
- [x] Corresponding page layouts using Prism theme tokens.
- [x] Filters, tables, cards, setup dialogs, and usage chart.
- [x] Existing approval/security boundaries preserved.
- [x] Desktop/mobile Chrome checks and focused Python checks.
- [x] README updated with behavior and limits.

## Organization membership update

The user's subsequent requirement takes precedence over the original seeded organization screenshot:
Prism and agent are the same user-created assistant. Organization now uses the canonical Prism
directory, includes drafts and paused Prisms, excludes archives and standalone engine agents, and
projects existing reporting links between the remaining Prisms. A card opens its Prism conversation;
Create Prism replaces Add position. Unassigned Prisms appear as roots without invented managers.

Regression validation: `pytest -q tests/test_prism_organization.py tests/test_operations.py`:
**5 passed**. The optional Node-based UI projection test covers renamed/ambiguous identities,
archives, duplicate positions, omitted ancestors, unprovisioned Prisms, and cyclic links. The focused
Chrome check rendered exactly three synthetic owned Prisms, retained their reporting edge and
pan/zoom, and excluded seeded positions. Capture: `/private/tmp/prism-owned-org.png` (1440 × 1000,
device scale factor 1). No live data or external mutations were used.

## AI employee team update

The newest requirement adds the connected user as the one human root, followed by the saved
Chief of Staff Prism and the department Prisms. The canonical source is now persisted role,
department, and reporting metadata on Prism records, rather than engine organization positions.
This supersedes the earlier owner-free organization membership projection.

- Chrome synthetic check: root Yash, one Chief of Staff, department members, creation form fields
  and payload, Chief editing constraints, mobile width, and zero uncaught page errors.
- Captures: `/private/tmp/prism-team-hierarchy.png` and `/private/tmp/prism-team-create.png`,
  both at 1440 × 1000 CSS pixels, device scale factor 1. Visual inspection confirmed the existing
  Prism theme, user/Chief/member order, department badges, and the new form controls.
- Migration checks: complete disposable-schema upgrade, backfill, downgrade, and re-upgrade.
  Separate PostgreSQL API/service checks cover persistence, duplicate Chiefs, reporting cycles,
  archived managers, and reparenting after archival.
- Local migration applied and verified: 12 original identities/history preserved, 11 non-archived
  Prisms, one reused Chief of Staff, and the existing ten members assigned under it. The saved
  owner display name is Yash Mandi.
- Full default suite: 238 passed, 161 skipped. Ruff, JavaScript syntax, and targeted model/schema
  mypy passed. See `docs/prism-team-organization.md` for applied assignments and manual UI checks.

final result: passed

## OpenCode-inspired platform theme and Settings update

The nine OpenCode screenshots attached in the conversation are the visual reference. Prism keeps
its existing sidebar and navigation, as the user clarified. The shared theme now uses compact
neutral controls, tighter radii, a dark palette near the reference, and a matching light palette.
The Settings page uses an internal navigation column and grouped cards; the current Prism settings
remain available. The top-right profile menu exposes Account settings, Workspace settings, Theme,
System status, and Sign out. Local development has no sign-in session to end; Sign out only clears
an operator access key when one is stored in that browser.

Chrome captures with synthetic data were reviewed at 1280 × 900 CSS pixels: General Settings in
dark mode, Usage in dark and light modes, and the profile menu in light mode. The compact controls,
card surfaces, two-column Settings layout, and profile menu match the requested direction. The
first General capture caught the existing tab fade while it was still running; the settled capture
was reviewed. A navigation path from General to Usage initially left provider totals unloaded;
the shortcut now invokes the same subtab action as the Settings navigation. Provider totals now
come from a database aggregate, so they are not truncated by call pagination.

Focused checks: Chrome Settings/profile/usage and People journeys passed at desktop and phone
widths (4 tests); Prism conversation journeys passed (4 tests). The provider aggregate passed a
PostgreSQL test using the disposable test database. Ruff, Python formatting, JavaScript syntax,
and diff whitespace checks passed. The browser run used synthetic usage and did not verify a live
Azure invoice. The swarm's upstream model provider is not recorded by Prism, so its tracked total
is labeled separately instead of attributing it to a provider without evidence.

## Shared design system implementation — 21 November 2026

This entry supersedes earlier palette and Notion-theme notes. The latest user brief specifies
OpenCode's neutral hierarchy as a reference while retaining Prism's own navigation, assets,
composition, and workflows. It also supplies derived light treatments and accessibility targets.

### Source and implementation evidence

- Source visual truth: the nine screenshots attached to the latest design-system request
  (Activity dark/light, Go, Models, Providers, Controls, Settings, Account, nested account menu).
  They are conversation attachments, not files in this repository. Displayed source dimensions
  range from 820 × 728 for the menu to about 2047 × 1020 for wide views; density is unspecified.
- Implementation: Google Chrome, device scale factor 1. Desktop 1440 × 960, tablet 900 × 960,
  reflow 720 × 960, phone 390 × 844, small screen 320 × 844. These captures are CSS pixels and
  contain only the project's synthetic records and messages.
- Capture directory: `/private/tmp/prism-design-system/`. Representative final captures include
  `approval-dark-1440.png`, `approval-light-390.png`, `settings-dark-900.png`,
  `settings-light-320.png`, `workspace-runs-dark-1440.png`, `workspace-runs-light-1440.png`,
  `menu-dark-900.png`, `menu-light-390.png`, `loading-1280.png`,
  `unavailable-light-390.png`, and `delivery-states-dark-1280.png`.
- Full-view comparison: inspected the rendered approval, Settings, Runs, and menu captures against
  the supplied reference's neutral chrome/workspace/panel hierarchy and compact controls. This is
  a different product composition and content, so a pixel-difference score or exact layout clone
  would be misleading. No source-resolution dimensions were presented as CSS measurements.
- Focused comparisons: menu and theme submenu surfaces/focus/checkmark; table header, numeric
  alignment, badge and row separation; approval textarea, evidence excerpt and action controls;
  mobile Settings labels/control stacking. Light views extend the supplied Activity light hierarchy.

### Required fidelity surfaces

| Surface | Result |
| --- | --- |
| Typography | Existing local Inter and system fallback retained; 14px body/controls, 12px metadata, 16px sections, 20px page headings, tabular metrics and numeric cells. Task names wrap; evidence remains readable. |
| Spacing/layout | 4px rhythm, neutral 6px controls, 8px panels, 12px menus, 14px dialogs; existing Prism layout retained. Settings stacks at narrow widths. Horizontal overflow is confined to table/code containers, with visible parent containers checked separately. |
| Colors/tokens | One semantic palette and compatibility aliases. No decorative control gradients or card hover translation. Dark chrome/workspace/panels use #080808/#161616/#242424; light uses #FAFAFA/#FFFFFF/#FAFAFA. |
| Assets | Prism's current logo, icons, avatars, and navigation assets retained. No new raster artwork or replacement illustrations were necessary. |
| Copy/content | Existing Prism text and destination/content disclosures retained. Status uses words alongside color. No reference-product pricing, account features, or branding was imported. |

### Findings and correction history

1. **P1 — competing palettes and saturated controls.** Replaced overlapping theme overrides with
   paired semantic tokens. Removed legacy theme declarations and superseded gradient overrides.
   Final dark/light views show stable neutral controls and flat reading panels.
2. **P2 — sampled dark error text on selection.** Automated measurement found only 4.05:1 for
   #F17471 over #3A3A3A. Adjusted the dark error token to #F88784. Dark links use #9BB0FF while
   the focus ring remains #6A8FFF. The final matrix passes text and focus contrast thresholds.
3. **P2 — menu keyboard and viewport behavior.** Added menu/submenu arrow traversal, Home/End,
   Escape, correct theme radio state, focus return, and viewport-aware placement. Narrow menus
   shift inward; desktop submenus open to the available side. Final captures show an opaque layer
   with a visible focus ring/checkmark. Settings tabs now use a roving tab stop and arrow keys.
4. **Verification fixture mismatch.** Existing Graph E2E fake lacked the real client's optional
   signature argument, causing successful-send tests to report Failed. Corrected only the fake's
   signature; production approval and Graph execution code did not change. All affected journeys
   then passed, including edited exact sends and duplicate-click protection.
5. **P2 — remaining feature-specific visual overrides.** Normalized Workspace heading size,
   approval textarea corners, readable inactive/rejected text, and bounded loading presentation.
   The final matrix and post-fix captures passed after these changes.

### Executed checks and practical limits

- Chrome regression invocation: **54 passed**, covering design-system states, source/evidence
  disclosure, exact send/edit/reject, independent approvals, failure recovery, XSS-safe rendering,
  Prism onboarding, People, and computer/QA approval behavior through fakes.
- Final design matrix after the last visual refinements: **10 passed**. Both themes, five widths,
  parent/document overflow, pending/failed/unconfirmed states, loading/unavailable, keyboard send,
  native dialog Escape/focus return, OS preference changes, persistence, and menu placement passed.
- Dashboard and operator security checks: **5 passed**. Targeted Ruff/format checks, JavaScript
  syntax checks, and diff whitespace checks passed. Chrome emitted no uncaught JavaScript errors
  in the approval matrix. Existing Starlette/httpx deprecation warning remains unrelated.
- Source/token contrast checked on workspace, panel, inset, and selected surfaces: normal text
  requires 4.5:1, focus cues 3:1. Placeholders, disabled explanations, and inactive copy use readable
  semantic roles. This is a focused accessibility check, not a complete WCAG certification.
- The 720px layout tests reflow equivalent to a 1440px window at 200%; Chrome toolbar zoom and
  assistive-technology announcements were not manually audited. Legacy gated views share the
  aliases and static dashboard checks; full legacy browser journeys were not rerun.
- Live Graph delivery, live Docker streaming, production billing, and external website actions were
  not performed. All approval/action verification used synthetic fixtures.

### Implementation checklist

- [x] One paired token layer and legacy aliases.
- [x] Shared controls, panels, fields, tables, charts, menus, dialogs, feedback and focus states.
- [x] Early theme initialization, System preference, native color scheme and stored-key compatibility.
- [x] Existing manager/approval/feature boundaries retained.
- [x] Desktop/tablet/mobile screenshots and keyboard/contrast/reflow verification.
- [x] Authoring guide, README and changelog updated.

No actionable P0/P1/P2 visual findings remain in the reviewed surfaces. The manual accessibility
checks above are recorded as remaining verification limits.

final result: passed

## Notion-style redesign — 21 November 2026

Supersedes the OpenCode palette above. The latest request asks for Notion's color theme, sidebar
(Chats, Workspace with Home moved inside, Search at the right edge), Settings as a modal with extra
sections, a single Spending page, Notion button/dialog rounding, and a Notion-style profile menu.

- Source visual truth: four Notion screenshots attached to the request (top icon row active/inactive,
  Preferences modal, account dropdown). They are conversation attachments, not repository files.
- Implementation checked in Google Chrome at 1440 × 900 and 390 × 844 CSS pixels, both themes, against
  stubbed synthetic APIs (no database, Graph, or engine). Captures are temporary session files.
- Verified by script: switch order Chat < Workspace < Search; legacy Home hidden in Prisms mode;
  settings modal opens from gear/menu, Escape closes and returns focus to the trigger; settings search
  filters sections; High contrast, notification-badge and Enter-newline preferences apply; profile menu
  keyboard (open, nested theme menu, Escape, focus return); Spending totals render and persist across reload;
  primary buttons render `rgb(28, 115, 204)`; no uncaught page errors in any capture.
- Bug found and fixed during verification: rebuilding the Settings nav dropped `#nav-brain-count`,
  which made Brain's render throw ("Cannot set properties of null (setting 'hidden')").
- Token contrast (script): text pairs ≥ 4.5:1 and focus / control edge / switch ≥ 3:1 in both themes
  after adjusting light success `#0B6E60`, light error `#B32F26`, dark secondary `#A0A0A0`, dark success `#58B7A6`.
- Not run: Playwright e2e suite (paused by the user); the three e2e files that touched the profile menu
  and Settings were edited for the new structure but not executed. No live Graph, engine, or database.
- Known tradeoff: Notion's blue `#2383E2` fails 4.5:1 with white text, so Prism uses `#1C73CC`.
