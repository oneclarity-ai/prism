import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { on } from "@/lib/events";
import { renderWithApp } from "@/test/render";
import { ApprovalsPage } from "./ApprovalsPage";
import { WorkPage } from "./WorkPage";
import { mockFetch } from "./test-fetch";
import { resetUnifiedWork } from "./unified-work";

const prism = { id: "p1", name: "Sales" };
const approval = { id: "a1", kind: "tool", prism_id: "p1", prism_name: "Sales", run_id: "r1", run_title: "Run", can_decide_here: true, payload: { summary: "<b>Send it</b>" } };

beforeEach(() => resetUnifiedWork());

describe("Work and Approvals tabs", () => {
  it("loads runs on tab visit and opens a Prism with the computer run", async () => {
    mockFetch([
      ["GET", /^\/api\/v2\/prisms\?/, () => [prism]],
      ["GET", /^\/api\/v2\/work\/status$/, () => ({ message: "Computers ready", available: true })],
      ["GET", /^\/api\/v2\/work\/runs/, () => [{ id: "r1", title: "Research", state: "running", active: true, prism_id: "p1", prism_name: "Sales", cost_usd: 0.5, activity: "<i>x</i>" }]],
      ["GET", /^\/api\/v2\/work\/approvals/, () => []],
    ]);
    const opened: unknown[] = [];
    const off = [on("open-agent", (d) => opened.push(d)), on("focus-computer-run", (d) => opened.push(d))];
    const { app } = renderWithApp(<WorkPage />, { app: { activeTab: "work" } });
    expect(await screen.findByText("Research")).toBeInTheDocument();
    expect(screen.getByText("<i>x</i>")).toBeInTheDocument();
    expect(screen.getByText("Computers ready")).toBeInTheDocument();
    expect(document.getElementById("work-status")).toHaveTextContent("1 recent task.");
    await userEvent.click(screen.getByRole("button", { name: "Watch computer" }));
    expect(app.setActiveTab).toHaveBeenCalledWith("agent");
    expect(opened).toEqual([{ prism }, { runId: "r1" }]);
    off.forEach((f) => f());
  });

  it("sends the decision and reloads the approvals inbox", async () => {
    let pending = true;
    const calls = mockFetch([
      ["GET", /^\/api\/v2\/prisms\?/, () => [prism]],
      ["GET", /^\/api\/v2\/work\/approvals/, () => (pending ? [approval] : [])],
      ["POST", /^\/api\/v2\/qa\/approvals\/a1\/decision$/, () => ((pending = false), {})],
    ]);
    renderWithApp(<ApprovalsPage />, { app: { activeTab: "approvals" } });
    expect(await screen.findByText("<b>Send it</b>")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(calls.find((c) => c.path.endsWith("/decision"))?.body).toEqual({ decision: "approve" }));
    expect(await screen.findByText("No computer actions are waiting for approval.")).toBeInTheDocument();
    expect(document.getElementById("work-approval-list")).toHaveClass("list", "empty-state");
  });
});
