# Prism team organization

Implemented on 20 November 2026. “Prism” and “agent” refer to the same assistant.

The chart uses the saved Prism organization, with the connected Microsoft user's display name
as its root. If no Microsoft name is available it shows “You”.

```text
Yash Mandi
└── Chief of Staff · Leadership
    ├── Sales Prisms
    ├── Marketing Prisms
    ├── Engineering and research Prisms
    └── Other department Prisms
```

Departments are stored on each Prism and shown on its card and in the sidebar filters. A manager
can assign a new Prism to another existing Prism, allowing managers within departments. Prisms
that have not run or been provisioned by the engine still appear in the chart.

## Creating and editing

The Create Prism form includes a job role, department, and reporting manager. Department accepts
the suggested names or a custom name. Chief of Staff is the default manager. When there is no
Chief of Staff, creation offers that role first. Its department is Leadership and its manager
is the user. Each team's non-archived Chief of Staff is unique.

For an existing working Prism, open its chat, then Settings → Profile → Edit role, department &
reporting. The same organization fields are also present in its existing Prism editor. These
records inform onboarding and the instructions used on its next computer run.

Reporting does not automatically launch another Prism, change action approvals, or share private
memories. Those boundaries continue to use the existing workflows.

## Current local assignments

The existing Chief of Staff was reused. These assignments were applied to the local database:

| Prism | Role | Department | Reports to |
| --- | --- | --- | --- |
| Chief of Staff | Chief of Staff | Leadership | Yash Mandi |
| Sales Outreach | Sales Outreach Specialist | Sales | Chief of Staff |
| Market Research | Market Research Analyst | Marketing | Chief of Staff |
| Customer Intelligence | Customer Intelligence Analyst | Customer Success | Chief of Staff |
| Deployment Watcher | Deployment & Engineering Specialist | Engineering | Chief of Staff |
| QA Analyst | QA Analyst | Quality Assurance | Chief of Staff |
| AI ML Researcher | AI Researcher | Research & Development | Chief of Staff |
| ai researcher | AI Researcher | Research & Development | Chief of Staff |
| Delivery Radar | Delivery Coordinator | Operations | Chief of Staff |
| Email Assistant | Inbox Assistant | Operations | Chief of Staff |
| Team Manager | Team Manager | Operations | Chief of Staff |

Finance Monitor remains archived and is omitted from the current chart. It received Finance
metadata without being restored. No Prism was renamed or recreated.

## Persistence and constraints

- `prisms.job_role`: role label, up to 120 characters.
- `prisms.department`: department label, up to 100 characters.
- `prisms.reports_to_prism_id`: nullable foreign key; Chief of Staff's null means the user.
- `prisms.is_chief_of_staff`: unique among non-archived Prisms.
- Organization edits are serialized with a PostgreSQL transaction lock to prevent concurrent cycles.
- Self-reporting, reporting cycles, unavailable managers, and duplicate Chiefs are rejected.
- Role/department/reporting edits and automatic reparenting are audited. Archiving a manager moves
  its reports to Chief of Staff and updates their versions, so stale clients must refresh.
- The Chief of Staff is protected from archival while other non-archived team members remain.
- Engine organization positions do not override this hierarchy.

## Migration and verification

Migration: `20261120_0045_prism_organization.py`, following `20261104_0044`.

The migration adds organization fields, classifies existing roles using deterministic rules, and
reuses the existing Chief of Staff or Executive Assistant. It preserves names, IDs, descriptions,
lifecycle states, and conversations. Existing clients can omit the new fields; new records then
receive inferred roles/departments and default to the existing Chief of Staff.

The migration was exercised on a disposable PostgreSQL schema: upgrade from the previous release,
backfill, downgrade, and re-upgrade. Downgrade removes the new organization metadata, so it should
be reserved for a deliberate rollback; do not use it to reset a working team. No production
downgrade was performed.

Local preservation checks confirmed all 12 original Prism records retained their identities,
descriptions, creation timestamps, and states. Conversation counts and their content digest,
working agreement counts, and memory record counts were unchanged. The resulting team contains
11 non-archived Prisms with exactly one Chief of Staff.

Additional checks:

- Full default suite: 238 passed, 161 skipped (opt-in database/browser suites).
- Disposable PostgreSQL service/API checks: creation persists metadata; organization reads the
  canonical team; duplicate Chiefs and cycles are rejected; archival safely reparents reports.
- Chrome with synthetic APIs: user → Chief → department members, creation payload fields,
  Chief editing controls, and mobile width. Zero uncaught page errors.
- Ruff, JavaScript syntax, and mypy checks on the changed model/schema files passed.

## UI checks

1. Refresh Workspace → Org chart. Confirm Yash Mandi → Chief of Staff → the ten other Prisms.
2. Check each Prism's department badge and the department filters.
3. Open Create Prism. Fill Role and Department; Reports to should default to Chief of Staff.
4. Save a test Prism and complete onboarding; confirm it appears under its selected manager.
5. Open a Prism's Profile and edit its reporting line. Confirm the chart changes after saving.
6. Confirm the original Chief of Staff and other Prism conversation histories are still visible.
