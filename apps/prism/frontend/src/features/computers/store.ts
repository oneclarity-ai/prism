import { useSyncExternalStore } from "react";
import { agentApi, errorMessage, jsonBody, operatorHeaders } from "@/lib/api";
import { emit, type PrismLike } from "@/lib/events";
import { cardKey, isActive } from "./helpers";
import { resetLive, startLive, stopLive } from "./live";
import type {
  ApprovalDecision,
  ComputerInfo,
  ComputersHost,
  PlanEdits,
  QaApproval,
  QaRun,
  QaStatus,
  SavedLogin,
  WorkFile,
} from "./types";

/*
 * Module-level store of the computers feature (port of the qa-tester.js state). Everything mutable lives in `state`;
 * React reads it through `useStoreVersion()`, which changes after every `notify()`.
 */

interface Frame {
  n: number;
  url: string;
}

const state = {
  host: null as ComputersHost | null,
  prism: null as PrismLike | null,
  runs: new Map<string, QaRun>(), // run id -> latest snapshot
  order: [] as string[], // run ids for the open Prism, newest first
  focus: null as string | null, // run shown in the computer panel
  streams: new Map<string, AbortController>(), // run id -> AbortController
  keys: new Map<string, string>(), // run id -> what chat cards depend on
  open: false,
  available: null as boolean | null,
  planEdits: new Set<string>(), // runs whose plan is open for editing
  edits: new Map<string, PlanEdits>(), // run id -> changes to send when the test starts
  screens: new Map<string, string>(), // "run:n" -> blob url
  screenLoading: new Set<string>(),
  frames: new Map<string, Frame>(), // run id -> the newest saved view of the screen
  frameLoading: new Set<string>(),
  loadingRuns: new Map<string, Promise<QaRun | null>>(),
  computers: false, // v2.4: every Prism has a computer
  computer: null as ComputerInfo | null,
  logins: [] as SavedLogin[],
  enlarged: false,
};

export type ComputersState = typeof state;
export const getState = (): ComputersState => state;

/* ---------- subscriptions ---------- */

let version = 0;
const listeners = new Set<() => void>();
const subscribe = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
export function notify(): void {
  version += 1;
  listeners.forEach((listener) => listener());
}
/** Re-render on every store change; read `getState()` in render afterwards. */
export const useStoreVersion = (): number => useSyncExternalStore(subscribe, () => version);

let clock = 0;
const clockListeners = new Set<() => void>();
const subscribeClock = (listener: () => void): (() => void) => {
  clockListeners.add(listener);
  return () => clockListeners.delete(listener);
};
/** One-second tick for the elapsed time of a running task. */
export function tickClock(): void {
  clock += 1;
  clockListeners.forEach((listener) => listener());
}
export const useClock = (): number => useSyncExternalStore(subscribeClock, () => clock);

/* ---------- derived facts ---------- */

export const isQaPrism = (prism: PrismLike | null | undefined): boolean => prism?.template_key === "qa_tester";
export const computersEnabled = (): boolean => state.computers;
export const usesComputer = (prism: PrismLike | null | undefined): boolean => Boolean(prism) && (isQaPrism(prism) || state.computers);

export const useComputersEnabled = (): boolean => useSyncExternalStore(subscribe, () => state.computers);
export const useComputerOpen = (): boolean => useSyncExternalStore(subscribe, () => state.open);

export interface ComputerButtonState {
  /** The Prism has a computer: show the button. */
  visible: boolean;
  open: boolean;
  /** A task is running (green dot). */
  live: boolean;
  /** A running task waits for the user (orange dot). */
  waiting: boolean;
}

export function useComputerButton(): ComputerButtonState {
  useStoreVersion();
  const runs = state.order.map((id) => state.runs.get(id));
  return {
    visible: usesComputer(state.prism),
    open: state.open,
    live: runs.some(isActive),
    waiting: runs.some((run) => run?.state === "waiting_approval"),
  };
}

const setStatus = (message: string, isError = false): void => state.host?.setStatus(message, isError);

/* ---------- plumbing ---------- */

export async function screenUrl(runId: string, index: number): Promise<string> {
  const key = `${runId}:${index}`;
  const have = state.screens.get(key);
  if (have) return have;
  const response = await fetch(`/api/v2/qa/runs/${runId}/screens/${index}`, { headers: operatorHeaders() });
  if (!response.ok) throw new Error("screenshot unavailable");
  const url = URL.createObjectURL(await response.blob());
  state.screens.set(key, url);
  return url;
}

export async function frameUrl(run: QaRun): Promise<string> {
  const have = state.frames.get(run.id);
  if (have && have.n === run.frame) return have.url;
  const response = await fetch(`/api/v2/qa/runs/${run.id}/frame?v=${run.frame}`, { headers: operatorHeaders() });
  if (!response.ok) throw new Error("no screen yet");
  const url = URL.createObjectURL(await response.blob());
  if (have?.url) setTimeout(() => URL.revokeObjectURL(have.url), 2000);
  state.frames.set(run.id, { n: run.frame as number, url });
  return url;
}

/** Fetch the newest saved frame for `run` once (called after every render of a screen view). */
export function ensureFrame(run: QaRun): void {
  const have = state.frames.get(run.id);
  if ((!have || have.n !== run.frame) && !state.frameLoading.has(run.id)) {
    state.frameLoading.add(run.id);
    frameUrl(run)
      .then(() => {
        if (state.focus === run.id && state.open) notify();
      })
      .catch(() => {})
      .finally(() => state.frameLoading.delete(run.id));
  }
}

/** Fetch the saved screenshot `run.screen` once. */
export function ensureScreen(run: QaRun): void {
  if (run.screen == null) return;
  const key = `${run.id}:${run.screen}`;
  if (state.screens.has(key) || state.screenLoading.has(key)) return;
  state.screenLoading.add(key);
  screenUrl(run.id, run.screen)
    .then(() => notify())
    .catch(() => {})
    .finally(() => state.screenLoading.delete(key));
}

function remember(run: QaRun): boolean {
  state.runs.set(run.id, run);
  const before = state.keys.get(run.id);
  const after = cardKey(run);
  state.keys.set(run.id, after);
  return before !== after;
}

function track(run: QaRun): void {
  if (state.prism && run.prism_id === state.prism.id && !state.order.includes(run.id)) state.order.unshift(run.id);
}

async function apply(run: QaRun): Promise<void> {
  const changed = remember(run);
  track(run);
  notify();
  if (changed && state.prism && run.prism_id === state.prism.id) {
    await state.host?.refreshMessages();
    state.host?.rerenderChat({ scroll: "auto" });
  }
}

/* ---------- following a run ---------- */

const wait = (ms: number, signal: AbortSignal): Promise<void> =>
  new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });

async function follow(runId: string): Promise<void> {
  if (state.streams.has(runId)) return;
  const controller = new AbortController();
  state.streams.set(runId, controller);
  let delay = 1000;
  try {
    while (!controller.signal.aborted) {
      let ended = false;
      try {
        const response = await fetch(`/api/v2/qa/runs/${runId}/stream`, { headers: operatorHeaders(), signal: controller.signal });
        if (!response.ok || !response.body) throw new Error("stream unavailable");
        delay = 1000;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let cut = buffer.indexOf("\n\n");
          while (cut >= 0) {
            const block = buffer.slice(0, cut);
            buffer = buffer.slice(cut + 2);
            const name = /^event: (.+)$/m.exec(block)?.[1];
            const data = /^data: (.+)$/m.exec(block)?.[1];
            if (name === "state" && data) await apply(JSON.parse(data) as QaRun);
            if (name === "end") ended = true;
            cut = buffer.indexOf("\n\n");
          }
        }
      } catch {
        if (controller.signal.aborted) return;
        // The stream dropped; fall back to a plain read, then try again.
        try {
          await apply(await agentApi<QaRun>(`/api/v2/qa/runs/${runId}`));
        } catch {
          /* retried below */
        }
      }
      if (ended || !isActive(state.runs.get(runId))) break;
      await wait(delay, controller.signal);
      delay = Math.min(delay * 2, 8000);
    }
  } finally {
    state.streams.delete(runId);
  }
}

async function loadRuns(): Promise<void> {
  if (!state.prism || !usesComputer(state.prism)) return;
  const prismId = state.prism.id;
  try {
    const runs = await agentApi<QaRun[]>(`/api/v2/prisms/${prismId}/qa/runs`);
    if (state.prism?.id !== prismId) return;
    runs.forEach(remember);
    state.order = runs.map((run) => run.id);
    runs.filter(isActive).forEach((run) => void follow(run.id));
    const active = runs.find(isActive);
    if (active && !isActive(state.runs.get(state.focus ?? ""))) state.focus = active.id;
    else if (!state.focus || !state.runs.has(state.focus)) state.focus = runs[0]?.id || null;
  } catch {
    /* the panel just shows no runs */
  }
  notify();
}

/** Load one run the chat refers to but this tab has not seen yet; concurrent callers share one request. */
export function loadRun(runId: string | undefined): Promise<QaRun | null> {
  if (!runId) return Promise.resolve(null);
  const have = state.runs.get(runId);
  if (have) return Promise.resolve(have);
  const pending = state.loadingRuns.get(runId);
  if (pending) return pending;
  const request = (async () => {
    try {
      const run = await agentApi<QaRun>(`/api/v2/qa/runs/${runId}`);
      remember(run);
      if (isActive(run)) void follow(run.id);
      notify();
      state.host?.rerenderChat({ scroll: "keep" });
      return run;
    } catch {
      return null;
    } finally {
      state.loadingRuns.delete(runId);
    }
  })();
  state.loadingRuns.set(runId, request);
  return request;
}

async function loadComputer(): Promise<void> {
  if (!state.computers || !state.prism) return;
  const prismId = state.prism.id;
  try {
    const [computer, logins] = await Promise.all([
      agentApi<ComputerInfo>(`/api/v2/prisms/${prismId}/computer`),
      agentApi<SavedLogin[]>(`/api/v2/prisms/${prismId}/logins`),
    ]);
    if (state.prism?.id !== prismId) return;
    state.computer = computer;
    state.logins = logins;
  } catch {
    /* the panel falls back to the run list */
  }
  notify();
}

/* ---------- called by the chat ---------- */

export async function checkAvailability(): Promise<boolean | null> {
  try {
    const status = await agentApi<QaStatus>("/api/v2/qa/status");
    state.available = status.available;
    state.computers = Boolean(status.computers);
  } catch {
    state.available = null;
  }
  notify();
  return state.available;
}

export function initQa(host: ComputersHost): void {
  state.host = host;
  void checkAvailability().then(() => {
    if (state.computers) onPrism(state.prism, true);
  });
}

export function onPrism(prism: PrismLike | null, force = false): void {
  const same = state.prism?.id === prism?.id;
  state.prism = prism || null;
  if (!usesComputer(prism)) {
    setOpen(false);
    return;
  }
  if (!same || force) {
    stopLive();
    state.order = [];
    state.focus = null;
    state.computer = null;
    notify();
    void loadRuns();
  } else notify();
}

// A computer-enabled Prism's task request becomes a plan card. Returns true when handled.
export async function planRequest(prism: PrismLike, threadId: string, content: string): Promise<boolean> {
  if (!usesComputer(prism)) return false;
  const result = await agentApi<{ handled?: boolean }>(`/api/v2/prisms/${prism.id}/qa/plan`, {
    method: "POST",
    ...jsonBody({ thread_id: threadId, content }),
  });
  return Boolean(result.handled);
}

export function setOpen(open: boolean): void {
  state.open = open && usesComputer(state.prism);
  notify();
  if (state.open) {
    emit("computer-opened");
    void loadRuns();
    void loadComputer();
  }
  if (!state.open) stopLive();
}

export async function focusRun(runId: string | undefined): Promise<void> {
  if (!runId || !state.prism) return;
  state.focus = runId;
  if (!state.runs.has(runId)) await loadRun(runId);
  setOpen(true);
  notify();
}

/** Show a run in the panel and open it ("Watch"). */
export function watchRun(run: QaRun): void {
  state.focus = run.id;
  setOpen(true);
}

export function selectRun(runId: string): void {
  state.focus = runId;
  notify();
}

/** Streams only while the panel is open and a task is running; otherwise nothing is held open. */
export function syncLive(run: QaRun | undefined): void {
  if (state.open && state.prism && usesComputer(state.prism) && isActive(run) && run && !run.startup_warning) {
    const prismId = state.prism.id;
    startLive(prismId, run.id, () => state.open && state.prism?.id === prismId && state.focus === run.id && isActive(state.runs.get(run.id)));
  } else stopLive();
}

export function setEnlarged(open: boolean): void {
  if (state.enlarged === open) return;
  state.enlarged = open;
  notify();
}

/* ---------- plan and run actions ---------- */

export function beginPlanEdit(runId: string): void {
  state.planEdits.add(runId);
  notify();
  state.host?.rerenderChat({ scroll: "keep" });
}

export function finishPlanEdit(run: QaRun, edits: PlanEdits | null): void {
  state.planEdits.delete(run.id);
  if (edits) {
    state.edits.set(run.id, edits);
    state.runs.set(run.id, { ...run, plan: { ...run.plan, ...edits } });
  }
  notify();
  state.host?.rerenderChat({ scroll: "keep" });
}

export async function startRun(run: QaRun, edits: PlanEdits): Promise<boolean> {
  state.focus = run.id;
  setOpen(true);
  try {
    const started = await agentApi<QaRun>(`/api/v2/qa/runs/${run.id}/start`, { method: "POST", ...jsonBody(edits || {}) });
    state.planEdits.delete(run.id);
    state.edits.delete(run.id);
    remember(started);
    track(started);
    state.focus = started.id;
    void follow(started.id);
    setOpen(true);
    await state.host?.refreshMessages();
    state.host?.rerenderChat({ scroll: "bottom" });
    return true;
  } catch (error) {
    setStatus(errorMessage(error), true);
    return false;
  }
}

export async function cancelRun(run: QaRun): Promise<void> {
  try {
    const stopped = await agentApi<QaRun>(`/api/v2/qa/runs/${run.id}/cancel`, { method: "POST" });
    await apply(stopped);
  } catch (error) {
    setStatus(errorMessage(error), true);
  }
}

/** Resolves true when the decision was sent. */
export async function decideApproval(approval: QaApproval, body: ApprovalDecision): Promise<boolean> {
  try {
    await apply(await agentApi<QaRun>(`/api/v2/qa/approvals/${approval.id}/decision`, { method: "POST", ...jsonBody(body) }));
    return true;
  } catch (error) {
    setStatus(errorMessage(error), true);
    return false;
  }
}

export async function downloadFile(runId: string, file: WorkFile): Promise<void> {
  try {
    const response = await fetch(`/api/v2/qa/runs/${runId}/files/${file.index}`, { headers: operatorHeaders() });
    if (!response.ok) throw new Error("unavailable");
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = file.name;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch {
    setStatus("That file isn't available right now.", true);
  }
}

/* ---------- the computer ---------- */

export async function resetComputer(): Promise<void> {
  const name = state.prism?.name || "Prism";
  if (!state.prism || !window.confirm(`This signs ${name} out of every site and clears its browser. Continue?`)) return;
  try {
    state.computer = await agentApi<ComputerInfo>(`/api/v2/prisms/${state.prism.id}/computer/reset`, { method: "POST" });
    state.logins = [];
    setStatus(`${name}'s computer was reset.`);
  } catch (error) {
    setStatus(errorMessage(error), true);
  }
  notify();
}

export async function removeLogin(login: SavedLogin): Promise<void> {
  if (!state.prism) return;
  try {
    state.logins = await agentApi<SavedLogin[]>(`/api/v2/prisms/${state.prism.id}/logins/${login.id}`, { method: "DELETE" });
  } catch (error) {
    setStatus(errorMessage(error), true);
  }
  notify();
}

/** Forget everything and release every stream and blob URL (tests, sign-out). */
export function resetComputers(): void {
  state.streams.forEach((controller) => controller.abort());
  state.streams.clear();
  stopLive();
  resetLive();
  state.screens.forEach((url) => URL.revokeObjectURL(url));
  state.frames.forEach((frame) => URL.revokeObjectURL(frame.url));
  Object.assign(state, {
    host: null,
    prism: null,
    order: [],
    focus: null,
    open: false,
    available: null,
    computers: false,
    computer: null,
    logins: [],
    enlarged: false,
  });
  state.runs.clear();
  state.keys.clear();
  state.planEdits.clear();
  state.edits.clear();
  state.screens.clear();
  state.screenLoading.clear();
  state.frames.clear();
  state.frameLoading.clear();
  state.loadingRuns.clear();
  notify();
}
