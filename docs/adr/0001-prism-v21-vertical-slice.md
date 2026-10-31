# ADR 0001: Prism v2.1 vertical slice and safety boundary

- Status: Accepted. Scope partly superseded by [ADR 0002](0002-one-manager-conversation.md).
- Date: 2026-10-28
- Owners: Prism maintainer

## Context

Prism already contains a dashboard, Microsoft delegated authentication, management data, memory,
and scheduled check-in/blocker automation. Prism v2.1 must validate a narrower manager-agent loop
without destabilizing those workflows or prematurely adding every planned Microsoft 365 surface.

## Decision

Prism v2.1 is a feature-flagged, web-first vertical slice. One authenticated manager selects one
Microsoft Teams one-to-one or group chat, requests a review, sees stored progress and evidence,
edits or approves a proposed reply, and sends the exact approved payload through the manager's
delegated Microsoft Graph connection.

`PRISM_V21_ENABLED` defaults to `false`. While false, no v2.1 route, navigation item, background
job, migration-dependent operation, or Graph call may be activated. Existing dashboard and
automation behavior remains unchanged.

The release includes only the capabilities listed in `docs/v2.1-development-phases.md`. Teams
channels, Outlook, scheduling, autonomous writes, multi-user tenancy, and a Teams-resident bot are
separate releases.

## Safety decisions

1. Read authority and write authority are separate.
2. The model produces analysis or proposals; only application services invoke Graph.
3. Approval binds a canonical payload hash covering action type, target chat, recipients, and body.
4. Any edit creates a new revision and invalidates prior approval.
5. Execution revalidates revision, approval, identity, destination, and idempotency immediately
   before Graph is called.
6. Teams content is untrusted input and is always escaped at the browser boundary.
7. Evidence-backed claims refer to stored, sanitized source records.
8. Provider secrets, Microsoft tokens, prompts, and message bodies are excluded from client state
   and application logs.

## Consequences

- The legacy automation remains operational and is not refactored as part of v2.1.
- New v2.1 API and frontend entry points must be registered conditionally.
- Tests use sanitized fixtures and deterministic providers; real Graph and model tests are opt-in.
- Later phases can reuse the job, proposal, approval, execution, and audit primitives for other
  Microsoft 365 surfaces.

## Release gate

The flag may default to enabled only after all Phase 8 acceptance and safety tests pass. Enabling it
locally before then is an explicit developer action, not a production-readiness signal.
