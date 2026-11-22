import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { PrismLogo } from "@/components/ui";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { emit } from "@/lib/events";
import { Bubble, TypingIndicator } from "./ChatParts";
import {
  ACKNOWLEDGEMENTS,
  ALWAYS_ASKS,
  answerText,
  dayLabel,
  formatTime,
  introText,
  isArchived,
  joinList,
  lowerFirst,
  monitoringSchedule,
  sentence,
  stateLabel,
  teamsScopeCopy,
  withoutGreeting,
} from "./helpers";
import { usePrismsInternal } from "./internal";
import { SourceDialog, type SourceDialogHandle } from "./SourceDialog";
import type { Agreement, OnboardingQuestion, OnboardingSession, Prism } from "./types";
import { useWorkspace, useWorkspaceLifecycle, type Workspace } from "./workspace";

type ComposerMode =
  | { kind: "none" }
  | { kind: "paused"; placeholder: string }
  | { kind: "conversation" }
  | { kind: "question"; question: OnboardingQuestion; session: OnboardingSession; index: number };

interface View {
  stream: ReactNode[];
  composer: ComposerMode;
}

function WorkAgreementCard({ prism, agreement, ws }: { prism: Prism | undefined; agreement: Agreement; ws: Workspace }) {
  const { setStatus } = useApp();
  const { replacePrism } = usePrismsInternal();
  const [how, setHow] = useState(prism?.role_instructions || "");
  const [busy, setBusy] = useState(false);
  const prismId = prism?.id;
  const hadInstructions = Boolean(prism?.role_instructions);

  useEffect(() => {
    if (!prismId || hadInstructions) return;
    agentApi<Prism>(`/api/v2/prisms/${prismId}`).then(
      (fresh) => {
        setHow(fresh.role_instructions || "");
        replacePrism(fresh, { render: false });
      },
      () => {},
    );
  }, [prismId, hadInstructions, replacePrism]);

  const confirm = async () => {
    setBusy(true);
    try {
      if (prism) await agentApi(`/api/v2/prisms/${prism.id}/profile`, { method: "PATCH", ...jsonBody({ role_instructions: how }) });
    } catch (error) {
      setStatus(errorMessage(error), true);
      setBusy(false);
      return;
    }
    void ws.confirmAgreement();
  };

  return (
    <>
      <div className="work-agreement-card">
        <h4>How I’ll work</h4>
        <textarea
          id="prism-agreement-how"
          rows={7}
          maxLength={6000}
          aria-label="How I’ll work"
          value={how}
          disabled={agreement.status !== "draft"}
          onChange={(event) => setHow(event.currentTarget.value)}
        />
        <h4>I always ask you first</h4>
        <ul>
          {ALWAYS_ASKS.filter((item) => prism?.logins_policy === "ask" || !item.startsWith("Signing")).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p className="panel-note">You can’t turn these off. I’ll show a card in the chat each time.</p>
      </div>
      {agreement.status === "draft" ? (
        <div className="chat-actions">
          <button className="button" type="button" disabled={busy} onClick={() => void confirm()}>
            Confirm and activate
          </button>
        </div>
      ) : null}
    </>
  );
}

function agreementView(prism: Prism | undefined, ws: Workspace, lead: string): { nodes: ReactNode[]; composer: ComposerMode } {
  const agreement = ws.state.agreement;
  if (agreement === "loading" || !agreement) {
    return {
      nodes: [
        <Bubble key="wait" speaker="Prism" message={`${lead} That’s everything I need. Give me a moment while I write up how we’ll work together.`} />,
        <TypingIndicator key="typing" name="Prism" />,
      ],
      composer: { kind: "paused", placeholder: "Writing up our working agreement…" },
    };
  }
  if (agreement === "error") {
    return {
      nodes: [
        <div key="error" className="empty-state inline-error">
          The working agreement could not be loaded. Refresh this Prism and try again.
        </div>,
      ],
      composer: { kind: "none" },
    };
  }
  const content = agreement.agreement;
  const confirmed = agreement.status === "confirmed";
  const lines: string[] = [];
  const say = (text: string) => lines.push(text);
  let tail: ReactNode;

  if (content.work) {
    say(confirmed ? "Your working agreement is confirmed. Here’s what we agreed." : `${lead} That’s everything I need. Here’s how I’ll work. Tell me if anything’s off, and you can adjust the details below.`);
    const said = Object.fromEntries((content.answers || []).map((item) => [item.key, String(item.answer || "").replace(/[.]$/, "")]));
    say(`Here’s how I understand my job: ${lowerFirst(sentence(content.mission))}`);
    if (said.work_sites) say(`To do that I’ll use ${lowerFirst(said.work_sites)}.`);
    if (said.work_scope) say(`By default I’ll go with this depth: ${lowerFirst(said.work_scope)}.`);
    if (said.work_output) say(`When I’m done, I’ll give you ${lowerFirst(said.work_output)}, plus a short summary here in the chat.`);
    if (said.tone) say(`I’ll keep my tone ${lowerFirst(said.tone)}.`);
    if (said.allowed_proposals) say(`For anything that needs your say-so, I’ll prepare ${lowerFirst(said.allowed_proposals)} and wait for your approval.`);
    if (said.restrictions) say(`And I’ll make sure never to: ${lowerFirst(said.restrictions)}.`);
    tail = <WorkAgreementCard key="work-card" prism={prism} agreement={agreement} ws={ws} />;
  } else {
    say(confirmed ? "Your working agreement is confirmed. Here’s what we agreed." : `${lead} That’s everything. Here’s how I understood our working relationship. Tell me if anything is off.`);
    say(`My job: ${sentence(content.mission)}`);
    const signals = joinList(content.attention_signals);
    if (signals) say(`I’ll bring ${signals} to your attention. ${content.regular_brief ? sentence(`For your regular brief: ${content.regular_brief}`) : ""}`.trim());
    say(`${sentence(content.teams_scope)} I’ll keep it ${String(content.tone || "friendly").replace(/\.$/, "").toLowerCase()}.`);
    const proposals = joinList(content.allowed_proposals);
    const restrictions = joinList(content.restrictions);
    say(
      `${proposals ? `I can prepare ${proposals} for your approval. ` : ""}${restrictions && !/^no\b/i.test(restrictions) ? `I won’t: ${restrictions}. ` : ""}${sentence(content.safety_rule)}`.trim(),
    );
    if (content.current_limitations) say(sentence(content.current_limitations));
    if (agreement.status === "draft") say("Happy with this? I can start as soon as you confirm.");
    tail =
      agreement.status === "draft" ? (
        <div className="chat-actions" key="confirm">
          <button className="button" type="button" onClick={() => void ws.confirmAgreement()}>
            Confirm and activate
          </button>
        </div>
      ) : null;
  }
  return {
    nodes: [
      <div className="working-agreement" key="agreement">
        {lines.map((text, index) => (
          <Bubble key={index} speaker="Prism" message={text} />
        ))}
      </div>,
      tail,
    ],
    composer: { kind: "none" },
  };
}

function onboardingView(prism: Prism | undefined, ws: Workspace, session: OnboardingSession): View {
  const { answering, editingQuestionId } = ws.state;
  const name = prism?.name || "Prism";
  const answers = new Map(session.answers.map((answer) => [answer.question_id, answer]));
  const activeId = editingQuestionId || session.current_question_id;
  const activeQuestion = session.status === "completed" ? undefined : session.questions.find((question) => question.id === activeId);
  const intro = introText(prism);
  const stream: ReactNode[] = [];
  let lead = "";
  session.questions.forEach((question, index) => {
    const answer = answers.get(question.id);
    if (!answer || question.id === activeId) return;
    if (index === 0) stream.push(<Bubble key={`intro-${question.id}`} speaker={name} message={intro} />);
    stream.push(<Bubble key={`q-${question.id}`} speaker={name} message={`${lead} ${index === 0 ? withoutGreeting(question.prompt) : question.prompt}`.trim()} />);
    stream.push(<Bubble key={`a-${question.id}`} speaker="You" kind="user" message={answerText(question, answer)} />);
    lead = ACKNOWLEDGEMENTS[index % ACKNOWLEDGEMENTS.length];
  });
  if (!activeQuestion) {
    const agreement = agreementView(prism, ws, lead);
    return { stream: [...stream, ...agreement.nodes], composer: agreement.composer };
  }
  const position = session.questions.indexOf(activeQuestion);
  if (position === 0) stream.push(<Bubble key="intro-active" speaker={name} message={intro} />);
  stream.push(
    <Bubble key={`q-${activeQuestion.id}`} speaker={name} message={`${lead} ${position === 0 ? withoutGreeting(activeQuestion.prompt) : activeQuestion.prompt}`.trim()} />,
  );
  if (answering) {
    stream.push(<Bubble key="answering" speaker="You" kind="user" message={answering.text} />, <TypingIndicator key="typing" name={name} />);
    return { stream, composer: { kind: "paused", placeholder: `${name} is typing…` } };
  }
  return { stream, composer: { kind: "question", question: activeQuestion, session, index: position } };
}

function activeConversationView(prism: Prism, ws: Workspace): View {
  const { conversation, pending } = ws.state;
  if (conversation === "loading" || !conversation) {
    return { stream: [<div key="note" className="chat-note">Loading this Prism’s private conversation…</div>], composer: { kind: "none" } };
  }
  if (conversation === "error") {
    return {
      stream: [<div key="note" className="chat-note inline-error">This Prism’s conversation could not be loaded. Select it again to retry.</div>],
      composer: { kind: "none" },
    };
  }
  const stream: ReactNode[] = [];
  if (!conversation.messages.length) {
    stream.push(<Bubble key="ready" speaker={prism.name} message="I’m ready. Ask me about your team’s work, or tell me what you want me to remember for this Prism." />);
  } else {
    let lastDay: string | null = null;
    conversation.messages.forEach((message, index) => {
      const day = message.created_at ? new Date(message.created_at).toDateString() : null;
      if (day && message.created_at && day !== lastDay) {
        stream.push(<div key={`day-${index}`} className="chat-day">{dayLabel(message.created_at)}</div>);
        lastDay = day;
      }
      const mine = message.role === "manager";
      stream.push(
        <Bubble key={message.id ?? `m-${index}`} speaker={mine ? "You" : prism.name} message={message.content} kind={mine ? "user" : "assistant"} time={message.created_at} />,
      );
    });
  }
  if (pending && pending.prismId === prism.id) {
    stream.push(<Bubble key="pending" speaker="You" kind="user" message={pending.content} />, <TypingIndicator key="pending-typing" name={prism.name} stage={pending.stage} />);
  }
  if (conversation.preferences?.length) {
    stream.push(
      <details className="chat-card" key="memory">
        <summary>{`What ${prism.name} remembers · ${conversation.preferences.length}`}</summary>
        <ul>
          {conversation.preferences.slice(0, 8).map((preference, index) => (
            <li key={index}>{preference.instruction}</li>
          ))}
        </ul>
      </details>,
    );
  }
  return { stream, composer: { kind: "conversation" } };
}

function buildView(prism: Prism | undefined, ws: Workspace): View {
  if (!prism) return { stream: [], composer: { kind: "none" } };
  const { onboarding, starting } = ws.state;
  const name = prism.name;
  if (isArchived(prism)) {
    return { stream: [<Bubble key="archived" speaker="Prism" message="This Prism is archived and its onboarding record is read-only." />], composer: { kind: "none" } };
  }
  if (String(prism.state).toLowerCase() === "active") return activeConversationView(prism, ws);
  const hello = `Hi, I’m ${name}. Before I start helping, I’d like to learn how you work. It takes a few quick questions, and everything stays private to me.`;
  if (onboarding === "missing") {
    return {
      stream: [
        <Bubble key="hello" speaker={name} message={hello} />,
        <div className="chat-actions" key="start">
          <button className="button" type="button" onClick={() => void ws.startOnboarding()}>
            Let’s get started
          </button>
        </div>,
      ],
      composer: { kind: "none" },
    };
  }
  if (onboarding === "loading" || !onboarding) {
    if (starting) {
      return {
        stream: [<Bubble key="hello" speaker={name} message={hello} />, <TypingIndicator key="typing" name={name} />],
        composer: { kind: "paused", placeholder: `${name} is getting ready…` },
      };
    }
    return { stream: [<div key="note" className="chat-note">Loading this Prism’s conversation…</div>], composer: { kind: "none" } };
  }
  if (onboarding === "error") {
    return { stream: [<div key="note" className="chat-note inline-error">Onboarding could not be loaded. Try selecting this Prism again.</div>], composer: { kind: "none" } };
  }
  return onboardingView(prism, ws, onboarding);
}

function PinnedBar({ active }: { active: boolean }) {
  const { monitoring } = usePrismsInternal();
  const { sourcePolicy: policy, activity, observations, triggerPolicy: trigger, runs } = monitoring;
  const loaded = policy && typeof policy === "object" ? policy : null;
  const openObservations = observations && typeof observations === "object" ? (observations.items || []).filter((item) => item.state === "open").slice(0, 3) : [];
  const latest = runs?.items?.[0];
  return (
    <details id="prism-pinned" className="chat-pinned" hidden={!active}>
      <summary>
        <span className={`pinned-dot${loaded?.last_discovery_error ? " warn" : ""}`} />
        <strong>Teams monitoring</strong>
        <span className="pinned-text">{teamsScopeCopy(policy)}</span>
      </summary>
      <div className="chat-pinned-body">
        {active ? (
          <>
            {loaded?.last_discovery_at ? (
              <p>{`Last checked ${formatTime(loaded.last_discovery_at)}.${loaded.last_discovery_error ? ` ${loaded.last_discovery_error}` : ""}`}</p>
            ) : policy !== "loading" && policy !== "error" ? (
              <p>No Teams activity has been checked yet. Use Refresh Teams activity in the menu for one bounded local read; nothing is sent.</p>
            ) : null}
            {activity && typeof activity === "object" && activity.items?.length ? (
              <ul className="prism-event-list">
                {activity.items.slice(0, 3).map((event, index) => {
                  const action = event.event_kind === "deleted" ? "deleted a message" : event.event_kind === "updated" ? "updated a message" : "posted";
                  const text = event.body_text ? `: ${event.body_text.replace(/\s+/g, " ")}` : ".";
                  return <li key={index}>{`${event.sender_display_name} ${action} in ${event.source_label || "Teams chat"}${text}`}</li>;
                })}
              </ul>
            ) : null}
            {openObservations.length ? (
              <>
                <p>{`Proactive recommendations (${openObservations.length})`}</p>
                <ul className="prism-event-list">
                  {openObservations.map((item, index) => (
                    <li key={index}>{`${item.urgency.toUpperCase()} · ${item.summary}: ${item.suggested_next_step}`}</li>
                  ))}
                </ul>
              </>
            ) : null}
            {trigger && typeof trigger === "object" ? (
              <>
                <p>{monitoringSchedule(trigger)}</p>
                {latest ? (
                  <p>{`Last monitoring run: ${latest.state}${latest.completed_at ? ` · ${formatTime(latest.completed_at)}` : ""}.${latest.safe_error ? ` ${latest.safe_error}` : ""}`}</p>
                ) : null}
              </>
            ) : null}
          </>
        ) : null}
      </div>
    </details>
  );
}

const MENU_ICONS: Record<string, string> = {
  settings: "M4 7h8M16 7h4M4 17h4M12 17h8",
  edit: "M4 20h4L19 9l-4-4L4 16v4ZM13 7l4 4",
  policy: "M12 3 5 6v5c0 4.5 3 8.5 7 10 4-1.5 7-5.5 7-10V6l-7-3Z",
  trigger: "M12 3v7l4 2M5 5l2-2m10 0 2 2M4 18l2 2m12-2-2 2M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18Z",
  sync: "M20 11a8 8 0 1 0 1.4 4.5M20 4v7h-7",
  notify: "M6 17V11a6 6 0 1 1 12 0v6l1.5 2h-15L6 17ZM10 21h4",
  health: "M3 12h4l2-6 4 12 2-6h6",
  archive: "M4 5h16v4H4zM6 9v10h12V9M10 13h4",
};

function MenuIcon({ name }: { name: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d={MENU_ICONS[name]} />
      {name === "settings" ? (
        <>
          <circle cx="14" cy="7" r="2" />
          <circle cx="10" cy="17" r="2" />
        </>
      ) : null}
    </svg>
  );
}

/** `#prism-workspace`: the onboarding chat (and, transiently, the private conversation) of the selected Prism. */
export function OnboardingChat() {
  const app = useApp();
  const internal = usePrismsInternal();
  const { selectedPrism: prism, monitoring, commands, archivePrism } = internal;
  const ws = useWorkspace();
  useWorkspaceLifecycle(ws);
  const { state } = ws;
  const sourceDialog = useRef<SourceDialogHandle>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const renderedId = useRef<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const lastLabel = useRef("Continue");
  const [menuOpen, setMenuOpen] = useState(false);

  const view = buildView(prism, ws);
  const mode = view.composer;
  const archived = Boolean(prism && isArchived(prism));
  const active = Boolean(prism && String(prism.state).toLowerCase() === "active");

  // A new question starts from its saved answer; a conversation keeps what is being typed.
  if (mode.kind === "question") {
    const existing = mode.session.answers.find((answer) => answer.question_id === mode.question.id);
    ws.syncComposer(`q:${prism?.id}:${mode.question.id}:${state.editingQuestionId ?? ""}:${mode.session.revision}`, existing?.selected_values ?? [], existing?.custom_text || "");
  } else if (mode.kind === "conversation") ws.syncComposer(`c:${prism?.id}`, [], "");
  else if (mode.kind === "paused" && state.composer.text) ws.setComposerText("");

  const { composer } = state;
  const question = mode.kind === "question" ? mode.question : null;
  const customHidden = question
    ? question.choices.length
      ? !question.allows_custom && question.question_type !== "long_text" && question.question_type !== "short_text"
      : false
    : false;
  const choicesVisible = Boolean(question?.choices.length);
  const sendLabel = mode.kind === "question" ? (state.editingQuestionId ? "Save answer" : "Continue") : mode.kind === "conversation" ? "Ask Prism" : lastLabel.current;
  useEffect(() => {
    if (mode.kind === "question" || mode.kind === "conversation") lastLabel.current = sendLabel;
  });
  const placeholder =
    mode.kind === "paused"
      ? mode.placeholder
      : mode.kind === "question"
        ? mode.question.choices.length
          ? "Or answer in your own words…"
          : "Type your answer…"
        : mode.kind === "conversation"
          ? `Message ${prism?.name}`
          : "Type your answer…";
  const sendDisabled = mode.kind === "paused" || (mode.kind === "conversation" && state.sending);

  // Keep the newest turn in view when the reader was already near the bottom, or when they just sent something.
  useLayoutEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller || !prism) return;
    const switched = renderedId.current !== prism.id;
    renderedId.current = prism.id;
    const force = ws.consumeScroll();
    if (switched || nearBottom.current || force) {
      scroller.scrollTop = scroller.scrollHeight;
      nearBottom.current = true;
    }
  });

  useLayoutEffect(() => {
    const input = textRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 200)}px`;
  }, [composer.text, mode.kind]);

  useEffect(() => {
    if (!prism) setMenuOpen(false);
  }, [prism]);

  useEffect(() => {
    if (menuOpen) menuRef.current?.querySelector<HTMLElement>(".menu-item:not([hidden])")?.focus();
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onClick = (event: MouseEvent) => {
      if (!(event.target instanceof Element) || !event.target.closest("#prism-menu, #prism-menu-button")) setMenuOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMenuOpen(false);
      menuButtonRef.current?.focus();
    };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const openEditor = (target: Prism) => commands.current.openEditor?.(target);
  const openMoreSettings = (target: Prism) => {
    if (app.modes.v24 !== true) {
      openEditor(target);
      return;
    }
    app.setSidebarSection("workspace");
    emit("workspace-navigate", { page: "prism", id: target.id });
    app.closeSidebarIfNarrow();
  };

  const submit = () => {
    const current = ws.current();
    if (current?.state === "active") {
      void ws.sendConversationMessage();
      return;
    }
    const session = ws.live.current.onboarding;
    if (!session || typeof session !== "object") return;
    const target = session.questions.find((item) => item.id === (ws.live.current.editingQuestionId || session.current_question_id));
    if (target) void ws.submitAnswer(target, session);
  };

  const selectedSources = state.selectedSources;
  const sourceLabel = selectedSources.length
    ? `Reading only: ${selectedSources.map((source) => source.label).join(", ")}. Click to change.`
    : "Auto: Prism picks the relevant Teams chats. Click to choose up to five.";

  const choices = (
    <fieldset id="prism-onboarding-choices" className="onboarding-choices" hidden={!choicesVisible}>
      {question
        ? [
            ...question.choices.map((choice) => (
              <label className="onboarding-choice" key={choice.value}>
                <input
                  type={question.question_type === "multiple_choice" ? "checkbox" : "radio"}
                  name="prism-onboarding-choice"
                  value={choice.value}
                  checked={composer.choices.includes(choice.value)}
                  onChange={(event) => {
                    const checked = event.currentTarget.checked;
                    if (question.question_type === "multiple_choice") {
                      ws.setComposerChoices(checked ? [...composer.choices, choice.value] : composer.choices.filter((value) => value !== choice.value));
                    } else if (checked) ws.setComposerChoices([choice.value]);
                  }}
                />
                <span className="choice-mark" />
                <span className="choice-text">{choice.label}</span>
              </label>
            )),
            ...(question.choices.length && !customHidden
              ? [
                  <button
                    key="other"
                    className="onboarding-choice other"
                    type="button"
                    onClick={() => {
                      ws.setComposerChoices([]);
                      textRef.current?.focus();
                    }}
                  >
                    <span className="choice-mark plus" />
                    <span className="choice-text">Something else, I’ll type it</span>
                  </button>,
                ]
              : []),
          ]
        : null}
    </fieldset>
  );

  const header = (
    <header className="agent-bar">
      <button className="icon-button chat-sidebar-open" type="button" aria-label="Open sidebar" data-tooltip="Open sidebar" onClick={app.openSidebar}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      <div className="agent-bar-title">
        <span id="prism-conversation-logo" className="header-logo" aria-hidden="true">
          {prism ? <PrismLogo prism={prism} className="prism-logo" /> : null}
        </span>
        <strong id="prism-conversation-title">{prism?.name ?? "Prism"}</strong>
        <code id="prism-conversation-code" className="prism-code" aria-label="Prism code" hidden={!prism?.code}>
          {prism?.code || ""}
        </code>
        <span id="prism-conversation-subtitle" className="agent-bar-sub" />
      </div>
      <div className="agent-bar-actions chat-header-actions">
        <span id="prism-conversation-state" className={`prism-state${prism ? ` ${prism.state}` : ""}`}>
          {prism ? stateLabel(prism) : ""}
        </span>
        <button
          id="prism-menu-button"
          ref={menuButtonRef}
          className="icon-button"
          type="button"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-controls="prism-menu"
          aria-label="More actions"
          onClick={(event) => {
            event.stopPropagation();
            setMenuOpen((open) => !open);
          }}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="5" cy="12" r="1" />
            <circle cx="12" cy="12" r="1" />
            <circle cx="19" cy="12" r="1" />
          </svg>
        </button>
        <div id="prism-menu" ref={menuRef} className="menu" role="menu" aria-label="Prism actions" hidden={!menuOpen} onClick={(event) => {
          if (event.target instanceof Element && event.target.closest(".menu-item")) setMenuOpen(false);
        }}>
          <button id="prism-more-settings-button" className="menu-item" type="button" role="menuitem" onClick={() => prism && openMoreSettings(prism)}>
            <MenuIcon name="settings" />
            <span>More settings</span>
          </button>
          <button id="prism-edit-button" className="menu-item" type="button" role="menuitem" onClick={() => prism && openEditor(prism)}>
            <MenuIcon name="edit" />
            <span id="prism-edit-label">{archived ? "View details" : "Edit Prism"}</span>
          </button>
          <button id="prism-policy-button" className="menu-item" type="button" role="menuitem" hidden={!active} onClick={() => void monitoring.openPolicy()}>
            <MenuIcon name="policy" />
            <span>Teams monitoring scope</span>
          </button>
          <button id="prism-trigger-button" className="menu-item" type="button" role="menuitem" hidden={!active} onClick={() => commands.current.openTrigger?.()}>
            <MenuIcon name="trigger" />
            <span>Monitoring schedule</span>
          </button>
          <button id="prism-sync-button" className="menu-item" type="button" role="menuitem" hidden={!active} disabled={monitoring.syncing} onClick={() => void monitoring.syncActivity()}>
            <MenuIcon name="sync" />
            <span>Refresh Teams activity</span>
          </button>
          <button id="prism-notify-button" className="menu-item" type="button" role="menuitem" hidden={!active} onClick={() => commands.current.openNotify?.()}>
            <MenuIcon name="notify" />
            <span>Notifications</span>
          </button>
          <button id="prism-health-button" className="menu-item" type="button" role="menuitem" hidden={!active} onClick={() => commands.current.openHealth?.()}>
            <MenuIcon name="health" />
            <span>Status &amp; tuning</span>
          </button>
          <div className="menu-divider" role="separator" />
          <button id="prism-archive-button" className="menu-item danger" type="button" role="menuitem" onClick={() => prism && void archivePrism(prism)}>
            <MenuIcon name="archive" />
            <span id="prism-archive-label">{archived ? "Delete permanently" : "Archive"}</span>
          </button>
        </div>
        <button className="icon-button" type="button" disabled aria-label="Search" data-tooltip="Available once onboarding is complete">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="6" />
            <path d="m20 20-4-4" />
          </svg>
        </button>
        <button className="icon-button" type="button" disabled aria-label="Preferences" data-tooltip="Available once onboarding is complete">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 7h8M16 7h4M4 17h4M12 17h8" />
            <circle cx="14" cy="7" r="2" />
            <circle cx="10" cy="17" r="2" />
          </svg>
        </button>
      </div>
    </header>
  );

  return (
    <section id="prism-workspace" className="chat" aria-live="polite">
      <div id="prism-workspace-empty" className="chat-empty" hidden={Boolean(prism)}>
        <span className="chat-empty-mark" aria-hidden="true">
          P
        </span>
        <h2>Select a Prism</h2>
        <p>Choose a Prism in the sidebar to open its private conversation.</p>
      </div>
      <div id="prism-onboarding-workspace" className="chat-window" hidden={!prism}>
        {header}
        <PinnedBar active={active} />
        <div
          id="prism-scroll"
          ref={scrollRef}
          className="agent-scroll fade-scrollbar"
          onScroll={(event) => {
            const el = event.currentTarget;
            nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
          }}
        >
          <div className="agent-stream">
            <div id="prism-onboarding-stream" className="agent-timeline" aria-live="polite">
              {view.stream}
              {choicesVisible ? choices : null}
            </div>
          </div>
        </div>
        <form
          id="prism-onboarding-form"
          ref={formRef}
          className="agent-dock"
          hidden={mode.kind === "none"}
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          {choicesVisible ? null : choices}
          <p id="prism-onboarding-error" className="form-error" role="alert" hidden={!state.answerError}>
            {state.answerError}
          </p>
          <div className="agent-composer pill">
            <label id="prism-onboarding-custom-wrap" className="composer-input" hidden={mode.kind === "none" || customHidden} htmlFor="prism-onboarding-custom">
              <span className="sr-only">Message</span>
              <textarea
                id="prism-onboarding-custom"
                ref={textRef}
                rows={1}
                maxLength={4000}
                placeholder={placeholder}
                disabled={mode.kind === "paused"}
                value={mode.kind === "paused" ? "" : composer.text}
                onChange={(event) => ws.setComposerText(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
                  event.preventDefault();
                  if (!sendDisabled) formRef.current?.requestSubmit();
                }}
              />
            </label>
            <span id="prism-choice-hint" className="composer-placeholder" hidden={mode.kind !== "question" || !customHidden}>
              Choose an answer above
            </span>
            <div id="prism-source-control" className="prism-source-control" hidden={mode.kind !== "conversation"}>
              <button
                id="prism-source-button"
                className={`source-chip${selectedSources.length ? " selected" : ""}`}
                type="button"
                title={sourceLabel}
                aria-label={sourceLabel}
                onClick={() => sourceDialog.current?.open()}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 5h16v11H9l-5 4V5Z" />
                </svg>
                <span id="prism-source-summary">{selectedSources.length ? `${selectedSources.length} ${selectedSources.length === 1 ? "chat" : "chats"}` : "Auto"}</span>
                <svg className="chevron" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </button>
            </div>
            <span className="composer-actions">
              <button
                id="prism-onboarding-back"
                className="mini-button ghost"
                type="button"
                hidden={mode.kind !== "question" || mode.index <= 0}
                onClick={() => {
                  if (mode.kind === "question") ws.setEditingQuestion(mode.session.questions[mode.index - 1].id);
                }}
              >
                Back
              </button>
              <button
                id="prism-onboarding-skip"
                className="mini-button ghost"
                type="button"
                hidden={mode.kind !== "question" || mode.question.required}
                onClick={() => {
                  if (mode.kind === "question") void ws.submitAnswer(mode.question, mode.session, true);
                }}
              >
                Skip
              </button>
              <button id="prism-onboarding-next" className="send-button" type="submit" aria-label={sendLabel} title={sendLabel} disabled={sendDisabled}>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 19V5M5 12l7-7 7 7" />
                </svg>
              </button>
            </span>
          </div>
        </form>
      </div>
      {createPortal(
        <SourceDialog ref={sourceDialog} monitoring={monitoring} selected={selectedSources} onSelect={ws.setSelectedSources} />,
        document.body,
      )}
    </section>
  );
}
