import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { humanize } from "@/features/legacy/format";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import type { Schema } from "@/types";
import { providerHeading } from "./providerLabels";

type Credential = Schema<"ProviderCredentialSummary">;

interface TestState {
  text: string;
  tone: "" | "ok" | "fail";
}

function EyeIcon({ off }: { off: boolean }) {
  return off ? (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 3l18 18" />
      <path d="M10.73 5.08A10.94 10.94 0 0 1 12 5c7 0 11 7 11 7a13.16 13.16 0 0 1-3.11 4.1M6.1 6.1C3.4 7.9 1 12 1 12a13.16 13.16 0 0 0 5.17 5.39A10.94 10.94 0 0 0 12 19c1 0 1.95-.14 2.84-.4" />
      <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

const badgeTone = (ready: boolean, state: string) => (ready ? "green" : state === "disabled" ? "blue" : "orange");

/**
 * One BYOK card. Model / endpoint / API version start from the saved or live values until the user types
 * (the status may arrive after the list), the key always starts empty. The parent remounts the card after every
 * (re)load, like the old innerHTML re-render.
 */
function ProviderCredentialCard({
  credential,
  liveModel,
  labelFor,
  onSaved,
}: {
  credential: Credential;
  liveModel: string | null;
  labelFor: (id: string) => string;
  onSaved: () => Promise<void>;
}) {
  const { setStatus, askDialog, refreshStatus } = useApp();
  const id = credential.provider;
  const formRef = useRef<HTMLFormElement>(null);
  const [model, setModel] = useState<string | null>(null);
  const [baseUrl, setBaseUrl] = useState(credential.base_url || "");
  const [apiVersion, setApiVersion] = useState(credential.api_version || "");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [test, setTest] = useState<TestState>({ text: "", tone: "" });

  const defaultModel = credential.model || liveModel || (credential.base_url_required ? "" : credential.default_model_hint);
  const modelValue = model ?? defaultModel;

  const stateBadge = credential.configured ? (
    <span className="badge green">Saved</span>
  ) : liveModel ? (
    <span className="badge blue">From server .env</span>
  ) : (
    <span className="badge">Not set</span>
  );
  const subtitle = credential.configured
    ? credential.model
    : liveModel
      ? `${liveModel} (from the server's environment, not saved here)`
      : "No key saved";
  const helpText = credential.configured
    ? `${credential.masked_key} is stored encrypted on this Prism server. Enter a new key to replace it.`
    : credential.can_manage
      ? "Stored encrypted on this Prism server. The key is never shown again."
      : "Configure a provider credential encryption key on the server before saving a key.";

  const payload = () => {
    const body: Record<string, string | null> = { api_key: apiKey, model: modelValue };
    if (credential.needs_base_url) body.base_url = baseUrl || null;
    if (credential.needs_api_version) body.api_version = apiVersion || null;
    return body;
  };

  const testKey = async () => {
    if (!formRef.current?.reportValidity()) return;
    setTesting(true);
    setTest({ text: "Testing…", tone: "" });
    try {
      const result = await agentApi<Schema<"ProviderCredentialTestResult">>(`/api/v1/provider/credentials/${id}/test`, {
        method: "POST",
        ...jsonBody(payload()),
      });
      setTest({ text: result.detail, tone: result.ok ? "ok" : "fail" });
    } catch (error) {
      setTest({ text: errorMessage(error), tone: "fail" });
    } finally {
      setTesting(false);
    }
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await agentApi(`/api/v1/provider/credentials/${id}`, { method: "PUT", ...jsonBody(payload()) });
      setStatus(`${labelFor(id)} key saved securely.`);
      await refreshStatus();
      await onSaved();
    } catch (error) {
      setStatus(errorMessage(error), true);
      setSaving(false);
    }
  };

  const remove = async () => {
    const confirmed = await askDialog({
      title: `Remove saved ${labelFor(id)} key?`,
      message: "Prism will fall back to the provider credential configured on this server, if any.",
      confirmLabel: "Remove key",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await agentApi(`/api/v1/provider/credentials/${id}`, { method: "DELETE" });
      setStatus(`Saved ${labelFor(id)} key removed.`);
      await refreshStatus();
      await onSaved();
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };

  const azure = id === "azure_openai";
  return (
    <div className={`provider-card${credential.is_active_provider ? " active" : ""}`}>
      <div className="setting-row">
        <div>
          <strong>{credential.label}</strong>
          <p className="panel-note">{subtitle}</p>
        </div>
        <span className="setting-actions">
          {credential.is_active_provider ? <span className="badge blue">Active</span> : null}
          {stateBadge}
        </span>
      </div>
      <form className="provider-key-form" data-provider-form={id} ref={formRef} onSubmit={save}>
        <p className="panel-note">{helpText}</p>
        <div className="field">
          <label htmlFor={`provider-model-${id}`}>Model{azure ? " (deployment name)" : ""}</label>
          <input
            id={`provider-model-${id}`}
            name="model"
            value={modelValue}
            onChange={(event) => setModel(event.currentTarget.value)}
            placeholder={credential.default_model_hint}
            autoComplete="off"
            required
          />
        </div>
        {credential.needs_base_url ? (
          <div className="field">
            <label htmlFor={`provider-base-url-${id}`}>{azure ? "Endpoint" : "Base URL"}</label>
            <input
              id={`provider-base-url-${id}`}
              name="base_url"
              type="url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.currentTarget.value)}
              placeholder={azure ? "https://<resource>.openai.azure.com" : "https://api.example.com/v1"}
              autoComplete="off"
              required={credential.base_url_required}
            />
          </div>
        ) : null}
        {credential.needs_api_version ? (
          <div className="field">
            <label htmlFor={`provider-api-version-${id}`}>API version</label>
            <input
              id={`provider-api-version-${id}`}
              name="api_version"
              value={apiVersion}
              onChange={(event) => setApiVersion(event.currentTarget.value)}
              placeholder="2024-10-21"
              autoComplete="off"
            />
          </div>
        ) : null}
        <div className="field">
          <label htmlFor={`provider-key-${id}`}>API key</label>
          <div className="field-with-action">
            <input
              id={`provider-key-${id}`}
              name="api_key"
              type={showKey ? "text" : "password"}
              autoComplete="new-password"
              minLength={8}
              placeholder="Paste a new API key"
              value={apiKey}
              onChange={(event) => setApiKey(event.currentTarget.value)}
              required
            />
            <button
              type="button"
              className="icon-button small"
              data-provider-toggle-key={id}
              aria-label={showKey ? "Hide API key" : "Show API key"}
              onClick={() => setShowKey((value) => !value)}
            >
              <EyeIcon off={showKey} />
            </button>
          </div>
        </div>
        <div className="provider-key-actions">
          <button className="button secondary" type="button" data-provider-test={id} disabled={testing} onClick={testKey}>
            Test key
          </button>
          <span className={`test-result${test.tone ? ` ${test.tone}` : ""}`} data-provider-test-result={id}>
            {test.text}
          </span>
          <button className="button" type="submit" disabled={!credential.can_manage || saving}>
            Save
          </button>
          {credential.configured ? (
            <button className="button secondary" type="button" data-provider-remove={id} onClick={remove}>
              Remove saved key
            </button>
          ) : null}
        </div>
      </form>
    </div>
  );
}

/**
 * Settings > AI provider. The list covers every provider Prism can store a BYOK key for; only the one the
 * server's LLM_PROVIDER selects is used, other saved keys wait for a switch.
 */
export function ProviderPane({ active }: { active: boolean }) {
  const app = useApp();
  const { providerStatus: status } = app;
  const [credentials, setCredentials] = useState<Credential[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const load = useCallback(async () => {
    try {
      setCredentials(await agentApi<Credential[]>("/api/v1/provider/credentials"));
      setFailure(null);
      setVersion((value) => value + 1);
    } catch (error) {
      setFailure(errorMessage(error));
    }
  }, []);

  // Old: loaded with the dashboard, and again whenever the section is opened.
  useEffect(() => {
    void load();
  }, [load, app.refreshKey]);
  const mounted = useRef(false);
  useEffect(() => {
    if (mounted.current && active) void load();
    mounted.current = true;
  }, [load, active]);

  const labelFor = useCallback((id: string) => credentials?.find((credential) => credential.provider === id)?.label || humanize(id), [credentials]);

  return (
    <>
      <h2 className="settings-title">AI provider</h2>
      <div className="setting-row">
        <div>
          <strong id="provider-status-name">{providerHeading(status)}</strong>
          <p id="provider-status-detail" className="panel-note" aria-live="polite">
            {status ? status.detail : "Loading safe configuration status."}
          </p>
        </div>
        <span id="provider-status-badge" className={status ? `badge ${badgeTone(status.ready, status.state)}` : "badge"}>
          {status ? (status.ready ? "Ready" : humanize(status.state)) : "Checking"}
        </span>
      </div>
      <p className="settings-intro">
        Prism runs whichever provider is selected on the server. Save a key below for that provider to use it; keys saved for other providers stay
        encrypted and ready for when you switch.
      </p>
      <div id="provider-credential-list" className="provider-credential-list">
        {failure !== null ? (
          <p className="panel-note">Could not load providers: {failure}</p>
        ) : credentials === null ? (
          <p className="panel-note">Loading providers…</p>
        ) : (
          credentials.map((credential) => (
            <ProviderCredentialCard
              key={`${credential.provider}-${version}`}
              credential={credential}
              liveModel={credential.is_active_provider && !credential.configured ? (status?.model ?? null) : null}
              labelFor={labelFor}
              onSaved={load}
            />
          ))
        )}
      </div>
    </>
  );
}
