import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { renderWithApp } from "@/test/render";
import { setNavCount } from "@/lib/nav-counts";
import { NotificationsSidebarPanel } from "./NotificationsSidebarPanel";
import { WorkspaceSidebarPanel } from "./WorkspaceSidebarPanel";
import { getWorkspaceNav, resetWorkspaceNav } from "./workspace-nav";

beforeEach(() => {
  localStorage.clear();
  resetWorkspaceNav();
});

const page = (name: string) => document.querySelector<HTMLElement>(`[data-workspace-page='${name}']`)!;

describe("WorkspaceSidebarPanel", () => {
  it("navigates the workspace and switches to the operations tab", async () => {
    const { app } = renderWithApp(<WorkspaceSidebarPanel />, { app: { activeTab: "operations" } });
    await userEvent.click(page("tasks"));
    expect(getWorkspaceNav().page).toBe("tasks");
    expect(app.setActiveTab).toHaveBeenCalledWith("operations");
    expect(localStorage.getItem("prism-workspace-page")).toBe("tasks");
  });

  it("highlights the current page only while operations is showing, and the Prisms button also covers the org chart", () => {
    const { unmount } = renderWithApp(<WorkspaceSidebarPanel />, { app: { activeTab: "operations" } });
    expect(page("overview")).toHaveClass("active");
    expect(page("overview")).toHaveAttribute("aria-current", "page");
    expect(page("tasks")).not.toHaveClass("active");
    unmount();
    renderWithApp(<WorkspaceSidebarPanel />, { app: { activeTab: "prisms" } });
    expect(page("overview")).not.toHaveClass("active");
    expect(page("overview")).not.toHaveAttribute("aria-current");
  });

  it("shows the count badges pushed through nav-counts", () => {
    renderWithApp(<WorkspaceSidebarPanel />);
    const badge = document.querySelector<HTMLElement>("[data-workspace-count='tasks']")!;
    expect(badge).not.toBeVisible();
    act(() => setNavCount("workspace:tasks", 3));
    expect(badge).toBeVisible();
    expect(badge).toHaveTextContent("3");
    act(() => setNavCount("workspace:tasks", 0));
    expect(badge).not.toBeVisible();
    act(() => setNavCount("work-approvals", 2));
    expect(document.getElementById("work-approval-count")).toHaveTextContent("2");
  });

  it("gates items by the v22/v24 modes", () => {
    const { unmount } = renderWithApp(<WorkspaceSidebarPanel />, { app: { modes: { v21: false, v22: true, v24: false, singleExecutive: false } } });
    expect(page("overview")).not.toBeVisible();
    expect(page("tasks")).not.toBeVisible();
    expect(page("brain")).toBeVisible();
    expect(document.getElementById("nav-spending")).toBeVisible();
    expect(document.getElementById("workspace-legacy-links")).toBeVisible();
    unmount();
    renderWithApp(<WorkspaceSidebarPanel />, { app: { modes: { v21: null, v22: null, v24: null, singleExecutive: false } } });
    expect(page("brain")).not.toBeVisible();
    expect(document.getElementById("nav-spending")).not.toBeVisible();
  });

  it("legacy links switch tab and close the narrow sidebar", async () => {
    const { app } = renderWithApp(<WorkspaceSidebarPanel />, { app: { modes: { v21: false, v22: true, v24: false, singleExecutive: false } } });
    await userEvent.click(document.querySelector("[data-tab-target='approvals']")!);
    expect(app.setActiveTab).toHaveBeenCalledWith("approvals");
    expect(app.closeSidebarIfNarrow).toHaveBeenCalled();
  });
});

describe("NotificationsSidebarPanel", () => {
  it("opens notification settings and closes the narrow sidebar", async () => {
    const { app } = renderWithApp(<NotificationsSidebarPanel />);
    await userEvent.click(screen.getByRole("button", { name: /Notification settings/ }));
    expect(app.settings.open).toHaveBeenCalledWith("notifications");
    expect(app.closeSidebarIfNarrow).toHaveBeenCalled();
  });

  it("links to approvals and the brain", async () => {
    renderWithApp(<NotificationsSidebarPanel />);
    await userEvent.click(screen.getByRole("button", { name: /Brain facts to review/ }));
    expect(getWorkspaceNav().page).toBe("brain");
  });
});
