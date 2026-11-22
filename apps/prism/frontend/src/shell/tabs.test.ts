import type { Modes } from "@/lib/app-context";
import { panelHidden, resolveTab, sectionFor } from "./tabs";

const modes = (over: Partial<Modes> = {}): Modes => ({ v21: null, v22: null, v24: null, singleExecutive: false, ...over });

describe("resolveTab", () => {
  it("keeps tabs while capabilities are unknown", () => {
    expect(resolveTab("prisms", modes())).toBe("prisms");
    expect(resolveTab("agent", modes())).toBe("agent");
  });
  it("falls back to overview for unknown tabs and settings", () => {
    expect(resolveTab("nope", modes())).toBe("overview");
    expect(resolveTab("settings", modes())).toBe("overview");
  });
  it("gates by v21/v22/v24 exactly like the old setActiveTab", () => {
    expect(resolveTab("agent", modes({ v21: false }))).toBe("overview");
    expect(resolveTab("prisms", modes({ v22: false }))).toBe("overview");
    expect(resolveTab("spending", modes({ v22: false }))).toBe("overview");
    expect(resolveTab("operations", modes({ v22: false, v24: false }))).toBe("overview");
    // operations -> overview (v24 off) -> prisms (Home retired once v22 is on), same order as the old code.
    expect(resolveTab("operations", modes({ v22: true, v24: false }))).toBe("prisms");
    expect(resolveTab("overview", modes({ v22: true }))).toBe("prisms");
    expect(resolveTab("ask", modes({ v21: true }))).toBe("overview");
  });
  it("sidebar section follows workspace tabs", () => {
    expect(sectionFor("operations")).toBe("workspace");
    expect(sectionFor("agent")).toBe("chat");
  });
});

describe("panelHidden", () => {
  it("hides non-active, legacy under v21, v22-only without v22, v24-only without v24", () => {
    expect(panelHidden({ tab: "overview" }, "prisms", modes())).toBe(true);
    expect(panelHidden({ tab: "ask", v21Legacy: true }, "ask", modes({ v21: true }))).toBe(true);
    expect(panelHidden({ tab: "ask", v21Legacy: true }, "ask", modes({ v21: false }))).toBe(false);
    expect(panelHidden({ tab: "prisms", v22Only: true }, "prisms", modes({ v22: null }))).toBe(true);
    expect(panelHidden({ tab: "prisms", v22Only: true }, "prisms", modes({ v22: true }))).toBe(false);
    expect(panelHidden({ tab: "operations", v22Only: true, v24Only: true }, "operations", modes({ v22: true, v24: false }))).toBe(true);
  });
});
