import { useSyncExternalStore } from "react";
import { operatorHeaders } from "@/lib/api";

/*
 * One open stream per Prism (multipart JPEG frames). Every <img> showing the screen (panel, enlarged popup) reads the
 * newest frame from this store, so the panel can re-render freely without dropping the connection.
 */

export interface LiveSnapshot {
  prismId: string | null;
  runId: string | null;
  url: string | null;
  status: string;
}

const CONNECTING = "Connecting live view…";

const live = {
  prismId: null as string | null,
  runId: null as string | null,
  controller: null as AbortController | null,
  url: null as string | null,
  retry: null as ReturnType<typeof setTimeout> | null,
  status: CONNECTING,
};

let snapshot: LiveSnapshot = { prismId: null, runId: null, url: null, status: CONNECTING };
const listeners = new Set<() => void>();

function publish(): void {
  if (snapshot.prismId === live.prismId && snapshot.runId === live.runId && snapshot.url === live.url && snapshot.status === live.status) return;
  snapshot = { prismId: live.prismId, runId: live.runId, url: live.url, status: live.status };
  listeners.forEach((listener) => listener());
}

const subscribe = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export const useLive = (): LiveSnapshot => useSyncExternalStore(subscribe, () => snapshot);
export const getLive = (): LiveSnapshot => snapshot;

function liveStatus(text: string): void {
  live.status = text;
  publish();
}

function indexOfBytes(buffer: Uint8Array, pattern: number[]): number {
  outer: for (let i = 0; i <= buffer.length - pattern.length; i += 1) {
    for (let j = 0; j < pattern.length; j += 1) if (buffer[i + j] !== pattern[j]) continue outer;
    return i;
  }
  return -1;
}

/** Split a multipart body into complete JPEG frames (`content-length` headers), returning the unread rest. */
export function frameBoundaries(input: Uint8Array<ArrayBuffer>): { frames: Uint8Array<ArrayBuffer>[]; rest: Uint8Array<ArrayBuffer> } {
  let buffer = input;
  const frames: Uint8Array<ArrayBuffer>[] = [];
  for (;;) {
    const end = indexOfBytes(buffer, [13, 10, 13, 10]);
    if (end < 0) break;
    const head = new TextDecoder().decode(buffer.subarray(0, end));
    const length = Number((/content-length:\s*(\d+)/i.exec(head) || [])[1]);
    if (!length) {
      buffer = buffer.subarray(end + 4);
      continue;
    }
    if (buffer.length < end + 4 + length) break;
    frames.push(buffer.slice(end + 4, end + 4 + length));
    // The trailing CRLF can arrive in the next network chunk.
    buffer = buffer.subarray(end + 4 + length);
  }
  return { frames, rest: buffer };
}

async function readLive(controller: AbortController, prismId: string): Promise<void> {
  const response = await fetch(`/api/v2/prisms/${prismId}/computer/live`, { headers: operatorHeaders(), signal: controller.signal, cache: "no-store" });
  if (!response.ok || !response.body) throw new Error("asleep");
  const reader = response.body.getReader();
  let buffer: Uint8Array<ArrayBuffer> = new Uint8Array(0);
  for (;;) {
    const watchdog = setTimeout(() => controller.abort(), 10000);
    let chunk;
    try {
      chunk = await reader.read();
    } finally {
      clearTimeout(watchdog);
    }
    const { done, value } = chunk;
    if (done) return;
    const joined = new Uint8Array(buffer.length + value.length);
    joined.set(buffer);
    joined.set(value, buffer.length);
    const parsed = frameBoundaries(joined);
    buffer = parsed.rest;
    const newest = parsed.frames.at(-1); // a slow tab shows the newest frame, never a backlog
    if (!newest || controller.signal.aborted) continue;
    const url = URL.createObjectURL(new Blob([newest], { type: "image/jpeg" }));
    const decoded = new Image();
    decoded.src = url;
    try {
      await decoded.decode();
    } catch {
      URL.revokeObjectURL(url);
      continue;
    }
    if (controller.signal.aborted || live.controller !== controller) {
      URL.revokeObjectURL(url);
      return;
    }
    const previous = live.url;
    live.url = url;
    live.status = "Live · continuous screen";
    publish();
    if (previous) setTimeout(() => URL.revokeObjectURL(previous), 1000);
  }
}

export function stopLive(): void {
  if (live.retry) clearTimeout(live.retry);
  live.retry = null;
  live.controller?.abort();
  live.controller = null;
}

/** `shouldRetry` decides whether a dropped stream reconnects (panel open, same Prism and run, run still active). */
export function startLive(prismId: string, runId: string, shouldRetry: () => boolean): void {
  // A reconnect is already scheduled: the status change that re-rendered the panel must not skip the delay.
  if ((live.controller || live.retry) && live.prismId === prismId && live.runId === runId) return;
  stopLive();
  if ((live.prismId !== prismId || live.runId !== runId) && live.url) {
    URL.revokeObjectURL(live.url);
    live.url = null;
  }
  live.prismId = prismId;
  live.runId = runId;
  const controller = new AbortController();
  live.controller = controller;
  live.status = CONNECTING;
  publish();
  readLive(controller, prismId)
    .catch(() => {})
    .finally(() => {
      if (live.controller !== controller) return;
      live.controller = null; // the computer was still starting, or the stream dropped: try again shortly
      liveStatus("Live view disconnected · reconnecting…");
      live.retry = setTimeout(() => {
        live.retry = null;
        if (shouldRetry()) startLive(prismId, runId, shouldRetry);
      }, 1000);
    });
}

/** Drop everything (tests, sign-out). */
export function resetLive(): void {
  stopLive();
  if (live.url) URL.revokeObjectURL(live.url);
  live.url = null;
  live.prismId = null;
  live.runId = null;
  live.status = CONNECTING;
  publish();
}
