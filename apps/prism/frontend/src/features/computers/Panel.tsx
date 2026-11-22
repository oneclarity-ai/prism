import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { elapsed, isActive, isWork, money, stateText, stripScheme } from "./helpers";
import { stopLive, useLive } from "./live";
import { Btn } from "./parts";
import {
  cancelRun,
  ensureFrame,
  ensureScreen,
  getState,
  isQaPrism,
  removeLogin,
  resetComputer,
  selectRun,
  setEnlarged,
  setOpen,
  syncLive,
  tickClock,
  useClock,
  useComputerButton,
  useComputerOpen,
  useStoreVersion,
} from "./store";
import type { QaRun } from "./types";

function Elapsed({ run }: { run: QaRun }) {
  useClock();
  return <span className="qa-elapsed">{elapsed(run)}</span>;
}

/* ---------- the screen ---------- */

function ScreenFrame({ run, large = false }: { run: QaRun | undefined; large?: boolean }) {
  const state = getState();
  const live = useLive();
  const [aspect, setAspect] = useState<string | undefined>();
  // Checked after every render, like the old renderPanel: fetches only when the newest frame is missing.
  useEffect(() => {
    if (run?.frame != null) ensureFrame(run);
    else if (run?.screen != null) ensureScreen(run);
  });

  let hasImage = false;
  let src: string | undefined;
  if (run?.frame != null) {
    hasImage = true;
    src = state.frames.get(run.id)?.url;
  } else if (run?.screen != null) {
    hasImage = true;
    src = state.screens.get(`${run.id}:${run.screen}`);
  }
  if (live.url && live.prismId === state.prism?.id && live.runId === run?.id) {
    // The live stream is newer than any saved frame: show it.
    hasImage = true;
    src = live.url;
  } else if (isActive(run)) {
    // No live frame yet: the first one to arrive replaces whatever saved frame is showing.
    hasImage = true;
  }

  return (
    <div className={large ? "qa-screen large" : "qa-screen"}>
      <div className="qa-chrome">
        <span className="qa-dots">
          <i />
          <i />
          <i />
        </span>
        <span className="qa-address">{run?.current_url || (run?.site ? `https://${run.site}` : "")}</span>
        {!large ? (
          <button className="qa-enlarge" type="button" title="Enlarge" aria-label="Enlarge the computer screen" onClick={() => setEnlarged(true)}>
            <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
            </svg>
          </button>
        ) : null}
      </div>
      <div className="qa-view" style={aspect ? { aspectRatio: aspect } : undefined}>
        <div className="qa-idle">
          <span className="qa-idle-mark">{state.prism?.name?.slice(0, 1) || "P"}</span>
        </div>
        {hasImage ? (
          <img
            className={src ? "qa-shot show" : "qa-shot"}
            alt="What the screen shows right now"
            src={src}
            onLoad={(event) => {
              const image = event.currentTarget;
              if (image.naturalWidth) setAspect(`${image.naturalWidth} / ${image.naturalHeight}`);
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

function EnlargedDialog() {
  const version = useStoreVersion();
  const state = getState();
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const run = state.runs.get(state.focus ?? "");
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (state.enlarged && !dialog.open) {
      dialog.showModal();
      closeRef.current?.focus();
    } else if (!state.enlarged && dialog.open) dialog.close();
  }, [state.enlarged, version]);
  return createPortal(
    <dialog
      ref={ref}
      id="qa-enlarged"
      className="qa-enlarged"
      aria-label="Computer, enlarged"
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
      onClose={() => setEnlarged(false)}
    >
      {state.enlarged ? (
        <>
          <div className="qa-enlarged-bar">
            <strong>{`${state.prism?.name || "Prism"}'s computer`}</strong>
            <button ref={closeRef} className="button secondary" type="button" onClick={() => ref.current?.close()}>
              Close
            </button>
          </div>
          <ScreenFrame run={run} large />
        </>
      ) : null}
    </dialog>,
    document.body,
  );
}

/* ---------- the run ---------- */

function Progress({ run }: { run: QaRun }) {
  const work = isWork(run);
  const meta = (
    <p className="qa-muted">
      {`Step ${run.turn}${run.max_turns ? ` of ${work ? "up to " : ""}${run.max_turns}` : ""} · ${money(run.cost_usd)}${run.budget_usd ? ` of ${money(run.budget_usd)}` : ""} · `}
      <Elapsed run={run} />
    </p>
  );
  if (work) {
    const checklist = run.checklist || [];
    const done = checklist.filter((step) => step.status === "done" || step.status === "skipped").length;
    const total = checklist.length;
    return (
      <div className="qa-progress">
        <div className="qa-bar">
          {done ? <span className="qa-seg tone-green" style={{ flex: String(done || 0) }} /> : null}
          {total - done > 0 || !total ? <span className="qa-seg tone-none" style={{ flex: String(Math.max(total - done, total ? 0 : 1)) }} /> : null}
        </div>
        {total ? <p className="qa-muted">{`${done} of ${total} steps done`}</p> : null}
        {meta}
      </div>
    );
  }
  const cases = run.cases || {};
  const total = cases.total || 0;
  const segments: Array<[keyof typeof cases, string]> = [
    ["pass", "green"],
    ["fail", "red"],
    ["blocked", "orange"],
    ["skipped", "gray"],
  ];
  const rest = total - ((cases.pass || 0) + (cases.fail || 0) + (cases.blocked || 0) + (cases.skipped || 0));
  return (
    <div className="qa-progress">
      <div className="qa-bar">
        {segments.map(([key, tone]) => (cases[key] ? <span key={key} className={`qa-seg tone-${tone}`} style={{ flex: String(cases[key]) }} /> : null))}
        {rest > 0 || !total ? <span className="qa-seg tone-none" style={{ flex: String(Math.max(rest, 1)) }} /> : null}
      </div>
      <p className="qa-muted">
        {total ? `${total} checks · ${cases.pass || 0} passed · ${cases.fail || 0} failed${cases.blocked ? ` · ${cases.blocked} couldn't check` : ""}` : "No checks yet"}
      </p>
      {meta}
    </div>
  );
}

const CHECK_MARKS: Record<string, string> = { done: "✓", doing: "●", skipped: "–", todo: "○" };

function Checklist({ run }: { run: QaRun }) {
  return (
    <div className="qa-checklist">
      <h4>Plan</h4>
      {(run.checklist || []).map((step, index) => (
        <p className={`qa-step ${step.status}`} key={index}>
          <span className="qa-step-mark">{CHECK_MARKS[step.status] || "○"}</span>
          <span>{step.title}</span>
        </p>
      ))}
    </div>
  );
}

function ComputerFooter({ live }: { live: boolean }) {
  const { logins } = getState();
  return (
    <div className="qa-footer">
      <details className="qa-logins">
        <summary>{`Saved logins (${logins.length})`}</summary>
        {!logins.length ? <p className="qa-muted">None. I'll ask you in the chat when a site needs one.</p> : null}
        {logins.map((login) => (
          <div className="qa-login-row" key={login.id}>
            <span>
              <strong>{stripScheme(login.site)}</strong>
              {` · ${login.username}${login.remember ? "" : " · one task"}`}
            </span>
            <Btn label="Remove" className="mini-button" onClick={() => void removeLogin(login)} />
          </div>
        ))}
      </details>
      <Btn
        label="Reset computer"
        className="button secondary"
        disabled={live}
        title={live ? "Stop the task first" : "Forget every login and clear the browser"}
        onClick={() => void resetComputer()}
      />
    </div>
  );
}

function PanelBody() {
  useStoreVersion();
  const state = getState();
  const liveView = useLive();
  const run = state.runs.get(state.focus ?? "");
  // Streams only while the panel is open and a task is running (idempotent, so safe after every render).
  useEffect(() => {
    syncLive(run);
  });
  const name = state.prism?.name || "Prism";
  const work = !run ? state.computers && !isQaPrism(state.prism) : isWork(run);
  const live = isActive(run);
  const waiting = run?.state === "waiting_approval" || Boolean(run?.startup_warning);
  const offline = !run && state.computer?.state === "unavailable";
  const past = state.order.map((id) => state.runs.get(id)).filter((item): item is QaRun => Boolean(item));
  return (
    <>
      <ScreenFrame run={run} />
      <div className="qa-caption">
        <span className={`qa-live${live ? " on" : ""}${waiting ? " waiting" : ""}`} />
        <strong>{`${name}'s screen`}</strong>
        <span className="qa-muted">{run ? stateText(run) : offline ? "Offline" : state.computers ? "Asleep" : "Idle"}</span>
      </div>
      {live && run ? (
        <p className="qa-muted qa-stream-status" role="status">
          {run.startup_warning ? "Live view will connect when the testing workspace is available." : liveView.status}
        </p>
      ) : run && (run.frame != null || run.screen != null || (liveView.runId === run.id && liveView.url)) ? (
        <p className="qa-muted">Last screen · task ended</p>
      ) : null}
      {!run ? (
        offline ? (
          <p className="qa-error">{state.computer?.reason || "My computer is offline right now."}</p>
        ) : work ? (
          <p className="qa-empty">{`Asleep. ${name}'s computer wakes up when you give it a task, for example "find five fintech companies in Bangalore and list their websites". You'll watch the work here.`}</p>
        ) : (
          <p className="qa-empty">{`Ask ${name} to test a website, for example "test example.com and check the contact form". You'll watch the work here.`}</p>
        )
      ) : (
        <>
          {run.startup_warning ? (
            <p className="qa-now qa-waiting">{run.startup_warning}</p>
          ) : run.state === "starting" ? (
            <p className="qa-now live">{run.activity || "Connecting to my testing workspace…"}</p>
          ) : waiting ? (
            <p className="qa-now qa-waiting">Waiting for you in the chat</p>
          ) : run.activity ? (
            <p className={`qa-now${live ? " live" : ""}`}>{run.activity}</p>
          ) : null}
          {isWork(run) && run.checklist?.length ? <Checklist run={run} /> : null}
          <Progress run={run} />
          {live ? <Btn label={isWork(run) ? "Stop" : "Stop the test"} className="button secondary qa-stop" onClick={() => void cancelRun(run)} /> : null}
          {run.state === "error" && run.error ? <p className="qa-error">{run.error}</p> : null}
          {run.activity_log?.length ? (
            <details className="qa-log">
              <summary>What I've done</summary>
              {[...run.activity_log].reverse().map((item, index) => (
                <p key={index}>{item.text}</p>
              ))}
            </details>
          ) : null}
        </>
      )}
      {past.length ? (
        <div className="qa-runs">
          <h4>{isWork(past[0]) ? "Tasks" : "Tests"}</h4>
          {past.slice(0, 8).map((item) => (
            <button key={item.id} className={`qa-run${item.id === state.focus ? " current" : ""}`} type="button" onClick={() => selectRun(item.id)}>
              <strong>{item.site || item.plan?.title || "Task"}</strong>
              <span className="qa-muted">{`${stateText(item)}${item.cases?.total ? ` · ${item.cases.pass || 0}/${item.cases.total}` : ""}`}</span>
            </button>
          ))}
        </div>
      ) : null}
      {state.computers ? <ComputerFooter live={live} /> : null}
    </>
  );
}

/** `<aside id="qa-computer-panel">`: the Prism's computer (live screen, progress, past runs, saved logins). */
export function ComputerPanel() {
  const open = useComputerOpen();
  useStoreVersion();
  const state = getState();
  const name = state.prism?.name || "Prism";

  // The elapsed clock of a running task ticks once a second while the panel is open.
  useEffect(() => {
    if (!open) return;
    const timer = setInterval(() => {
      const current = getState();
      if (isActive(current.runs.get(current.focus ?? ""))) tickClock();
    }, 1000);
    return () => clearInterval(timer);
  }, [open]);
  useEffect(() => () => stopLive(), []);

  return (
    <>
      <aside id="qa-computer-panel" className={`agent-drawer computer-panel${open ? " open" : ""}`} aria-label="Prism's computer">
        <div className="drawer-head">
          <h3 id="qa-computer-title">{`${name}'s computer`}</h3>
          <button id="qa-computer-close" className="icon-button" type="button" aria-label="Close computer" onClick={() => setOpen(false)}>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </div>
        <div id="qa-computer-body" className="computer-body">
          {open ? <PanelBody /> : null}
        </div>
      </aside>
      <EnlargedDialog />
    </>
  );
}

/** The `#agent-computer-button` toggle (with the live/waiting dot) for the chat header; hidden when the Prism has no computer. */
export function ComputerButton() {
  const { visible, open, live, waiting } = useComputerButton();
  return (
    <button
      id="agent-computer-button"
      className={open ? "icon-button active" : "icon-button"}
      type="button"
      aria-expanded={open}
      aria-controls="qa-computer-panel"
      aria-label="Show Prism's computer"
      data-tooltip="Computer"
      hidden={!visible}
      onClick={() => setOpen(!getState().open)}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="4" width="18" height="12" rx="2" />
        <path d="M8 20h8M12 16v4" />
      </svg>
      <span id="agent-computer-dot" className={waiting ? "icon-badge live-dot waiting" : "icon-badge live-dot"} hidden={!live} />
    </button>
  );
}
