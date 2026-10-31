# ADR 0003: Prism v2.2 multi-Prism boundary

- Status: Accepted
- Date: 2026-10-29
- Owners: Prism maintainer
- Builds on: [ADR 0002](0002-one-manager-conversation.md)

## Context

Prism v2.1 proved a safe manager-agent loop: one web conversation can read bounded Teams evidence,
prepare exact Teams messages, request approval, send once through the connected manager account,
and retain an audit trail. The next product step is not a replacement Teams inbox. It is a private
workspace where the same user can create several specialized Prisms with different responsibilities.

Examples include an Executive Assistant, a Daily Evening Update Prism, a Production Watch Prism,
and a QA Prism. These roles must not mix their instructions, memory, updates, or pending actions.

## Decision

1. `PRISM_V22_ENABLED` defaults to `false`. While false, no v2.2 UI, lifecycle mutation,
   monitoring loop, schedule, notification, or Microsoft Graph activity may activate.
2. v2.2 is local and single-user. Every Prism is private to the configured user. Sharing,
   organizations, and multi-tenant data boundaries are out of scope.
3. Every Prism will have a separately confirmed working agreement, continuing conversation,
   instructions, source policy, triggers, schedules, observations, and memory.
4. Microsoft credentials and provider configuration remain user-level resources. They are never
   copied into a Prism record, prompt, browser state, or notification.
5. Teams chats are readable by default only within the user's existing delegated Microsoft Graph
   access. Optional exclusions must be enforced before content is presented to a model.
6. v2.2 proactive work may read, summarize, recommend, and create an unapproved proposal. It must
   reuse v2.1's exact-payload approval and execution boundary for every external Teams message.
7. Local incremental polling is the required monitoring fallback. Graph webhooks are optional and
   may accelerate detection when a public callback is configured. ngrok is never required for the
   local v2.2 workflow.
8. Browser notifications are best-effort convenience while a Prism page is open. Durable Prism
   conversation updates are the system of record.
9. Similar observations can be clustered to avoid duplicate alerts, but each Prism retains its own
   role-specific interpretation and memory.

## Phase 0 consequences

- Phase 0 exposes only the gated `/api/v2/prisms/foundation` capability contract.
- It adds no tables, migrations, UI navigation, scheduler, monitoring, or external Graph writes.
- The v2.1 Agent workspace remains the active product surface while v2.2 is disabled or incomplete.
- Sanitized fixtures and deterministic clock/scheduler contracts are required before proactive
  monitoring implementation begins.

## Release gate

The v2.2 flag can default to enabled only after the release criteria in
[Prism v2.2 development phases](../v2.2-development-phases.md) are met. Enabling the flag during
development is not evidence that monitoring, notifications, or autonomous behavior are production
ready.
