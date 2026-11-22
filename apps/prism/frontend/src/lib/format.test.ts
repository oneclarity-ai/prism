import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { age, count, duration, money, plainSummary, statusMeta, time, words } from "./format";

describe("words", () => {
  it("replaces underscores and defaults to unknown", () => {
    expect(words("waiting_approval")).toBe("waiting approval");
    expect(words("")).toBe("unknown");
    expect(words(null)).toBe("unknown");
    expect(words(undefined)).toBe("unknown");
  });
});

describe("money", () => {
  it("formats with two decimals and tolerates junk", () => {
    expect(money(1.005)).toBe("$1.00");
    expect(money("2.5")).toBe("$2.50");
    expect(money(null)).toBe("$0.00");
    expect(money(undefined)).toBe("$0.00");
    expect(money("abc")).toBe("$NaN");
  });
});

describe("count", () => {
  it("uses compact notation", () => {
    expect(count(0)).toBe("0");
    expect(count(null)).toBe("0");
    expect(count(950)).toBe("950");
    expect(count(1500)).toBe(new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(1500));
    expect(count(1500)).toMatch(/1\.5/);
  });
});

describe("time", () => {
  it("returns a dash for empty or invalid values", () => {
    expect(time(null)).toBe("—");
    expect(time(undefined)).toBe("—");
    expect(time("")).toBe("—");
    expect(time("not a date")).toBe("—");
  });
  it("formats valid dates", () => {
    expect(time("2026-01-02T03:04:00Z")).toBe(
      new Date("2026-01-02T03:04:00Z").toLocaleString([], { dateStyle: "medium", timeStyle: "short" }),
    );
  });
});

describe("age", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-10T12:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("handles empty, invalid, today, singular and plural", () => {
    expect(age(null)).toBe("—");
    expect(age("garbage")).toBe("—");
    expect(age("2026-06-10T00:00:00Z")).toBe("Today");
    expect(age("2026-06-09T00:00:00Z")).toBe("1 day ago");
    expect(age("2026-06-01T12:00:00Z")).toBe("9 days ago");
    expect(age("2026-07-01T00:00:00Z")).toBe("Today");
  });
});

describe("duration", () => {
  it("prefers avg_duration_s", () => {
    expect(duration({ avg_duration_s: 59.4 })).toBe("59s");
    expect(duration({ avg_duration_s: 125 })).toBe("2m 5s");
    expect(duration({ avg_duration_s: 60 })).toBe("1m 0s");
    expect(duration({ avg_duration_s: -5 })).toBe("0s");
    expect(duration({ avg_duration_s: "abc" })).toBe("0s");
    expect(duration({ avg_duration_s: null })).toBe("0s");
  });
  it("derives from timestamps otherwise", () => {
    expect(duration({})).toBe("0s");
    expect(duration({ started_at: "2026-06-10T10:00:00Z", ended_at: "2026-06-10T10:01:30Z" })).toBe("1m 30s");
  });
  it("uses now for a run that has not ended", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-10T10:00:45Z"));
    expect(duration({ started_at: "2026-06-10T10:00:00Z" })).toBe("45s");
    vi.useRealTimers();
  });
});

describe("plainSummary", () => {
  it("strips markdown noise", () => {
    const text = "## Mission\n# Title\n- first **bold** point\n* `code` second\n\nlast_line";
    expect(plainSummary(text)).toBe("first bold point code second lastline");
  });
  it("truncates on a word boundary with an ellipsis", () => {
    const text = "alpha beta gamma delta epsilon";
    expect(plainSummary(text, 14)).toBe("alpha beta…");
    expect(plainSummary(text, 100)).toBe(text);
  });
  it("tolerates empty input", () => {
    expect(plainSummary(null)).toBe("");
    expect(plainSummary(undefined)).toBe("");
  });
});

describe("statusMeta", () => {
  it("knows statuses and falls back for the rest", () => {
    expect(statusMeta("waiting_approval")).toEqual(["Needs approval", "shield-check", "orange"]);
    expect(statusMeta("mystery_state")).toEqual(["mystery state", "circle-dashed", "gray"]);
    expect(statusMeta(undefined)).toEqual(["unknown", "circle-dashed", "gray"]);
    expect(statusMeta("constructor")[1]).toBe("circle-dashed");
  });
});
