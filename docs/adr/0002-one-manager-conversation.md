# ADR 0002: One manager conversation with disclosed multi-source scope

- Status: Accepted
- Date: 2026-10-29
- Owners: Prism maintainer
- Supersedes: the "one selected Teams chat" scope in ADR 0001. Its safety decisions still apply.

## Context

ADR 0001 shipped a selected-source baseline: the manager picked one Teams chat, and each chat
became its own Prism thread. That proved the approval, execution, and audit boundaries, but it
made Prism look like a second Teams inbox and could not answer "what needs my attention across the
release team?".

## Decision

1. The manager has **one** continuing Prism conversation. Teams people and groups are sources and
   destinations attached to jobs, evidence, and actions. They are never navigation-level chats.
2. Every job records the scope the manager requested (`auto`, `person`, `chat`, `explicit-set`)
   and the sources Prism actually used, with a rationale. The UI shows both as source chips and a
   "Why these sources" view on every answer.
3. The source filter defaults to **Auto** and only constrains requests when the manager sets it.
   Ambiguous names produce a clarification, never a guessed chat.
4. One request can produce several action cards in a coordinated plan. Each card keeps its own
   exact payload hash, approval, idempotency key, and delivery state. Bulk approval is available
   only while every exact payload is visible.
5. Reading or resolving a source never grants write authority. Every destination is explicit on its
   own approval card.
6. History stays one list: day and topic separators, search, and "load earlier" navigate it without
   turning past topics into separate chats. Pre-existing selected-source threads were merged into
   the canonical conversation and keep resolving through aliases.
7. Failures that need the manager's action (Microsoft reconnect, missing permission, throttling,
   unconfirmed delivery) are shown with a specific next step and never imply a message was sent.

## Consequences

- Old per-chat deep links redirect to the canonical conversation.
- The release gate includes a browser journey at desktop and phone widths on a scratch schema
  with fake Graph and model providers (`make test-e2e`), and a migration and rollback test from the
  Phase 8 database shape.
- A private Teams bot, channels, mail, and calendar remain out of scope for v2.1.
