import { describe, expect, it } from "vitest";
import {
  answerText,
  introText,
  joinList,
  monitoringSchedule,
  policyAllowsSource,
  prismListKey,
  sentence,
  sourceDetail,
  splitNames,
  stateLabel,
  teamsScopeCopy,
  withoutGreeting,
} from "./helpers";
import type { OnboardingQuestion, TeamsPolicy, TriggerPolicy } from "./types";
import { prismRow } from "./test-utils";

describe("prism helpers", () => {
  it("labels lifecycle states", () => {
    expect(stateLabel({ state: "draft" })).toBe("Draft");
    expect(stateLabel({ state: "awaiting_confirmation" })).toBe("Review needed");
    expect(stateLabel({ state: "paused_for_now" as never })).toBe("paused for now");
  });

  it("builds the onboarding intro from the description", () => {
    expect(introText({ name: "Sales", description: "Research prospects. More." })).toContain("Hi, I’m Sales Prism. You set me up to: research prospects.");
    expect(introText({ name: "Ops Prism", description: "" })).toMatch(/^Hi, I’m Ops Prism\. I’ll ask/);
  });

  it("strips a model greeting and formats lists", () => {
    expect(withoutGreeting("Hello there! what do you do?")).toBe("What do you do?");
    expect(joinList(["a.", "b", "c"])).toBe("a, b and c");
    expect(joinList(undefined)).toBe("");
    expect(sentence("Done")).toBe("Done.");
    expect(sentence("Done?")).toBe("Done?");
  });

  it("describes answers and Teams scope", () => {
    const question = { choices: [{ value: "a", label: "Alpha" }] } as OnboardingQuestion;
    expect(answerText(question, { question_id: "q", selected_values: ["a", "z"], custom_text: null, skipped: false })).toBe("Alpha, z");
    expect(answerText(question, { question_id: "q", selected_values: [], custom_text: null, skipped: true })).toBe("Skip for now");
    const policy = { mode: "include_only", rules: [{ external_id: "x" }] } as TeamsPolicy;
    expect(teamsScopeCopy(policy)).toBe("Only 1 selected Teams chat is eligible to be read.");
    expect(teamsScopeCopy("loading")).toMatch(/Loading/);
    expect(policyAllowsSource(policy, { external_id: "x", label: "X" })).toBe(true);
    expect(policyAllowsSource(policy, { external_id: "y", label: "Y" })).toBe(false);
    expect(policyAllowsSource({ ...policy, mode: "all_except" }, { external_id: "x", label: "X" })).toBe(false);
    expect(sourceDetail({ external_id: "1", label: "L", chat_type: "oneOnOne", participants: ["Ann"] })).toBe("1:1 chat · Ann");
  });

  it("summarises the monitoring schedule", () => {
    const trigger = { mode: "scheduled", local_scheduler_enabled: false, next_scheduled_for: null } as TriggerPolicy;
    expect(monitoringSchedule(trigger)).toBe("Monitoring mode: Daily schedule. Local scheduler is off; run it manually until enabled.");
  });

  it("only changes the list key for visible fields", () => {
    const a = prismRow();
    expect(prismListKey([a])).toBe(prismListKey([{ ...a, updated_at: "later" }]));
    expect(prismListKey([a])).not.toBe(prismListKey([{ ...a, last_message_preview: "hi" }]));
  });

  it("normalises comma separated names", () => {
    expect(splitNames("Teams, teams , Save_File,,")).toEqual(["teams", "save_file"]);
  });
});
