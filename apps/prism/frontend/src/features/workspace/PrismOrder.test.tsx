import { act, screen } from "@testing-library/react";
import { beforeAll, beforeEach, expect, it } from "vitest";
import { FormDialogProvider } from "@/components/ui";
import type { PrismLike } from "@/lib/events";
import { installDialogPolyfill } from "@/test/dialog";
import { renderWithApp } from "@/test/render";
import { emit } from "@/lib/events";
import { OperationsPage } from "./OperationsPage";
import { mockFetch } from "./test-fetch";
import { resetWorkspaceNav } from "./workspace-nav";

beforeAll(installDialogPolyfill);
beforeEach(() => {
  localStorage.clear();
  resetWorkspaceNav();
});

const prism = (name: string, extra = {}): PrismLike & Record<string, unknown> => ({
  id: `id-${name}`, name, state: "active", job_role: "Role", department: "Ops", description: "", tools_allowed: 0, tools_ask_first: 0, ...extra,
});
// Sidebar order (most recent activity first) differs from the organization endpoint order (Chief of Staff first).
const sidebar = ["Sales & Marketing", "Marketing", "Azure Watcher", "Chief of Staff"].map((n) => prism(n));
const organization = ["Chief of Staff", "Azure Watcher", "Marketing", "Sales & Marketing"].map((n) => prism(n, n === "Chief of Staff" ? { is_chief_of_staff: true } : {}));

it("lists Prism cards in the shared (sidebar) list order, not the organization endpoint order", async () => {
  mockFetch([
    ["GET", /overview$/, () => ({ agents: [], positions: [], tasks: [], runs: [], approvals: [], bugs: [], targets: [] })],
    ["GET", /prisms\/organization$/, () => ({ owner_name: "Y", members: organization })],
    ["GET", /\/brain$/, () => []],
  ]);
  renderWithApp(
    <FormDialogProvider>
      <OperationsPage />
    </FormDialogProvider>,
    { app: { activeTab: "operations" }, prisms: { list: sidebar, loading: false } },
  );
  await screen.findByText("Active Prisms");
  act(() => emit("workspace-navigate", { page: "agents" }));
  await screen.findByRole("link", { name: /Sales & Marketing, open settings/ });
  const names = [...document.querySelectorAll(".pc-card .pc-who strong")].map((n) => n.textContent);
  expect(names).toEqual(["Sales & Marketing", "Marketing", "Azure Watcher", "Chief of Staff"]);
});
