import { describe, expect, it } from "vitest";
import { buildTimeline } from "./build-timeline";
import { initialState } from "./store";
import { job, message, thread } from "./testkit";
import { newTurn } from "./store";
import type { ChatState, Observation } from "./types";

const base = (patch: Partial<ChatState>): ChatState => ({ ...initialState(), rendered: true, ...patch });
const kinds = (state: ChatState) => {
  const view = buildTimeline(state);
  return view.kind === "items" ? view.items.map((item) => item.type) : view.kind;
};

describe("buildTimeline", () => {
  it("is loading, then welcome when there is nothing to show", () => {
    expect(kinds(base({ loading: true }))).toBe("loading");
    expect(kinds(base({ activeThread: thread() }))).toBe("welcome");
  });

  it("keeps the pending submission visible while loading", () => {
    const pending = { content: "hi", label: "x", createdAt: "2026-01-01T10:00:00Z" };
    expect(kinds(base({ loading: true, pendingSubmission: pending }))).toEqual(["stamp", "pending"]);
  });

  it("shows progress under an unanswered question only", () => {
    const j1 = job("j1");
    const j2 = job("j2");
    const state = base({
      activeThread: thread(),
      jobs: [j1, j2],
      turns: new Map([
        ["j1", newTurn(j1)],
        ["j2", newTurn(j2)],
      ]),
      messages: [message("a", "manager", "q1", "j1", 1), message("b", "assistant", "r1", "j1", 2), message("c", "manager", "q2", "j2", 3)],
    });
    expect(kinds(state)).toEqual(["stamp", "user", "assistant", "user", "progress"]);
  });

  it("places updates between the messages around their creation time, oldest first", () => {
    const update = { id: "u1", created_at: "2026-01-01T10:02:30Z" } as Observation;
    const state = base({
      activeThread: thread(),
      messages: [message("a", "manager", "q", null, 1), message("b", "manager", "q", null, 4)],
      updates: [update],
    });
    expect(kinds(state)).toEqual(["stamp", "user", "update", "user"]);
  });

  it("adds history and load-earlier controls", () => {
    const state = base({ activeThread: thread(), anchor: "a", hasEarlier: true, messages: [message("a", "manager", "q", null, 1)] });
    expect(kinds(state).slice(0, 2)).toEqual(["history-banner", "load-earlier"]);
  });
});
