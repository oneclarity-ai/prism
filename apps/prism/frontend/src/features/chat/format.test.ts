import { describe, expect, it } from "vitest";
import { briefDescription, confidenceText, draftState, draftStatusText, snippetFor, stampLabel, toneFor } from "./format";
import { proposal } from "./testkit";

describe("chat formatting", () => {
  it("maps proposal and execution state to a label and tone", () => {
    expect(draftState(proposal("a", "j", "X"), null)).toMatchObject({ key: "pending", label: "Awaiting approval", tone: "orange" });
    expect(draftState(proposal("a", "j", "X", { state: "executed" }), null).key).toBe("sent");
    const execution = { created_at: "2026-01-01T00:00:00Z" };
    expect(draftState(proposal("a", "j", "X", { state: "approved" }), { ...execution, state: "uncertain" }).key).toBe("uncertain");
    expect(draftState(proposal("a", "j", "X", { state: "approved" }), { ...execution, state: "failed" }).key).toBe("failed");
    expect(draftState(proposal("a", "j", "X", { state: "approved" }), null).key).toBe("approved");
    expect(draftStatusText(proposal("a", "j", "X", { state: "rejected" }), null)).toBe("Rejected. Nothing was sent.");
    expect(draftStatusText(proposal("a", "j", "X"), { ...execution, state: "failed", safe_error_detail: "Chat gone" })).toBe("Chat gone");
  });

  it("shortens descriptions at the first sentence and a word boundary", () => {
    expect(briefDescription("")).toContain("Ask me about your team");
    expect(briefDescription("Tracks releases. Also does more.")).toBe("Tracks releases.");
    const long = `${"word ".repeat(60)}end.`;
    const brief = briefDescription(long, 20);
    expect(brief.endsWith("…")).toBe(true);
    expect(brief.length).toBeLessThanOrEqual(21);
  });

  it("buckets confidence and snippets", () => {
    expect(confidenceText(0.9)).toBe("High confidence");
    expect(confidenceText(0.5)).toBe("Medium confidence");
    expect(confidenceText(0.1)).toBe("Low confidence");
    expect(snippetFor("a ".repeat(200), "zzz").endsWith("…")).toBe(true);
    expect(snippetFor("hello world", "world")).toBe("hello world");
  });

  it("labels stamps by distance and gives stable tones", () => {
    const now = new Date();
    expect(stampLabel(now.toISOString())).not.toMatch(/Yesterday/);
    const yesterday = new Date(now.getTime() - 86400000);
    expect(stampLabel(yesterday.toISOString())).toMatch(/^Yesterday, /);
    expect(toneFor("Parv")).toBe(toneFor("Parv"));
  });
});
