# Prism skills and tool access

Prisms are AI employees for any department. Skills describe how they do their jobs; Tools
control which apps and actions they may use.

## Onboarding flow

1. Create a Prism and answer its existing onboarding questions in chat.
2. Confirm its working agreement.
3. Prism creates exactly three role-specific skills from those confirmed answers. There is
   no second questionnaire or skill approval popup.
4. A saved message in the Prism's chat names the three skills and explains that they can be
   edited in Prism settings → Skills. A brief toast also acknowledges creation.

Generation uses the configured Prism LLM and normal usage accounting. Invalid, duplicate or
unavailable model output falls back to three instruction sets covering the agreed work brief,
priorities/recommendations and drafts/reporting. Both paths use the confirmed chat data.
Retries reuse the existing set and do not re-enable disabled skills or duplicate chat notices.

Existing configured skills are preserved. An active Prism that has confirmed chat onboarding
but no assigned skills can use **Create 3 skills from onboarding** on its Skills tab. Prisms
created through an API shortcut without onboarding need to finish chat onboarding or receive
a manually authored skill. No questions are repeated in a popup.

## Skills and Tools are separate tabs

Open Workspace → Prisms → a Prism's settings.

- **Skills** shows enabled counts, access requirements, editable skill cards and the workspace
  library. Edit instructions, rename a skill, or disable it. Private skill edits update this
  Prism's instruction snapshot for its next task and leave other Prisms unchanged.
- **Tools** shows the existing Allowed / Ask first / Off permission controls grouped by purpose.
  Generating or editing skills never changes tool grants, source scope, login policy or budgets.

Skills with missing access show a visible Needs access status and expandable requirements.
Instructions for unavailable skills are withheld from runtime context until their dependencies
are available. Existing runtime authorization and connection checks remain authoritative.

## Privacy and shared skills

Automatically generated skills are private to their Prism. Onboarding can contain private
business details, so generated instructions are not automatically published in the workspace
library or copied into another Prism's context.

Workspace → Skills and Settings → Workspace → Skills manage explicitly shared definitions.
These remain available to other Prisms to enable separately. Editing a shared definition
does not silently change existing approved assignments: each Prism must adopt the new
revision. A private skill can only be edited through its own Prism's settings.

Archived Prisms are read-only. Archiving a shared skill stops its use; restoring it does not
re-enable old assignments. Conflicting edits return a refresh/retry error.

## Boundaries

Skills are instructions, not executable code or integration installers. They cannot grant
tool access, expand Teams sources or bypass approval for messages and external changes.
They guide Teams reviews and computer jobs; deterministic monitoring filters, working
agreements and schedules remain unchanged. External browser approval has the existing
engine limitations documented in the v2.4 runbook.

A Prism can enable eight skills, with up to 2,000 instruction characters per skill. Existing
chat history, memories, skills and permissions are not overwritten by onboarding generation.
Legacy interview endpoints remain available for older API clients; the current UI does not
open that questionnaire.

## Local rollout and verification

Stop the development launcher, run `make migrate`, then restart it and refresh the browser.
Migration `20261122_0048` adds optional ownership to skill definitions; existing shared skills
keep their current permissions and assignments. It follows `20261121_0047`.

Downgrading 0048 removes newly private skill definitions and their assignments before removing
ownership, so private instructions are never exposed as shared definitions. Back up skill data
before any downgrade. Existing shared skill definitions and Prisms are preserved.

Tests in `tests/e2e/test_prism_skills.py` cover generation from chat answers, three-skill
fallbacks, duplicate prevention, private editing and isolation, separate tabs, preserved
permissions, shared library compatibility, and reversible migrations on disposable schemas.
The harness uses synthetic Graph/provider/engine responses and Chrome. No live Teams sends
or browser actions are needed for these checks.

Verified on 2026-11-22: 23 browser/API/migration checks and 23 targeted unit checks passed,
along with type checking, targeted Ruff/format checks, JavaScript syntax checks and
`git diff --check`. Synthetic Skills screenshots were captured in both themes at desktop
and phone widths under `/private/tmp/prism-skills-v2/`. The development database was not
migrated during verification; run `make migrate` before testing the updated application.
