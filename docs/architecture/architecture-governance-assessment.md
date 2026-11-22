# Architecture governance assessment

Assessment-mode pass over this repo using the method from
[MercatorProj/codebase-architecture-governance](https://github.com/MercatorProj/codebase-architecture-governance)
(an agent-skill methodology for module boundaries, ownership, and dependency direction —
not a linter or CLI; see that repo's `SKILL.md`). Read-only: nothing in the source tree was
changed to produce this. Scope: `apps/prism` (primary, actively developed) with a short note on
`apps/swarm`. Facts below are labeled confirmed (grep/line-count evidence quoted) or `likely`
(inferred, not fully traced); nothing here is a hypothesis presented as fact.

## 1. Executive diagnosis

`apps/prism`'s backend is **well organized at the folder level**: `app/services/<domain>/`,
`app/models/<domain>/`, `app/schemas/<domain>/`, `app/api/routes/<domain>/` each split along the
same eight domains (`engine`, `llm`, `management`, `memory`, `people`, `prisms`, `qa`, `teams`),
with a small, genuinely shared kernel (`services/common.py`, `services/errors.py`,
`models/enums.py`, `schemas/common.py`, `routes/health.py`) exactly as `AGENTS.md` §3 describes.
Layering direction is clean (confirmed): no file under `app/models` or `app/schemas` imports
`app.services`, and no file under `app/services` imports `app.api`.

Two real issues this pass found, both **structural, not bugs**:

- **Three circular service-domain dependencies** (confirmed): `management` <-> `prisms`,
  `teams` <-> `prisms`, `engine` <-> `qa` each import each other. Dependency direction between
  these domains is currently undefined.
- **A handful of oversized, single-class service modules** that bundle more than one concern
  (confirmed by method-prefix evidence below), the most significant being
  `services/management/response_service.py` (2929 lines, one class, 38 methods).

> **Update:** the dashboard has since been rewritten as React + TypeScript under `apps/prism/frontend` with one
> folder per feature (`src/features/*`). The frontend findings below describe the pre-rewrite `app/static/js/` layout.

The static dashboard (`app/static/js/`) has no equivalent domain/feature split — it is 24 flat
files, four of them 1,100+ lines, with all page wiring for a given area living in one file
(`likely`: no module boundary enforcement exists there beyond file naming).

Nothing below recommends deleting or renaming by itself. This is the assessment + plan
(governance skill phases 1-8); implementation (phase 9 / "Implementation mode") still needs
explicit sign-off per file, especially for the oversized files, which have real behavior riding
on them (audit records, deterministic send policy, Teams token handling).

## 2. Current-state module map

| Module | Responsibility | Depends on (same layer) | Confidence |
| --- | --- | --- | --- |
| `services/management` | Response policy/decisions, automation scheduling, project/blocker/commitment workflows | llm, memory, people, prisms, teams | confirmed |
| `services/prisms` | Prism lifecycle, org chart, skills, runs, onboarding, agent state | llm, management, memory, qa, teams | confirmed |
| `services/teams` | Microsoft Graph client, token handling, directory sync | memory, prisms | confirmed |
| `services/qa` | QA-tester Prism runs, swarm client bridge | engine, llm, memory, prisms | confirmed |
| `services/engine` | Swarm/computer bridge (HMAC, work bridge) | memory, prisms, qa | confirmed |
| `services/people` | Employee directory, org import | memory, prisms, teams | confirmed |
| `services/memory` | Temporal facts/episodes/relations, consolidation | *(none — leaf domain)* | confirmed |
| `services/llm` | Provider adapters, BYOK credentials, usage accounting | *(none — leaf domain)* | confirmed |
| `services/common.py` + `errors.py` | Shared Employee/Project lookups, typed `DomainError`s | imports `models.management.Project`, `models.people.Employee` directly | confirmed, low-risk |

`memory` and `llm` are the two genuinely dependency-free "leaf" domains other services build on —
they are the closest thing this backend has to the governance skill's `domain/core` layer.
`management` and `prisms` are the most central/connected domains, which tracks with the product
(§1 of `AGENTS.md`: a Prism *is* a management agent with continuing conversations).

## 3. The three circular dependencies (confirmed, evidence)

```
management -> prisms   (app/services/management/*.py imports app.services.prisms.*)
prisms     -> management (app/services/prisms/*.py imports app.services.management.*)

teams  -> prisms
prisms -> teams

engine -> qa   (engine/*.py: "from app.services.qa import qa_run_service")
qa     -> engine
```

None of these are *import-time* circular-import errors (the app imports and every test suite
passes), so each pair imports specific submodules/functions, not each other's package `__init__`
during module load. The issue is architectural, not a crash risk: two domains each treat the
other as a dependency, so "which one owns the relationship" is undefined, and a change in either
can ripple into the other with no enforced boundary.

`likely` root cause per pair (not fully traced call-by-call — flag as `needs investigation` before
acting):
- `management` <-> `prisms`: a Prism's conversation review needs management policy, and
  management automation needs to look up which Prism a conversation belongs to.
- `teams` <-> `prisms`: Prism replies go out over Teams, and Teams reply processing needs to
  resolve which Prism owns a given chat.
- `engine` <-> `qa`: the swarm bridge needs to inspect/trigger QA runs, and QA run service needs
  the bridge's HMAC/webhook plumbing.

This may be intentional, accepted coupling (ADR 0003 covers multi-Prism boundaries) rather than
an oversight — flagging it as a **dependency-rule gap to decide on**, not a defect to fix blindly.

## 4. Oversized / multi-concern modules (confirmed)

| File | Lines | Shape | Note |
| --- | --- | --- | --- |
| `services/management/response_service.py` | 2929 | 1 class, 38 methods | Method name prefixes span `safe_*` (9), `normalize_*` (4), `validate_*` (2), `process_*` (2), `send_*` — sanitization, validation, decision-making and sending look mixed into one class. Highest-value split candidate. |
| `services/qa/qa_run_service.py` | 1890 | 1 class (`QaRunService`) + a few module-level helpers | Single class carries the whole QA run lifecycle. |
| `services/teams/microsoft_service.py` | 1303 | **5 classes already** (`TokenCipher`, `MicrosoftGraphClient`, `MicrosoftDirectoryService`, `MicrosoftService`, a private HTML parser) | Already internally decomposed; large because it bundles a cohesive Graph-integration surface, not because responsibilities are tangled. Lower priority than the two above. |
| `services/management/conversation_review_service.py` | 1060 | 1 class + 1 small schema | Single-responsibility-looking (review a conversation); large mainly from prompt/context assembly. |
| `agents/management_agent.py` | 952 | 29 top-level defs | Not reviewed in depth this pass — flagged `needs investigation`. |

`services/common.py` importing `models.management.Project` and `models.people.Employee` directly
is a **minor, low-risk** shared-kernel finding (the governance skill's rule 8: shared code may only
depend on stable lower-level primitives). In practice `Employee`/`Project` are foundational
cross-cutting entities, not optional feature modules, so this reads as acceptable as-is — noted,
not actioned.

## 5. Frontend (`app/static/js/`, confirmed by line count)

```
agent-chat.js        2187
app.js                1393
prism-directory.js    1351
qa-tester.js          1138
operations.js          383
workspace-pages.js     335
command-palette.js     323
...                 (17 more files, all <310 lines)
```

24 flat files, no folder-level feature boundary. `app.js` in particular now does bootstrap,
settings-dialog wiring (including the just-added AI-provider BYOK UI), setup/connections,
provider status, and dashboard loading all in one file. The governance skill's illustrative
frontend target (`app/`, `features/<capability>/`, `application/`, `shared/{ui,api,contracts,utils}`)
is explicitly "illustrative, not a required migration target" — and this is static ES modules
with no bundler (`AGENTS.md` §2: "no Node package or frontend build pipeline"), so a literal
`features/` folder split would need either a lot of `<script type="module">` tags kept in sync by
hand or a build step this project has deliberately avoided. **Lower priority than the backend
findings**; worth a plan only if the user wants it.

## 6. Dependency rules (proposed, for discussion — not yet enforced anywhere)

| Rule | Status today |
| --- | --- |
| `models`/`schemas` never import `services` | holds (confirmed, 0 violations) |
| `services` never import `api.routes` | holds (confirmed, 0 violations) |
| `services/common.py`, `services/errors.py` depend only on stable primitives | mostly holds (Employee/Project exception, judged acceptable) |
| `memory` and `llm` are dependency-free leaf domains | holds (confirmed) |
| No two domains import each other | **violated** by management<->prisms, teams<->prisms, engine<->qa |

## 7. Proposed phased plan (plan only — needs sign-off before any batch starts)

1. **Batch 0 (no code change):** decide, per cyclic pair, which domain should own the
   relationship (or accept it as a documented exception, e.g. in ADR 0003). This alone resolves
   §3/§6 without touching a line of code.
2. **Batch 1 (low-risk, additive):** split `response_service.py`'s sanitization/`safe_*` and
   `normalize_*` helpers into a new `services/management/response_sanitizer.py` (pure functions,
   easy to unit test in isolation), with `ResponseService` calling into it. No behavior change if
   done as a pure extract.
3. **Batch 2 (low-risk, additive):** similarly extract `qa_run_service.py`'s activity-text/summary
   helpers (already partly separated as `_Answer`/`_Summary`/`_WorkSummary` classes) from the run
   orchestration itself.
4. **Batch 3 (needs investigation first):** `management_agent.py` and
   `conversation_review_service.py` — read in full before proposing a split; not enough evidence
   yet to say they need one.
5. **Batch 4 (only if asked):** frontend module split. Given the no-build-step constraint, this
   would need its own design discussion (plain `<script type="module">` imports vs. introducing a
   minimal bundler) before a plan is worth writing.

Each batch: add/confirm tests around the extracted behavior first, extract with no logic change,
run `make check`, diff-review, then move on. Exactly the governance skill's batch template.

## 8. Behavioral invariants to preserve

Per `AGENTS.md` §6: deterministic policy validation and audit records in the response/decision
path, bounded retries, Fernet-encrypted credentials, constant-time webhook validation, exact
approved-destination/text sends. Any extraction from `response_service.py` must not change what
gets sent, logged, or audited — only where the code that decides it lives.

## 9. Validation plan

`make check` (lint, format, mypy on core/models/schemas, offline tests, secret scan) after every
batch; `RUN_DB_TESTS=1 make test-integration` for anything touching `management`, `prisms`,
`teams`, or `qa` persistence; targeted `pytest` on the specific service's existing test file
before and after each extraction to confirm no behavior drift.

## 10. Unknowns / needs investigation

- Exact call sites causing each of the three cycles (traced to package level, not function level).
- Whether `management_agent.py` and `conversation_review_service.py` are single-responsibility-but-
  long, or actually multi-concern — not read in full this pass.
- `apps/swarm/backend` was only skimmed: flat `app/{api,services,schemas,db/models}` (no
  per-domain split), largest file `runtime/openai_agents.py` at 1037 lines. Given it is a smaller,
  single-product codebase treated as an external engine (`AGENTS.md` §3-4), forcing Prism's
  per-domain convention onto it is **not** recommended by the governance skill's own rule 14
  ("fit the repository") unless it grows substantially — noted, not assessed further.

## Bottom line

This repo already follows the shape the governance skill asks for at the backend-folder level;
it was not disorganized. The concrete gaps are the three cross-domain cycles (a decision, not a
rewrite) and a short list of oversized service files (safe to extract from incrementally). No
action has been taken yet — this is the assessment and proposed plan only.
