Prism should evolve into a persistent, approval-first manager agent—not be rewritten from scratch. The existing management records, memory, Microsoft OAuth, webhooks, audit trail, and safety policies are valuable foundations. The missing layer is a general agent runtime capable of understanding goals, using multiple Microsoft tools, showing progress, and proposing actions for approval.

I’m treating “OneClarity” as Prism.

## Agreed Prism v2.0 product direction

Prism v2.0 will be:

- One manager agent coordinating multiple employees.
- Local and single-manager.
- Web-first: the manager talks to Prism, follows progress, and approves actions in the Prism web
  app.
- Microsoft Graph for reading work context and executing approved actions through the connected
  manager account.
- No cloud computer or browser automation.
- Able to read Teams, Outlook email, and calendars.
- Able to draft replies, coordinate employees, schedule meetings, and update Prism tasks.
- Required to obtain manager approval before externally visible actions.
- Conversational, context-aware, and capable of showing ongoing work.
- Designed for multiple model providers through BYOK.

The Prism web app is the v2.1 manager-facing control plane. It provides one continuing conversation
with the manager agent, receives natural-language requests, resolves relevant work sources, shows
job progress, and presents inline approval controls. Microsoft Graph is the action plane: it reads
explicitly authorized work conversations and performs only the exact actions the manager approves,
using the connected manager’s Microsoft identity. Teams people, groups, and channels are sources
and destinations—not separate Prism chats. Employees remain in their normal Teams conversations
and do not need to install or operate Prism.

A private Prism app inside Microsoft Teams is intentionally deferred to a later Prism v2.x release.
That later release can move the same chat, progress, and approval experience into Teams without
changing the underlying agent-job, approval, Graph, audit, or memory architecture built for v2.1.

## Current codebase assessment

The codebase is not empty. It already has meaningful foundations:

| Capability | Current state | Decision |
|---|---|---|
| Microsoft OAuth and encrypted tokens | Working | Keep |
| Teams one-to-one messages | Partial | Generalize |
| Manager-facing web agent | Basic dashboard only | Build for v2.1 |
| Manager-facing Teams bot | Missing | Defer to later Prism v2.x |
| Group chats and channels | Missing | Build |
| Outlook email | Send digest only | Build read, draft, reply |
| Calendar | Missing | Build |
| Local tasks/projects | Working | Expose as agent tools |
| Blocker/employee coordination | Narrow workflow | Generalize |
| Organisational memory | Strong foundation | Extend |
| Manager approvals | Only escalation-specific | Replace with generic approval engine |
| Agent execution | Check-in/reply specific | Build general job runtime |
| Progress visibility | Basic activity lists | Build job timeline |
| LLM providers | Azure-only and hard-coded | Refactor |
| Background execution | In-process scheduler | Keep initially, make durable |
| Automated tests | 99 passing, 56 DB-dependent skipped | Preserve and expand |

The Azure dependency is concentrated in [llm_service.py](/Users/yashmandi/code/prism/app/services/llm_service.py:1). Microsoft Graph functionality is concentrated in a large [microsoft_service.py](/Users/yashmandi/code/prism/app/services/microsoft_service.py:49). The current agent in [management_agent.py](/Users/yashmandi/code/prism/app/agents/management_agent.py:59) is a specialized blocker/check-in workflow rather than a general tool-using agent.

## Target architecture

```text
Prism web app / Graph webhooks
                    │
                    ▼
          Normalized incoming event
                    │
                    ▼
       Conversation + relevant memory
                    │
                    ▼
             Agent job/plan
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
     Read-only tools     Proposed write actions
     execute safely             │
                               ▼
                       Manager approval
                               │
                               ▼
                     Revalidate and execute
                               │
                               ▼
                 Result, audit log and memory
```

Every operation should become an observable job with clear states:

`queued → researching → planning → waiting_for_approval → executing → completed/failed`

The manager can inspect progress, cancel a job, edit a proposal, approve it, or reject it in the
Prism web app.

## Core data model to add

Do not overload the existing employee conversations and automation runs. Add a general agent layer:

- `agent_threads`: the canonical manager/Prism conversation and any future topic-level segments;
  never one thread per Teams person or group.
- `agent_jobs`: goals, status, progress, requester, result and errors.
- `agent_job_sources`: explicit or resolved Teams sources used by each job, including scope and
  resolution rationale.
- `agent_steps`: individual reasoning, retrieval and tool steps.
- `action_proposals`: exact proposed external actions and previews.
- `approval_decisions`: approve, reject, edit, actor and reason.
- `tool_executions`: tool input hash, output, idempotency and errors.
- `external_events`: normalized Teams, email and calendar events.
- `sync_cursors`: delta tokens and recovery positions.
- `scheduled_routines`: recurring manager-authorized workflows.

Existing memory tables remain the long-term context layer, with stronger scope and provenance.

## Approval design

Every potentially consequential write becomes an `action_proposal`. Examples:

- Send a Teams reply
- Post in a channel
- Send an email
- Create or update a meeting
- Assign or change a task
- Contact multiple employees
- Reschedule or cancel something

Each proposal contains:

- Human-readable preview
- Exact target and content
- Source evidence
- Reason for the action
- Risk classification
- Expiration time
- Idempotency key
- Hash of the reviewed payload

The proposal is rendered as a web approval card with **Approve and send**, **Edit**, and **Reject**
actions. Editing any material field produces a revised proposal that must be approved explicitly.

If Prism changes the recipient, content, time, or action after approval, the approval becomes invalid and must be requested again.

Read-only activity can run without approval. No external message or calendar mutation executes
without explicit approval in Prism v2.x.

## Future Teams in-app experience

A later Prism v2.x release can add a private personal Teams app for the manager. It will reuse the
v2.1 APIs and data model while moving natural-language requests, progress updates, and approval
cards into Teams. Prism v2.1 will not include a Teams bot, bot messaging endpoint, Teams app
manifest, or Adaptive Card approval flow.

## Microsoft Graph expansion

Current permissions cover directory access, direct chats, sending chat messages, and sending mail.
The broader Prism v2.0 direction will require additional delegated permissions, granted
incrementally:

- Teams chats: retain `Chat.Read`, `Chat.Create`, `ChatMessage.Send`.
- Group chats: enumerate existing chats and subscribe only to selected conversations.
- Channels: add channel listing, `ChannelMessage.Read.All`, and `ChannelMessage.Send`.
- Email: add `Mail.Read` or `Mail.ReadWrite` for inbox context and drafts; retain `Mail.Send`.
- Calendar: add calendar read/write access and shared availability access where required.

Microsoft supports delegated subscriptions for individual chats and channels, while tenant-wide
subscriptions often require application permissions. For local Prism v2.x releases, Prism should
subscribe only to chats and channels explicitly selected by the manager. [Teams message subscriptions](https://learn.microsoft.com/en-us/graph/teams-changenotifications-chatmessage)

Outlook messages and calendar events support delegated change notifications in the signed-in manager’s mailbox. [Outlook change notifications](https://learn.microsoft.com/en-us/graph/outlook-change-notifications-overview?tabs=http)

## LLM and BYOK design

Prism must not read `/Users/yashmandi/.codex/auth.json`. That is private Codex client state, not a stable Prism integration contract.

OpenAI’s API accepts supported API credentials, and normal API billing is separate from a ChatGPT subscription. [API authentication](https://developers.openai.com/api/reference/overview), [billing separation](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform)

There is now a supported alternative worth considering: **Sign in with ChatGPT** can allow eligible Plus or Pro users and qualifying open-source clients to authorize Responses API requests through OAuth. Prism would need to implement that documented PKCE flow; it still must not copy Codex’s tokens. Eligibility and usage access are not guaranteed until the client is registered and tested. [Sign in with ChatGPT](https://developers.openai.com/siwc/quickstart)

The provider interface should support:

```text
LLMProvider
├── OpenAI API key
├── OpenAI Sign in with ChatGPT
├── Azure OpenAI
├── Local Ollama
└── Future: Anthropic, Gemini, others
```

Initially, implement:

1. Fake provider for deterministic tests.
2. OpenAI standard provider.
3. Existing Azure provider.
4. Local Ollama provider for zero-cost experimentation.
5. ChatGPT OAuth adapter if Prism qualifies for the documented flow.

Provider credentials should be encrypted and never passed to the frontend after initial entry.

## Broader Prism v2.0 roadmap

The phases below describe the longer Prism v2.0 direction across Teams, email, calendar, and
multi-employee coordination. They are not the implementation sequence for the narrower v2.1
release. Use [Prism v2.1 development phases](v2.1-development-phases.md) as the authoritative
build and test plan for v2.1.

### Phase 0 — Stabilize the foundation

Estimated: 2–3 focused days.

- Write architectural decision records.
- Run the complete PostgreSQL integration suite.
- Document Prism v2.1 Graph and approval permissions.
- Preserve the current check-in automation as a legacy workflow.
- Add feature flags for the new agent runtime.
- Define acceptance scenarios and test fixtures.

Completion criteria: existing behavior remains green and every future write action has a documented approval requirement.

### Phase 1 — Provider-independent intelligence

Estimated: 4–6 days.

- Extract `LLMProvider` from the Azure-specific service.
- Add structured output, text generation, streaming and usage contracts.
- Implement OpenAI, Azure, fake and optional Ollama adapters.
- Add provider/model selection and usage limits.
- Record provider, model, latency, tokens and cost consistently.
- Investigate the supported ChatGPT OAuth flow.

Completion criteria: the same agent request works through at least two providers without changing business logic.

### Phase 2 — General agent runtime and web manager chat

Estimated: 6–8 days.

- Add agent threads, jobs, steps and progress events.
- Build one persistent conversational manager interface in the Prism web app.
- Show progress updates and evidence summaries in the same web conversation.
- Render proposed actions as web approval cards with edit, approve and reject actions.
- Add tool registration and typed tool schemas.
- Add memory retrieval with citations to source messages and records.
- Support cancel, retry and resume.
- Add an audit view for active and completed jobs.

Completion criteria: from the Prism web app, the configured manager can ask Prism a natural
question, see its progress and receive an evidence-backed answer without external writes.

### Phase 3 — Microsoft read layer

Estimated: 6–8 days.

- Split Microsoft integration into auth, client, chats, channels, mail, calendar and subscription modules.
- Import existing one-to-one and group chats.
- Let Prism resolve relevant authorized chats from manager requests, with optional explicit source
  filters and clarification for ambiguous people or groups.
- Add Teams channel subscriptions.
- Add Outlook inbox and calendar subscriptions.
- Normalize incoming information into `external_events`.
- Add delta synchronization so missed webhooks can be recovered.
- Deduplicate every event.

Completion criteria: selected Teams, email and calendar activity appears in Prism reliably without sending anything.

### Phase 4 — Generic approvals and Graph actions

Estimated: 6–8 days.

Implement tools such as:

- `draft_teams_reply`
- `send_teams_reply`
- `draft_channel_post`
- `send_channel_post`
- `draft_email_reply`
- `send_email`
- `find_meeting_times`
- `create_calendar_event`
- `update_calendar_event`
- `create_local_task`
- `update_local_task`
- `assign_local_task`

Add:

- Web approval cards and an approval inbox
- A web audit view for pending and completed approvals
- Editable previews
- Approve/reject controls
- Exact-payload approval hashes
- Execution retries and idempotency
- Immutable action audit trail

Completion criteria: no external write is possible without approval, and approving the same action twice cannot duplicate it.

### Phase 5 — Three flagship workflows

Estimated: 8–10 days.

1. **Message assistant**

   - Identify Teams and email messages that need attention.
   - Gather relevant context.
   - Draft replies in the manager’s tone.
   - Show evidence and request approval.
   - Send only after approval.

2. **Meeting scheduler**

   - Understand a natural-language request.
   - Resolve participants.
   - Read availability.
   - Suggest suitable times.
   - Prepare an invite.
   - Create it after approval.

3. **Multi-employee coordinator**

   - Turn a manager goal into requests for several employees.
   - Present the outbound batch for approval.
   - Send approved requests.
   - Track replies and missing responses.
   - Summarize progress.
   - Propose follow-ups for separate approval.

Completion criteria: each workflow succeeds end-to-end with real Microsoft accounts and has failure/retry tests.

### Phase 6 — Memory and learning

Estimated: 5–7 days.

- Store communication preferences and working style.
- Summarize long threads without discarding source evidence.
- Track ongoing goals and unresolved work.
- Learn from edits, approvals and rejections.
- Distinguish preferences from facts.
- Expire or supersede stale information.
- Add “Why does Prism remember this?” visibility.

Completion criteria: Prism recalls relevant preferences and ongoing work while always linking back to evidence.

### Phase 7 — Quality and safety hardening

Estimated: 4–6 days.

- Prompt-injection defenses for messages and email.
- Tool-level allowlists.
- Recipient and tenant validation.
- HTML and attachment sanitization.
- Webhook replay protection.
- Retry and recovery tests.
- Evaluation dataset for the three workflows.
- Token and context budgets.
- Backup and recovery documentation.
- Clear failure notifications.

## Cheapest practical development setup

For local Prism v2.x development:

- Existing Mac
- Existing PostgreSQL
- FastAPI process
- Free ngrok tunnel
- No Redis
- No Celery
- No cloud hosting
- PostgreSQL-backed durable job queue
- Fake provider for most automated tests
- Ollama optionally for local generation
- OpenAI ChatGPT OAuth if eligible, otherwise a very small prepaid API balance

Use the LLM only for interpretation, planning and drafting. Microsoft reads, permission checks, validation, approval handling and execution should remain deterministic.

## Deliberately excluded from Prism v2.1

- Cloud computer or browser automation
- Jira, ClickUp and Slack
- Multi-tenant SaaS
- Per-employee private agents
- Voice conversations
- Autonomous external writes
- A private Prism bot inside Microsoft Teams
- Bot participation in employee group chats and channels
- Mobile application
- Multiple cooperating Prism agents

The connector and tool interfaces should make Jira, ClickUp and Slack straightforward later, but implementing them now would delay the core manager workflows.

## Recommended first vertical slice

Build this before expanding into all surfaces:

1. Manager chats naturally with Prism in the web app.
2. Prism resolves and discloses the relevant authorized Teams conversations.
3. Prism reads a bounded set of sources and identifies work needing a response.
4. Prism drafts one or more coordinated replies with supporting context.
5. The web app shows job progress and evidence.
6. The manager independently edits, approves, or rejects each reply card.
7. Prism sends only approved actions through Graph.
8. The result and manager feedback enter memory.
9. The web app retains the complete audit trail.

That slice validates one manager conversation, multi-source retrieval, coordinated planning,
memory, tools, approvals, progress, Graph execution, BYOK, and auditability together. Once it
works, email, calendar, and Teams-native delivery become controlled extensions rather than
separate systems.

The detailed implementation sequence, completion gates, and testing requirements are in
[Prism v2.1 development phases](v2.1-development-phases.md).

A realistic target is approximately 30–36 focused development days for the web-first v2.1
vertical slice and roughly 6–9 focused weeks for the broader Graph-backed Prism v2.0 direction.
