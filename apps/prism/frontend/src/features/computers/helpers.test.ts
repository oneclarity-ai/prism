import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cardKey, elapsed, isLink, minutesText, money, stateText } from "./helpers";
import { frameBoundaries } from "./live";
import { makeRun, makeWorkRun } from "./testkit";

describe("helpers", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:10:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("formats elapsed time for running and ended tasks", () => {
    expect(elapsed(makeRun())).toBe("");
    expect(elapsed(makeRun({ started_at: "2026-01-01T00:09:55Z" }))).toBe("5s");
    expect(elapsed(makeRun({ started_at: "2026-01-01T00:07:55Z" }))).toBe("2m 05s");
    expect(elapsed(makeRun({ started_at: "2026-01-01T00:00:00Z", ended_at: "2026-01-01T00:01:00Z" }))).toBe("1m 00s");
  });

  it("words the run state", () => {
    expect(stateText(makeRun({ state: "running" }))).toBe("Testing");
    expect(stateText(makeWorkRun({ state: "running" }))).toBe("Working");
    expect(stateText(makeRun({ state: "waiting_approval" }))).toBe("Waiting for you");
    expect(stateText(makeRun({ state: "starting", startup_warning: "x" }))).toBe("Waiting for workspace");
    expect(stateText(makeRun({ state: "mystery" }))).toBe("mystery");
  });

  it("formats money, minutes and the card key", () => {
    expect(money(undefined)).toBe("$0.00");
    expect(money(1.5)).toBe("$1.50");
    expect(minutesText(10)).toBe("1 min");
    expect(minutesText(300)).toBe("5 min");
    expect(minutesText(null)).toBeNull();
    const base = cardKey(makeRun());
    expect(cardKey(makeRun({ state: "running" }))).not.toBe(base);
    expect(cardKey(makeRun({ report: { counts: {} } }))).not.toBe(base);
    expect(cardKey(makeRun({ turn: 5, cost_usd: 3 }))).toBe(base);
  });

  it("links only plain http(s) URLs", () => {
    expect(isLink("https://acme.com/a?b=1")).toBe(true);
    expect(isLink("HTTP://acme.com")).toBe(true);
    expect(isLink("javascript:alert(1)")).toBe(false);
    expect(isLink("https://acme.com is great")).toBe(false);
    expect(isLink("ftp://acme.com")).toBe(false);
  });
});

describe("frameBoundaries", () => {
  const part = (body: string) => new TextEncoder().encode(`--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${body.length}\r\n\r\n${body}\r\n`);
  const join = (...chunks: Uint8Array<ArrayBuffer>[]) => {
    const out = new Uint8Array(chunks.reduce((n, c) => n + c.length, 0));
    let at = 0;
    for (const chunk of chunks) {
      out.set(chunk, at);
      at += chunk.length;
    }
    return out;
  };

  it("extracts every complete frame and keeps the partial rest", () => {
    const whole = part("AAAA");
    const second = part("BBBBBB");
    const { frames, rest } = frameBoundaries(join(whole, second.subarray(0, 40)));
    expect(frames.map((f) => new TextDecoder().decode(f))).toEqual(["AAAA"]);
    const more = frameBoundaries(join(rest, second.subarray(40)));
    expect(more.frames.map((f) => new TextDecoder().decode(f))).toEqual(["BBBBBB"]);
  });

  it("skips parts without a content length", () => {
    const junk = new TextEncoder().encode("--frame\r\nX: y\r\n\r\n");
    expect(frameBoundaries(join(junk, part("Z"))).frames).toHaveLength(1);
  });
});
