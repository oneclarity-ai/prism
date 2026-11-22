import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { useApp, type AppApi } from "@/lib/app-context";
import { AppProvider } from "./AppProvider";
import { ConfirmDialog } from "./ConfirmDialog";

function respond(routes: Record<string, unknown | (() => unknown)>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      const match = Object.keys(routes).find((key) => path.startsWith(key));
      if (!match) return new Response(JSON.stringify({ detail: "missing" }), { status: 404 });
      const body = routes[match];
      return new Response(JSON.stringify(typeof body === "function" ? (body as () => unknown)() : body), { status: 200 });
    }),
  );
}

let api: AppApi;
function Probe() {
  const value = useApp();
  useEffect(() => {
    api = value;
  });
  return (
    <div>
      <span data-testid="tab">{value.activeTab}</span>
      <span data-testid="settings">{value.settings.isOpen ? value.settings.section : "closed"}</span>
    </div>
  );
}

const FOUNDATION = {
  "/api/v2/agent/foundation": {},
  "/api/v2/prisms/foundation": { single_executive_mode: false },
  "/api/v2/qa/status": { computers: true },
  "/api/v1/provider/status": { provider: "openai", model: "m", state: "ready", ready: true, detail: "Ready" },
  "/api/v1/microsoft/status": { is_connected: false },
};

beforeEach(() => {
  history.replaceState({}, "", "/");
  localStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

describe("AppProvider", () => {
  it("probes capabilities, retires Home when Prisms are on and opens the chats URL", async () => {
    respond(FOUNDATION);
    render(
      <AppProvider>
        <Probe />
      </AppProvider>,
    );
    await waitFor(() => expect(api.modes).toMatchObject({ v21: true, v22: true, v24: true }));
    await waitFor(() => expect(screen.getByTestId("tab")).toHaveTextContent("prisms"));
  });

  it("falls back to overview when the Prism foundation is unavailable", async () => {
    const { "/api/v2/prisms/foundation": _drop, ...rest } = FOUNDATION;
    void _drop;
    respond(rest);
    localStorage.setItem("manager-agent-tab", "prisms");
    render(
      <AppProvider>
        <Probe />
      </AppProvider>,
    );
    await waitFor(() => expect(api.modes.v22).toBe(false));
    await waitFor(() => expect(screen.getByTestId("tab")).toHaveTextContent("overview"));
  });

  it("writes /settings/<section> when settings opens and restores the page path on close", async () => {
    respond(FOUNDATION);
    render(
      <AppProvider>
        <Probe />
      </AppProvider>,
    );
    await waitFor(() => expect(api.modes.v24).toBe(true));
    await waitFor(() => expect(location.pathname).toBe("/chats"));
    act(() => api.settings.open("provider"));
    expect(screen.getByTestId("settings")).toHaveTextContent("provider");
    expect(location.pathname).toBe("/settings/provider");
    act(() => api.settings.setSection("access"));
    expect(location.pathname).toBe("/settings/access");
    expect(localStorage.getItem("manager-agent-subtab-settings")).toBe("access");
    act(() => api.settings.close());
    expect(screen.getByTestId("settings")).toHaveTextContent("closed");
    expect(location.pathname).toBe("/chats");
  });

  it("shows the toast and hides it after the timeout", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      respond(FOUNDATION);
      render(
        <AppProvider>
          <Probe />
        </AppProvider>,
      );
      act(() => api.setStatus("Saved"));
      act(() => api.setStatus("Saved"));
      await act(async () => {
        vi.advanceTimersByTime(4600);
      });
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("askDialog", () => {
  function setup() {
    respond(FOUNDATION);
    render(
      <AppProvider>
        <Probe />
        <ConfirmDialog />
      </AppProvider>,
    );
  }

  it("resolves true on confirm and null on cancel", async () => {
    setup();
    const user = userEvent.setup();
    let answer = api.askDialog({ title: "Delete?", message: "Gone for good", confirmLabel: "Delete", danger: true });
    const ok = await screen.findByRole("button", { name: "Delete", hidden: true });
    expect(ok).toHaveClass("danger");
    expect(document.getElementById("confirm-title")).toHaveTextContent("Delete?");
    await user.click(ok);
    await expect(answer).resolves.toBe(true);

    answer = api.askDialog({ title: "Again?" });
    await user.click(await screen.findByRole("button", { name: "Cancel", hidden: true }));
    await expect(answer).resolves.toBeNull();
  });

  it("returns the typed text when a field is requested", async () => {
    setup();
    const user = userEvent.setup();
    const answer = api.askDialog({ title: "Key", confirmLabel: "Save", field: { label: "Access key", type: "password" } });
    const input = await screen.findByLabelText("Access key", { selector: "input" });
    expect(input).toHaveAttribute("type", "password");
    await user.type(input, "abc123");
    await user.click(screen.getByRole("button", { name: "Save", hidden: true }));
    await expect(answer).resolves.toBe("abc123");
  });
});
