import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { navigation } from "@/features/legacy/microsoft";
import { mockFetch } from "@/features/legacy/testing";
import { PrismsContext } from "@/features/prisms/PrismsContext";
import { AppContext, type AppApi, type SettingsSection } from "@/lib/app-context";
import { STORAGE_KEYS } from "@/lib/storage";
import { fakeApp } from "@/test/render";
import { pressEscape } from "@/test/dialog";
import { SettingsDialog } from "./SettingsDialog";

interface Harness {
  app: AppApi;
  open: () => void;
}

/** Keeps the shell's settings state (open + section) so section changes re-render like the real AppProvider. */
function renderSettings(overrides: Partial<AppApi> = {}, initial: { open?: boolean; section?: SettingsSection } = {}): Harness & { ui: ReturnType<typeof render> } {
  const base = fakeApp(overrides);
  const handle = { app: base, open: () => {} } as Harness;
  const spies = { open: vi.fn(), close: vi.fn(), setSection: vi.fn() };
  function Shell({ children }: { children: ReactNode }) {
    const [isOpen, setOpen] = useState(initial.open ?? true);
    const [section, setSection] = useState<SettingsSection>(initial.section ?? "preferences");
    spies.open.mockImplementation((next?: SettingsSection) => {
      setOpen(true);
      if (next) setSection(next);
    });
    spies.close.mockImplementation(() => setOpen(false));
    spies.setSection.mockImplementation((next: SettingsSection) => setSection(next));
    const settings = { isOpen, section, open: spies.open, close: spies.close, setSection: spies.setSection };
    const app = { ...base, ...overrides, settings };
    handle.app = app;
    handle.open = () => settings.open();
    return <AppContext.Provider value={app}>{children}</AppContext.Provider>;
  }
  const ui = render(
    <Shell>
      <PrismsContext.Provider value={{ prisms: [], loading: false, selectedId: null, reload: async () => {} }}>
        <SettingsDialog />
      </PrismsContext.Provider>
    </Shell>,
  );
  return Object.assign(handle, { ui });
}

const tab = (name: string) => document.querySelector(`[data-subtab-target="${name}"]`) as HTMLButtonElement;
const panel = (name: string) => document.querySelector(`[data-subtab-group="settings"][data-subtab="${name}"]`) as HTMLElement;
const dialog = () => document.getElementById("settings-dialog") as HTMLDialogElement;

beforeEach(() => {
  localStorage.clear();
  mockFetch({ "GET /api/v1/provider/credentials": [] });
});
afterEach(() => vi.unstubAllGlobals());

describe("modal behaviour", () => {
  it("opens the native dialog when the shell says so and focuses the active tab", () => {
    renderSettings({}, { open: true });
    expect(dialog()).toHaveAttribute("open");
    expect(tab("preferences")).toHaveFocus();
  });

  it("stays closed until opened, then closes again", () => {
    const h = renderSettings({}, { open: false });
    expect(dialog()).not.toHaveAttribute("open");
    act(() => h.open());
    expect(dialog()).toHaveAttribute("open");
    act(() => void h.app.settings.close());
    expect(dialog()).not.toHaveAttribute("open");
  });

  it("reports Escape, the close button and a backdrop click through settings.close()", async () => {
    const h = renderSettings();
    act(() => pressEscape(dialog()));
    expect(h.app.settings.close).toHaveBeenCalledTimes(1);
    act(() => h.open());
    await userEvent.click(screen.getByRole("button", { name: "Close settings" }));
    expect(h.app.settings.close).toHaveBeenCalledTimes(2);
    act(() => h.open());
    fireEvent.click(dialog());
    expect(h.app.settings.close).toHaveBeenCalledTimes(3);
  });

  it("does not close when clicking inside the dialog", async () => {
    const h = renderSettings();
    await userEvent.click(screen.getByText("Choose how you want Prism to look and behave."));
    expect(h.app.settings.close).not.toHaveBeenCalled();
  });
});

describe("sections", () => {
  it("shows only the current section and marks its tab selected", () => {
    renderSettings({}, { section: "connections" });
    expect(panel("connections")).toBeVisible();
    expect(panel("preferences")).not.toBeVisible();
    expect(tab("connections")).toHaveAttribute("aria-selected", "true");
    expect(tab("connections")).toHaveAttribute("tabindex", "0");
    expect(tab("preferences")).toHaveAttribute("aria-selected", "false");
    expect(tab("preferences")).toHaveAttribute("tabindex", "-1");
    expect(tab("connections")).toHaveClass("nav-item", "active");
  });

  it("switches section on click and remembers it", async () => {
    const h = renderSettings();
    await userEvent.click(screen.getByRole("tab", { name: "Connections" }));
    expect(h.app.settings.setSection).toHaveBeenCalledWith("connections");
    expect(localStorage.getItem(STORAGE_KEYS.subtab("settings"))).toBe("connections");
    expect(panel("connections")).toBeVisible();
  });

  it("hides the v2.2-only tabs until the Prism workspace is on", () => {
    renderSettings({ modes: { v21: false, v22: false, v24: false, singleExecutive: false } });
    expect(tab("skills")).toHaveAttribute("hidden");
    expect(tab("archived")).toHaveAttribute("hidden");
    expect(tab("skills")).toHaveAttribute("data-v22-only");
  });

  it("shows them with v2.2 enabled", () => {
    renderSettings();
    expect(tab("skills")).not.toHaveAttribute("hidden");
    expect(tab("archived")).not.toHaveAttribute("hidden");
  });

  it("General links jump to a section; Spending closes settings and opens the page", async () => {
    const h = renderSettings({}, { section: "general" });
    await userEvent.click(document.querySelector('[data-settings-link="access"]') as HTMLElement);
    expect(h.app.settings.setSection).toHaveBeenCalledWith("access");
    act(() => void h.app.settings.setSection("general"));
    await userEvent.click(document.querySelector('[data-settings-link="spending"]') as HTMLElement);
    expect(h.app.settings.close).toHaveBeenCalled();
    expect(h.app.setActiveTab).toHaveBeenCalledWith("spending");
  });

  it("falls back to the first tab for an unknown section", () => {
    renderSettings({}, { section: "bogus" as SettingsSection });
    expect(tab("account")).toHaveAttribute("aria-selected", "true");
  });
});

describe("tab keyboard navigation", () => {
  it("moves with arrows (wrapping), Home and End, selecting as it goes", async () => {
    renderSettings({}, { section: "preferences" });
    tab("preferences").focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(tab("notifications")).toHaveFocus();
    expect(tab("notifications")).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowUp}{ArrowUp}");
    expect(tab("account")).toHaveFocus();
    await userEvent.keyboard("{ArrowUp}");
    expect(tab("developer")).toHaveFocus();
    await userEvent.keyboard("{Home}");
    expect(tab("account")).toHaveFocus();
    await userEvent.keyboard("{End}");
    expect(tab("developer")).toHaveFocus();
    await userEvent.keyboard("{ArrowRight}");
    expect(tab("account")).toHaveFocus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(tab("developer")).toHaveFocus();
  });

  it("skips tabs that are hidden", async () => {
    renderSettings({ modes: { v21: false, v22: false, v24: false, singleExecutive: false } }, { section: "notifications" });
    tab("notifications").focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(tab("general")).toHaveFocus();
  });

  it("ignores keys that are not navigation", async () => {
    const h = renderSettings();
    tab("preferences").focus();
    await userEvent.keyboard("a");
    expect(h.app.settings.setSection).not.toHaveBeenCalled();
  });
});

describe("settings search", () => {
  it("filters tabs by title and section text", async () => {
    renderSettings();
    await userEvent.type(document.getElementById("settings-search") as HTMLInputElement, "contrast");
    expect(tab("preferences")).not.toHaveClass("search-hidden");
    expect(tab("account")).toHaveClass("search-hidden");
    expect(tab("developer")).toHaveClass("search-hidden");
    expect(document.getElementById("settings-search-empty")).not.toBeVisible();
    // Group labels with nothing left under them disappear too.
    const labels = [...document.querySelectorAll(".settings-nav-label")];
    expect(labels.map((label) => [label.textContent, label.classList.contains("search-hidden")])).toEqual([
      ["Account", false],
      ["Workspace", true],
      ["Advanced", true],
    ]);
  });

  it("says so when nothing matches, and restores everything when cleared", async () => {
    renderSettings();
    const input = document.getElementById("settings-search") as HTMLInputElement;
    await userEvent.type(input, "zzzz");
    expect(document.getElementById("settings-search-empty")).toBeVisible();
    expect(document.getElementById("settings-search-empty")).toHaveTextContent("No matching settings.");
    await userEvent.clear(input);
    expect(document.getElementById("settings-search-empty")).not.toBeVisible();
    expect(document.querySelectorAll(".nav-item.search-hidden")).toHaveLength(0);
  });

  it("Enter opens the first remaining match", async () => {
    const h = renderSettings({}, { section: "account" });
    const input = document.getElementById("settings-search") as HTMLInputElement;
    await userEvent.type(input, "ngrok{Enter}");
    // Only the Access section mentions ngrok.
    expect(h.app.settings.setSection).toHaveBeenCalledWith("access");
    expect(localStorage.getItem(STORAGE_KEYS.subtab("settings"))).toBe("access");
  });

  it("matches the tab title case-insensitively", async () => {
    renderSettings();
    await userEvent.type(document.getElementById("settings-search") as HTMLInputElement, "ARCHIVED");
    expect(tab("archived")).not.toHaveClass("search-hidden");
  });
});

describe("preferences and notifications", () => {
  it("writes display size, contrast and the Enter preference to the same keys as before", async () => {
    renderSettings();
    await userEvent.selectOptions(document.getElementById("size-select") as HTMLSelectElement, "large");
    expect(localStorage.getItem("prism-pref-ui-size")).toBe("large");
    await userEvent.selectOptions(document.getElementById("contrast-select") as HTMLSelectElement, "on");
    expect(localStorage.getItem("prism-pref-contrast")).toBe("on");
    await userEvent.selectOptions(document.getElementById("contrast-select") as HTMLSelectElement, "system");
    expect(localStorage.getItem("prism-pref-contrast")).toBeNull();
    await userEvent.click(document.getElementById("pref-enter-newline") as HTMLElement);
    expect(localStorage.getItem("prism-pref-enter-newline")).toBe("1");
    expect(document.getElementById("pref-enter-newline")).toBeChecked();
    await userEvent.click(document.getElementById("pref-enter-newline") as HTMLElement);
    expect(localStorage.getItem("prism-pref-enter-newline")).toBeNull();
  });

  it("stores the approvals toggle as 0 only when off", async () => {
    renderSettings();
    const toggle = document.getElementById("pref-notify-approvals") as HTMLInputElement;
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    expect(localStorage.getItem("prism-pref-notify-approvals")).toBe("0");
    expect(toggle).not.toBeChecked();
  });

  it("shows the browser permission and offers to enable it when undecided", async () => {
    const request = vi.fn(async () => "granted" as NotificationPermission);
    vi.stubGlobal("Notification", Object.assign(function Notification() {}, { permission: "default", requestPermission: request }));
    renderSettings({}, { section: "notifications" });
    expect(document.getElementById("pref-notify-status")).toHaveTextContent("Off");
    const enable = document.getElementById("pref-notify-enable") as HTMLButtonElement;
    expect(enable).toBeVisible();
    await userEvent.click(enable);
    await waitFor(() => expect(document.getElementById("pref-notify-status")).toHaveTextContent("On"));
    expect(document.getElementById("pref-notify-status")).toHaveClass("green");
    expect(enable).not.toBeVisible();
  });

  it("marks a blocked permission", () => {
    vi.stubGlobal("Notification", Object.assign(function Notification() {}, { permission: "denied", requestPermission: vi.fn() }));
    renderSettings({}, { section: "notifications" });
    expect(document.getElementById("pref-notify-status")).toHaveTextContent("Blocked");
    expect(document.getElementById("pref-notify-status")).toHaveClass("orange");
  });

  it("shows the browser time zone", () => {
    renderSettings();
    expect(document.getElementById("pref-timezone")?.textContent).toBeTruthy();
  });
});

describe("account and connections", () => {
  it("keeps the static account copy until Microsoft status arrives", () => {
    renderSettings({}, { section: "account" });
    expect(document.getElementById("settings-account-name")).toHaveTextContent("Microsoft account");
    expect(document.getElementById("settings-account-avatar")).toHaveTextContent("M");
    expect(document.getElementById("account-menu-email")).toHaveTextContent("No Microsoft account connected");
    const button = document.getElementById("connect-microsoft-button") as HTMLButtonElement;
    expect(button).toHaveTextContent("Connect Microsoft account");
    expect(button).toHaveClass("button", "secondary");
    expect(button).toBeEnabled();
    expect(document.getElementById("conn-microsoft-detail")).toHaveTextContent("Checking connection.");
  });

  it("shows the connected account with initials and a Switch button", () => {
    renderSettings({
      microsoft: { is_connected: true, is_auth_configured: true, connection: { display_name: "Ada Lovelace", user_principal_name: "ada@example.test" } },
    });
    expect(document.getElementById("settings-account-name")).toHaveTextContent("Ada Lovelace");
    expect(document.getElementById("settings-account-avatar")).toHaveTextContent("AL");
    expect(document.getElementById("account-menu-email")).toHaveTextContent("ada@example.test");
    expect(document.getElementById("connect-microsoft-button")).toHaveTextContent("Switch Microsoft account");
    expect(document.getElementById("conn-microsoft-detail")).toHaveTextContent("Signed in as ada@example.test.");
    expect(document.getElementById("conn-microsoft-badge")).toHaveTextContent("Connected");
    expect(document.getElementById("conn-microsoft-badge")).toHaveClass("green");
  });

  it("disables Connect when Microsoft auth is not configured, drops the secondary style when disconnected", () => {
    renderSettings({ microsoft: { is_connected: false, is_auth_configured: false, connection: null } });
    const button = document.getElementById("connect-microsoft-button") as HTMLButtonElement;
    expect(button).toBeDisabled();
    expect(button).not.toHaveClass("secondary");
    expect(document.getElementById("conn-microsoft-badge")).toHaveTextContent("Needs attention");
    expect(document.getElementById("conn-microsoft-badge")).toHaveClass("orange");
  });

  it("Connect redirects to the OAuth start", async () => {
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    renderSettings({ microsoft: { is_connected: false, is_auth_configured: true, connection: null } });
    await userEvent.click(document.getElementById("connect-microsoft-button") as HTMLElement);
    expect(assign).toHaveBeenCalledWith("/api/v1/microsoft/auth/start");
  });

  it("asks before switching an existing account", async () => {
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    const askDialog = vi.fn(async () => null);
    renderSettings({ askDialog, microsoft: { is_connected: true, is_auth_configured: true, connection: { display_name: "Ada" } } });
    await userEvent.click(document.getElementById("connect-microsoft-button") as HTMLElement);
    expect(askDialog).toHaveBeenCalledWith(expect.objectContaining({ title: "Switch Microsoft account?", message: "Switch from Ada to a different account." }));
    expect(assign).not.toHaveBeenCalled();
  });

  it("reports provider and computers status", () => {
    renderSettings({
      providerStatus: { provider: "openai", model: "gpt-x", state: "ready", ready: true, detail: "All good" },
      modes: { v21: false, v22: true, v24: false, singleExecutive: false },
    });
    expect(document.getElementById("conn-provider-detail")).toHaveTextContent("All good");
    expect(document.getElementById("conn-provider-badge")).toHaveTextContent("Connected");
    expect(document.getElementById("conn-engine-detail")).toHaveTextContent("Computer features are not enabled on this server.");
    expect(document.getElementById("conn-engine-badge")).toHaveTextContent("Needs attention");
  });

  it("keeps 'Checking availability.' while the computer probe is pending", () => {
    renderSettings({ modes: { v21: null, v22: null, v24: null, singleExecutive: false } });
    expect(document.getElementById("conn-engine-detail")).toHaveTextContent("Checking availability.");
  });

  it("the provider nav dot shows only when the provider needs attention", () => {
    renderSettings({ providerStatus: { provider: "openai", model: null, state: "not_configured", ready: false, detail: "No key" } });
    expect(document.getElementById("provider-nav-dot")).not.toHaveAttribute("hidden");
  });

  it("hides the dot when ready or unavailable", () => {
    const { ui } = renderSettings({ providerStatus: { provider: "openai", model: null, state: "ready", ready: true, detail: "" } });
    expect(document.getElementById("provider-nav-dot")).toHaveAttribute("hidden");
    ui.unmount();
    renderSettings({ providerStatus: { provider: "unknown", model: null, state: "unavailable", ready: false, detail: "" } });
    expect(document.getElementById("provider-nav-dot")).toHaveAttribute("hidden");
  });
});

describe("access", () => {
  it("saves a trimmed key, tells the user and reloads the data", async () => {
    const askDialog = vi.fn(async () => "  secret-key  ");
    const h = renderSettings({ askDialog }, { section: "access" });
    await userEvent.click(screen.getByRole("button", { name: "Set access key" }));
    expect(askDialog).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Operator access key", confirmLabel: "Save", field: { label: "Access key", type: "password" } }),
    );
    expect(localStorage.getItem(STORAGE_KEYS.operatorToken)).toBe("secret-key");
    expect(h.app.setStatus).toHaveBeenCalledWith("Operator access key saved in this browser.");
    expect(h.app.refresh).toHaveBeenCalled();
  });

  it("removes the key when left blank, with the replace wording when one exists", async () => {
    localStorage.setItem(STORAGE_KEYS.operatorToken, "old");
    const askDialog = vi.fn(async () => "");
    const h = renderSettings({ askDialog }, { section: "access" });
    await userEvent.click(screen.getByRole("button", { name: "Set access key" }));
    expect(askDialog).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining("Replace the operator access key") }));
    expect(localStorage.getItem(STORAGE_KEYS.operatorToken)).toBeNull();
    expect(h.app.setStatus).toHaveBeenCalledWith("Operator access key removed from this browser.");
  });

  it("changes nothing when the dialog is dismissed", async () => {
    const h = renderSettings({ askDialog: vi.fn(async () => null) }, { section: "access" });
    await userEvent.click(screen.getByRole("button", { name: "Set access key" }));
    expect(h.app.refresh).not.toHaveBeenCalled();
    expect(localStorage.getItem(STORAGE_KEYS.operatorToken)).toBeNull();
  });
});

describe("developer", () => {
  it("opens docs and health in a new tab safely", () => {
    renderSettings({}, { section: "developer" });
    const docs = within(panel("developer")).getByRole("link", { name: "Open docs" });
    expect(docs).toHaveAttribute("href", "/docs");
    expect(docs).toHaveAttribute("target", "_blank");
    expect(docs.getAttribute("rel")).toContain("noopener");
    expect(within(panel("developer")).getByRole("link", { name: "Open /health" })).toHaveAttribute("href", "/health");
  });
});
