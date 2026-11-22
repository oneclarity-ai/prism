import { chatPath, initialTabFor, parseRoute, pathForView, pathForWorkspace } from "./routes";

describe("parseRoute", () => {
  it("maps the bare dashboard to default", () => {
    expect(parseRoute("/")).toEqual({ kind: "default" });
    expect(parseRoute("/dashboard/")).toEqual({ kind: "default" });
    expect(parseRoute("/dashboard")).toEqual({ kind: "default" });
  });
  it("parses settings with a default section", () => {
    expect(parseRoute("/settings")).toEqual({ kind: "settings", section: "general" });
    expect(parseRoute("/settings/provider")).toEqual({ kind: "settings", section: "provider" });
  });
  it("parses Prism chat and settings routes by short code, PR number or uuid", () => {
    expect(parseRoute("/prisms/pA7xQ2")).toEqual({ kind: "chat", key: "pA7xQ2" });
    expect(parseRoute("/prisms/PR-12/settings")).toEqual({ kind: "prism-settings", key: "PR-12", section: "overview" });
    expect(parseRoute("/prisms/pA7xQ2/settings/skills")).toEqual({ kind: "prism-settings", key: "pA7xQ2", section: "skills" });
    const id = "12345678-1234-1234-1234-123456789abc";
    expect(parseRoute(`/prisms/${id}`)).toEqual({ kind: "chat", key: id });
  });
  it("falls through to the workspace Prisms page for malformed keys (the server 404s these first)", () => {
    expect(parseRoute("/prisms/not-a-code")).toEqual({ kind: "workspace", page: "agents" });
    expect(parseRoute("/prisms/PA7xQ2")).toEqual({ kind: "workspace", page: "agents" });
  });
  it("parses runs, workspace pages and top-level pages", () => {
    expect(parseRoute("/runs/abc")).toEqual({ kind: "run", id: "abc" });
    expect(parseRoute("/run-analytics")).toEqual({ kind: "workspace", page: "usage" });
    expect(parseRoute("/organization")).toEqual({ kind: "workspace", page: "positions" });
    expect(parseRoute("/chats")).toEqual({ kind: "page", page: "prisms" });
    expect(parseRoute("/assistant")).toEqual({ kind: "page", page: "agent" });
    expect(parseRoute("/nonsense")).toEqual({ kind: "missing" });
  });
});

describe("paths", () => {
  it("builds chat and workspace paths", () => {
    expect(chatPath({ id: "x", code: "pA7xQ2" })).toBe("/prisms/pA7xQ2");
    expect(chatPath({ id: "uuid-1" })).toBe("/prisms/uuid-1");
    expect(pathForWorkspace({ page: "tasks" })).toBe("/tasks");
    expect(pathForWorkspace({ page: "runs", runId: "r 1" })).toBe("/runs/r%201");
    expect(pathForWorkspace({ page: "prism", prism: { id: "u", code: "pA7xQ2" }, section: "skills" })).toBe("/prisms/pA7xQ2/settings/skills");
    expect(pathForWorkspace({ page: "prism", id: "u" })).toBe("/prisms/u/settings/overview");
    expect(pathForView("agent")).toBe("/assistant");
    expect(pathForView("operations")).toBe("/chats");
  });
  it("derives the initial tab", () => {
    expect(initialTabFor({ kind: "workspace", page: "tasks" })).toBe("operations");
    expect(initialTabFor({ kind: "chat", key: "pA7xQ2" })).toBe("prisms");
    expect(initialTabFor({ kind: "page", page: "spending" })).toBe("spending");
    expect(initialTabFor({ kind: "default" })).toBeNull();
  });
});
