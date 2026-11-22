import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockFetch } from "@/features/legacy/testing";
import type { ProviderStatus } from "@/lib/app-context";
import { renderWithApp } from "@/test/render";
import { ProviderPane } from "./ProviderPane";

const status: ProviderStatus = { provider: "anthropic", model: "claude-live-1", state: "ready", ready: true, detail: "Ready via server environment" };

const anthropic = {
  provider: "anthropic",
  label: "Anthropic",
  configured: false,
  can_manage: true,
  is_active_provider: true,
  model: null,
  masked_key: null,
  base_url: null,
  api_version: null,
  base_url_required: false,
  needs_base_url: false,
  needs_api_version: false,
  default_model_hint: "claude-default",
};
const openai = {
  ...anthropic,
  provider: "openai",
  label: "OpenAI",
  configured: true,
  is_active_provider: false,
  model: "gpt-saved",
  masked_key: "sk-…1234",
  default_model_hint: "gpt-default",
};
const azure = {
  ...anthropic,
  provider: "azure_openai",
  label: "Azure OpenAI",
  is_active_provider: false,
  needs_base_url: true,
  base_url_required: true,
  needs_api_version: true,
  default_model_hint: "gpt-5-nano",
};

let net: ReturnType<typeof mockFetch>;

beforeEach(() => {
  net = mockFetch({
    "GET /api/v1/provider/credentials": [anthropic, openai, azure],
  });
});
afterEach(() => vi.unstubAllGlobals());

async function renderPane(app: Parameters<typeof renderWithApp>[1] = {}) {
  const view = renderWithApp(<ProviderPane active />, { ...app, app: { providerStatus: status, ...app?.app } });
  await screen.findByText("Anthropic");
  return view;
}

function card(id: string): HTMLElement {
  const form = document.querySelector(`[data-provider-form="${id}"]`);
  if (!form) throw new Error(`no card for ${id}`);
  return form.closest(".provider-card") as HTMLElement;
}

describe("provider status block", () => {
  it("shows the label with model, the detail and a green Ready badge", async () => {
    await renderPane();
    expect(document.getElementById("provider-status-name")).toHaveTextContent("Anthropic · claude-live-1");
    expect(document.getElementById("provider-status-detail")).toHaveTextContent("Ready via server environment");
    expect(document.getElementById("provider-status-badge")).toHaveClass("badge", "green");
    expect(document.getElementById("provider-status-badge")).toHaveTextContent("Ready");
  });

  it("keeps the static copy until the status arrives", async () => {
    await renderPane({ app: { providerStatus: null } });
    expect(document.getElementById("provider-status-name")).toHaveTextContent("Checking provider…");
    expect(document.getElementById("provider-status-badge")).toHaveTextContent("Checking");
  });
});

describe("credential cards", () => {
  it("prefills the active provider's model from the server environment", async () => {
    await renderPane();
    const active = card("anthropic");
    expect(active).toHaveClass("provider-card", "active");
    expect(within(active).getByLabelText("Model")).toHaveValue("claude-live-1");
    expect(within(active).getByText("From server .env")).toBeInTheDocument();
    expect(within(active).getByText(/from the server's environment, not saved here/)).toBeInTheDocument();
    // A configured provider uses its saved model; an inactive one the hint.
    expect(within(card("openai")).getByLabelText("Model")).toHaveValue("gpt-saved");
    expect(within(card("openai")).getByText("Saved")).toBeInTheDocument();
  });

  it("falls back to the model hint while the live status is unknown", async () => {
    await renderPane({ app: { providerStatus: null } });
    expect(within(card("anthropic")).getByLabelText("Model")).toHaveValue("claude-default");
    expect(within(card("anthropic")).getByText("Not set")).toBeInTheDocument();
  });

  it("leaves Azure model empty and asks for endpoint and API version", async () => {
    await renderPane();
    const form = card("azure_openai");
    expect(within(form).getByLabelText("Model (deployment name)")).toHaveValue("");
    expect(within(form).getByLabelText("Endpoint")).toBeRequired();
    expect(within(form).getByLabelText("API version")).toBeInTheDocument();
    expect(within(card("anthropic")).queryByLabelText("Base URL")).toBeNull();
  });

  it("flips the key field between password and text with the eye button", async () => {
    await renderPane();
    const active = card("anthropic");
    const key = within(active).getByLabelText("API key");
    expect(key).toHaveAttribute("type", "password");
    expect(key.parentElement).toHaveClass("field-with-action");
    await userEvent.click(within(active).getByRole("button", { name: "Show API key" }));
    expect(key).toHaveAttribute("type", "text");
    await userEvent.click(within(active).getByRole("button", { name: "Hide API key" }));
    expect(key).toHaveAttribute("type", "password");
  });

  it("Test key validates the form first and does not call the API when invalid", async () => {
    await renderPane();
    const active = card("anthropic");
    const validity = vi.spyOn(HTMLFormElement.prototype, "reportValidity");
    await userEvent.click(within(active).getByRole("button", { name: "Test key" }));
    expect(validity).toHaveBeenCalled();
    expect(net.callsTo("POST", "/api/v1/provider/credentials/anthropic/test")).toHaveLength(0);
    expect(within(active).getByLabelText("API key")).toBeRequired();
    expect(within(active).getByLabelText("API key")).toHaveAttribute("minlength", "8");
  });

  it("Test key posts the card values and shows the result", async () => {
    net.set("POST /api/v1/provider/credentials/anthropic/test", { ok: true, detail: "Key works." });
    await renderPane();
    const active = card("anthropic");
    await userEvent.type(within(active).getByLabelText("API key"), "sk-ant-long-enough-key");
    await userEvent.click(within(active).getByRole("button", { name: "Test key" }));
    await waitFor(() => expect(active.querySelector("[data-provider-test-result]")).toHaveTextContent("Key works."));
    expect(active.querySelector("[data-provider-test-result]")).toHaveClass("test-result", "ok");
    expect(net.callsTo("POST", "/api/v1/provider/credentials/anthropic/test")[0].body).toEqual({
      api_key: "sk-ant-long-enough-key",
      model: "claude-live-1",
    });
  });

  it("shows a failed test in the fail style", async () => {
    net.set("POST /api/v1/provider/credentials/anthropic/test", { ok: false, detail: "The API key was rejected" });
    await renderPane();
    const active = card("anthropic");
    await userEvent.type(within(active).getByLabelText("API key"), "sk-ant-long-enough-key");
    await userEvent.click(within(active).getByRole("button", { name: "Test key" }));
    await waitFor(() => expect(active.querySelector("[data-provider-test-result]")).toHaveClass("fail"));
  });

  it("Azure test and save send base_url and api_version (null when empty)", async () => {
    net.set("POST /api/v1/provider/credentials/azure_openai/test", { ok: true, detail: "ok" });
    await renderPane();
    const form = card("azure_openai");
    await userEvent.type(within(form).getByLabelText("Model (deployment name)"), "my-deploy");
    await userEvent.type(within(form).getByLabelText("Endpoint"), "https://res.openai.azure.com");
    await userEvent.type(within(form).getByLabelText("API key"), "azure-key-long-enough");
    await userEvent.click(within(form).getByRole("button", { name: "Test key" }));
    await waitFor(() => expect(net.callsTo("POST", "/api/v1/provider/credentials/azure_openai/test")).toHaveLength(1));
    expect(net.callsTo("POST", "/api/v1/provider/credentials/azure_openai/test")[0].body).toEqual({
      api_key: "azure-key-long-enough",
      model: "my-deploy",
      base_url: "https://res.openai.azure.com",
      api_version: null,
    });
  });

  it("Save PUTs the key, refreshes the status and reloads the cards", async () => {
    net.set("PUT /api/v1/provider/credentials/anthropic", { ...anthropic, configured: true });
    const view = await renderPane();
    const active = card("anthropic");
    await userEvent.type(within(active).getByLabelText("API key"), "sk-ant-long-enough-key");
    await userEvent.click(within(active).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(view.app.setStatus).toHaveBeenCalledWith("Anthropic key saved securely."));
    expect(net.callsTo("PUT", "/api/v1/provider/credentials/anthropic")[0].body).toEqual({ api_key: "sk-ant-long-enough-key", model: "claude-live-1" });
    expect(view.app.refreshStatus).toHaveBeenCalled();
    await waitFor(() => expect(net.callsTo("GET", "/api/v1/provider/credentials")).toHaveLength(2));
    // The reloaded card starts with an empty key again.
    await waitFor(() => expect(within(card("anthropic")).getByLabelText("API key")).toHaveValue(""));
  });

  it("reports a failed save and re-enables the button", async () => {
    net.set("PUT /api/v1/provider/credentials/anthropic", () => ({ __reply: { status: 422, json: { detail: "Bad key" } } }));
    const view = await renderPane();
    const active = card("anthropic");
    await userEvent.type(within(active).getByLabelText("API key"), "sk-ant-long-enough-key");
    await userEvent.click(within(active).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(view.app.setStatus).toHaveBeenCalledWith("Bad key", true));
    expect(within(active).getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("disables Save when the server cannot manage credentials", async () => {
    net.set("GET /api/v1/provider/credentials", [{ ...anthropic, can_manage: false }]);
    await renderPane();
    expect(within(card("anthropic")).getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByText(/Configure a provider credential encryption key/)).toBeInTheDocument();
  });

  it("Remove saved key asks first, then DELETEs and reloads", async () => {
    net.set("DELETE /api/v1/provider/credentials/openai", null);
    const view = await renderPane();
    await userEvent.click(within(card("openai")).getByRole("button", { name: "Remove saved key" }));
    expect(view.app.askDialog).toHaveBeenCalledWith(expect.objectContaining({ title: "Remove saved OpenAI key?", danger: true, confirmLabel: "Remove key" }));
    await waitFor(() => expect(net.callsTo("DELETE", "/api/v1/provider/credentials/openai")).toHaveLength(1));
    expect(view.app.setStatus).toHaveBeenCalledWith("Saved OpenAI key removed.");
    expect(view.app.refreshStatus).toHaveBeenCalled();
  });

  it("does nothing when the removal is not confirmed", async () => {
    const view = await renderPane({ app: { askDialog: vi.fn(async () => null) } });
    await userEvent.click(within(card("openai")).getByRole("button", { name: "Remove saved key" }));
    expect(net.callsTo("DELETE", "/api/v1/provider/credentials/openai")).toHaveLength(0);
    expect(view.app.setStatus).not.toHaveBeenCalled();
  });

  it("shows an error line when the list cannot be loaded", async () => {
    net.set("GET /api/v1/provider/credentials", () => ({ __reply: { status: 500, json: { detail: "boom" } } }));
    renderWithApp(<ProviderPane active />);
    expect(await screen.findByText(/Could not load providers: boom/)).toBeInTheDocument();
  });
});
