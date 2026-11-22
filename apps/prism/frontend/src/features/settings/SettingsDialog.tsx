import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { initials } from "@/features/legacy/format";
import { useConnectMicrosoft } from "@/features/legacy/microsoft";
import { useModalDialog } from "@/features/legacy/useModalDialog";
import { PeoplePane } from "@/features/people/PeoplePane";
import { ArchivedPrismsPane } from "@/features/prisms/ArchivedPrismsPane";
import { SkillLibrary } from "@/features/prisms/SkillLibrary";
import { CurrencyToggle } from "@/features/spending/CurrencyToggle";
import { useApp, type SettingsSection } from "@/lib/app-context";
import { setPref, setUiSize, usePref, useUiSize, type UiSize } from "@/lib/prefs";
import { STORAGE_KEYS, readStorage, writeStorage } from "@/lib/storage";
import { connectionRows, type ConnectionRow } from "./connections";
import { ProviderPane } from "./ProviderPane";

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {children}
    </svg>
  );
}

type NavEntry =
  | { label: string }
  | { key: SettingsSection; title: string; icon: ReactNode; v22Only?: boolean; dot?: boolean };

const NAV: NavEntry[] = [
  { label: "Account" },
  {
    key: "account",
    title: "Account",
    icon: (
      <Svg>
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21a8 8 0 0 1 16 0" />
      </Svg>
    ),
  },
  {
    key: "preferences",
    title: "Preferences",
    icon: (
      <Svg>
        <path d="M4 7h8M16 7h4M4 17h4M12 17h8" />
        <circle cx="14" cy="7" r="2" />
        <circle cx="10" cy="17" r="2" />
      </Svg>
    ),
  },
  {
    key: "notifications",
    title: "Notifications",
    icon: (
      <Svg>
        <path d="M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7M10 20a2 2 0 0 0 4 0" />
      </Svg>
    ),
  },
  { label: "Workspace" },
  {
    key: "skills",
    title: "Skills",
    v22Only: true,
    icon: (
      <Svg>
        <path d="M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-3H4zM20 4h-4a3 3 0 0 0-3 3M13 21a4 4 0 0 1 4-3h3V4" />
      </Svg>
    ),
  },
  {
    key: "general",
    title: "General",
    icon: (
      <Svg>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
      </Svg>
    ),
  },
  {
    key: "teams",
    title: "People",
    icon: (
      <Svg>
        <circle cx="9" cy="8" r="3.2" />
        <path d="M3 19c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5M16 5.2a3.2 3.2 0 0 1 0 5.6M18 14c1.8.6 3 2.2 3 5" />
      </Svg>
    ),
  },
  {
    key: "archived",
    title: "Archived Prisms",
    v22Only: true,
    icon: (
      <Svg>
        <path d="M4 5h16v4H4zM6 9v10h12V9M10 13h4" />
      </Svg>
    ),
  },
  {
    key: "connections",
    title: "Connections",
    icon: (
      <Svg>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </Svg>
    ),
  },
  {
    key: "provider",
    title: "AI provider",
    dot: true,
    icon: (
      <Svg>
        <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" />
      </Svg>
    ),
  },
  {
    key: "access",
    title: "Access",
    icon: (
      <Svg>
        <rect x="5" y="11" width="14" height="9" rx="2" />
        <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      </Svg>
    ),
  },
  { label: "Advanced" },
  {
    key: "developer",
    title: "Developer",
    icon: (
      <Svg>
        <path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14" />
      </Svg>
    ),
  },
];

const TABS = NAV.filter((entry): entry is Extract<NavEntry, { key: SettingsSection }> => "key" in entry);
const KEYS = new Set<string>(TABS.map((tab) => tab.key));
const NAV_KEYS = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"];

function ConnectionBadge({ id, row }: { id: string; row: ConnectionRow }) {
  return (
    <span id={id} className={`badge${row.tone ? ` ${row.tone}` : ""}`}>
      {row.badge}
    </span>
  );
}

function ConnectMicrosoftButton({ id }: { id?: string }) {
  const { microsoft } = useApp();
  const connect = useConnectMicrosoft();
  const connected = Boolean(microsoft?.is_connected);
  return (
    <button
      id={id}
      // Until the status arrives the static markup (a secondary, enabled "Connect" button) shows.
      className={`button${!microsoft || connected ? " secondary" : ""}`}
      type="button"
      data-connect-microsoft
      disabled={microsoft ? !microsoft.is_auth_configured : false}
      onClick={() => void connect()}
    >
      {connected ? "Switch Microsoft account" : "Connect Microsoft account"}
    </button>
  );
}

function AccountPane() {
  const { microsoft } = useApp();
  const connected = Boolean(microsoft?.is_connected && microsoft.connection);
  const name = connected ? String(microsoft?.connection?.display_name ?? "") : "Microsoft account";
  return (
    <>
      <h2 className="settings-title">Account</h2>
      <div className="setting-row">
        <div className="setting-identity">
          <span id="settings-account-avatar" className="account-avatar lg" aria-hidden="true">
            {connected ? initials(name) : "M"}
          </span>
          <div>
            <strong id="settings-account-name">{name}</strong>
            <p id="account-menu-email" className="panel-note">
              {connected ? microsoft?.connection?.user_principal_name : "No Microsoft account connected"}
            </p>
          </div>
        </div>
        <ConnectMicrosoftButton id="connect-microsoft-button" />
      </div>
      <p className="settings-foot">
        Prism reads your Teams chats and sends approved replies from this account. Choose who Prism manages, and import your directory, on the People page.
      </p>
    </>
  );
}

function PreferencesPane() {
  const size = useUiSize();
  const contrast = usePref("contrast") || "system";
  const enterNewline = usePref("enter-newline") === "1";
  return (
    <>
      <h2 className="settings-title">Preferences</h2>
      <p className="settings-intro">Choose how you want Prism to look and behave.</p>
      <h3 className="settings-group">Appearance</h3>
      <div className="setting-row">
        <div>
          <strong>Display size</strong>
          <p className="panel-note">Make text and controls smaller or larger. Touch screens always use full-size controls.</p>
        </div>
        <select id="size-select" aria-label="Display size" value={size} onChange={(event) => setUiSize(event.currentTarget.value as UiSize)}>
          <option value="compact">Compact</option>
          <option value="default">Default</option>
          <option value="large">Large</option>
        </select>
      </div>
      <div className="setting-row">
        <div>
          <strong>
            High contrast <span className="tag">Beta</span>
          </strong>
          <p className="panel-note">Increase contrast for improved visibility.</p>
        </div>
        <select
          id="contrast-select"
          aria-label="High contrast"
          value={contrast}
          onChange={(event) => setPref("contrast", event.currentTarget.value === "system" ? null : event.currentTarget.value)}
        >
          <option value="system">Use system setting</option>
          <option value="off">Off</option>
          <option value="on">On</option>
        </select>
      </div>
      <h3 className="settings-group">Input options</h3>
      <div className="setting-row">
        <div>
          <strong>Use Enter to add a new line</strong>
          <p className="panel-note">
            Applies to Prism chat. Press <kbd>Cmd</kbd>/<kbd>Ctrl</kbd> + <kbd>Enter</kbd> to send.
          </p>
        </div>
        <input
          id="pref-enter-newline"
          className="toggle"
          type="checkbox"
          role="switch"
          aria-label="Use Enter to add a new line"
          checked={enterNewline}
          onChange={(event) => setPref("enter-newline", event.currentTarget.checked ? "1" : null)}
        />
      </div>
      <h3 className="settings-group">Display</h3>
      <div className="setting-row">
        <div>
          <strong>Currency</strong>
          <p className="panel-note">Used for spending and cost totals.</p>
        </div>
        <CurrencyToggle />
      </div>
      <div className="setting-row">
        <div>
          <strong>Time zone</strong>
          <p className="panel-note">Dates and times follow this browser.</p>
        </div>
        <span id="pref-timezone" className="setting-value">
          {Intl.DateTimeFormat().resolvedOptions().timeZone || "Local time"}
        </span>
      </div>
    </>
  );
}

function NotificationsPane() {
  const approvals = usePref("notify-approvals") !== "0";
  const supported = typeof Notification !== "undefined";
  const [permission, setPermission] = useState<NotificationPermission | null>(supported ? Notification.permission : null);
  const badge =
    permission === null
      ? { text: "Not supported", tone: "" }
      : permission === "granted"
        ? { text: "On", tone: " green" }
        : permission === "denied"
          ? { text: "Blocked", tone: " orange" }
          : { text: "Off", tone: "" };
  return (
    <>
      <h2 className="settings-title">Notifications</h2>
      <p className="settings-intro">Control what asks for your attention on this browser.</p>
      <h3 className="settings-group">Approvals</h3>
      <div className="setting-row">
        <div>
          <strong>Show waiting-approval counts</strong>
          <p className="panel-note">Badges in the sidebar and Home when drafts or actions wait for you.</p>
        </div>
        <input
          id="pref-notify-approvals"
          className="toggle"
          type="checkbox"
          role="switch"
          aria-label="Show waiting-approval counts"
          checked={approvals}
          onChange={(event) => setPref("notify-approvals", event.currentTarget.checked ? null : "0")}
        />
      </div>
      <h3 className="settings-group">Browser alerts</h3>
      <div className="setting-row">
        <div>
          <strong>Desktop notifications</strong>
          <p className="panel-note">Prism can alert you when a Prism needs you. Permission is managed by your browser.</p>
        </div>
        <span className="setting-actions">
          <span id="pref-notify-status" className={`badge${badge.tone}`}>
            {badge.text}
          </span>
          <button
            id="pref-notify-enable"
            className="button secondary"
            type="button"
            hidden={permission !== "default"}
            onClick={() => void Notification.requestPermission().then(setPermission)}
          >
            Allow notifications
          </button>
        </span>
      </div>
    </>
  );
}

function ConnectionsPane({ computers, onLink }: { computers: boolean | null; onLink: (name: string) => void }) {
  const { microsoft, providerStatus } = useApp();
  const rows = connectionRows(microsoft, providerStatus, computers);
  return (
    <>
      <h2 className="settings-title">Connections</h2>
      <p className="settings-intro">Services Prism uses on your behalf.</p>
      <div className="settings-card conn-list">
        <div className="setting-row">
          <div>
            <strong>Microsoft Teams</strong>
            <p id="conn-microsoft-detail" className="panel-note">
              {rows.microsoft.detail}
            </p>
          </div>
          <span className="setting-actions">
            <ConnectionBadge id="conn-microsoft-badge" row={rows.microsoft} />
            <ConnectMicrosoftButton />
          </span>
        </div>
        <div className="setting-row">
          <div>
            <strong>AI provider</strong>
            <p id="conn-provider-detail" className="panel-note">
              {rows.provider.detail}
            </p>
          </div>
          <span className="setting-actions">
            <ConnectionBadge id="conn-provider-badge" row={rows.provider} />
            <button className="button secondary" type="button" data-settings-link="provider" onClick={() => onLink("provider")}>
              Manage
            </button>
          </span>
        </div>
        <div className="setting-row">
          <div>
            <strong>Computers</strong>
            <p id="conn-engine-detail" className="panel-note">
              {rows.engine.detail}
            </p>
          </div>
          <span className="setting-actions">
            <ConnectionBadge id="conn-engine-badge" row={rows.engine} />
          </span>
        </div>
      </div>
    </>
  );
}

function AccessPane() {
  const { askDialog, setStatus, refresh } = useApp();
  const setOperatorToken = async () => {
    const current = readStorage(STORAGE_KEYS.operatorToken);
    const value = await askDialog({
      title: "Operator access key",
      message: current
        ? "Replace the operator access key. Leave blank to remove it from this browser."
        : "Enter the operator access key from your local .env file.",
      confirmLabel: "Save",
      field: { label: "Access key", type: "password" },
    });
    if (value === null) return;
    const text = value === true ? "" : value.trim();
    if (text) {
      writeStorage(STORAGE_KEYS.operatorToken, text);
      setStatus("Operator access key saved in this browser.");
    } else {
      writeStorage(STORAGE_KEYS.operatorToken, null);
      setStatus("Operator access key removed from this browser.");
    }
    refresh();
  };
  return (
    <>
      <h2 className="settings-title">Access</h2>
      <div className="setting-row">
        <div>
          <strong>Operator access key</strong>
          <p className="panel-note">Required when this dashboard is exposed through ngrok. Stored only in this browser.</p>
        </div>
        <button id="operator-token-button" className="button secondary" type="button" onClick={() => void setOperatorToken()}>
          Set access key
        </button>
      </div>
    </>
  );
}

const GENERAL_LINKS: ReadonlyArray<readonly [string, string, string]> = [
  ["provider", "AI provider", "Current model and OpenAI key"],
  ["teams", "People and Microsoft Teams", "Connected account and team directory"],
  ["spending", "Spending", "Prism, swarm, and provider costs"],
  ["connections", "Connections", "Microsoft Teams, AI provider, computers"],
  ["access", "Access", "Operator key for this browser"],
];

/** `<dialog id="settings-dialog">`: nav, search, and every section body. Open state lives in the shell. */
export function SettingsDialog() {
  const app = useApp();
  const { settings, modes } = app;
  const dialogRef = useRef<HTMLDialogElement>(null);
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());
  const panelRefs = useRef(new Map<string, HTMLElement>());
  const [query, setQuery] = useState("");
  const [searchHidden, setSearchHidden] = useState<ReadonlySet<string>>(new Set());

  useModalDialog(dialogRef, settings.isOpen, settings.close);

  const section: SettingsSection = KEYS.has(settings.section) ? settings.section : "account";
  const tabHidden = (tab: { v22Only?: boolean }) => Boolean(tab.v22Only) && modes.v22 !== true;
  const visibleTabs = () => TABS.filter((tab) => !tabHidden(tab) && !searchHidden.has(tab.key));

  const choose = (name: SettingsSection) => {
    writeStorage(STORAGE_KEYS.subtab("settings"), name);
    settings.setSection(name);
  };

  // The old openSettings() focused the active section tab.
  useEffect(() => {
    if (settings.isOpen) tabRefs.current.get(section)?.focus();
    // Only when the dialog opens, not on every section change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.isOpen]);

  const onNavKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const source = event.target;
    if (!(source instanceof HTMLButtonElement) || !source.hasAttribute("data-subtab-target") || !NAV_KEYS.includes(event.key)) return;
    const tabs = visibleTabs();
    const index = tabs.findIndex((tab) => tab.key === source.getAttribute("data-subtab-target"));
    if (index < 0) return;
    event.preventDefault();
    const previous = event.key === "ArrowLeft" || event.key === "ArrowUp";
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (previous ? -1 : 1) + tabs.length) % tabs.length;
    const target = tabs[next];
    tabRefs.current.get(target.key)?.focus();
    choose(target.key);
  };

  const onSearch = (value: string) => {
    setQuery(value);
    const text = value.trim().toLowerCase();
    const hidden = new Set<string>();
    for (const tab of TABS) {
      const content = panelRefs.current.get(tab.key)?.textContent || "";
      if (text && !`${tab.title} ${content}`.toLowerCase().includes(text)) hidden.add(tab.key);
    }
    setSearchHidden(hidden);
  };

  const onSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") return;
    const first = visibleTabs()[0];
    if (first) choose(first.key);
  };

  const link = (name: string) => {
    if (name === "spending") {
      settings.close();
      app.setActiveTab("spending");
      return;
    }
    if (KEYS.has(name)) choose(name as SettingsSection);
  };

  const onBackdrop = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === event.currentTarget) settings.close();
  };

  const panel = (name: SettingsSection, children: ReactNode) => (
    <section
      key={name}
      data-subtab-group="settings"
      data-subtab={name}
      hidden={section !== name}
      ref={(node) => {
        if (node) panelRefs.current.set(name, node);
        else panelRefs.current.delete(name);
      }}
    >
      {children}
    </section>
  );

  const labelHidden = (index: number): boolean => {
    let any = false;
    for (let next = index + 1; next < NAV.length && !("label" in NAV[next]); next += 1) {
      const entry = NAV[next];
      if ("key" in entry && !searchHidden.has(entry.key)) any = true;
    }
    return !any;
  };
  const shown = TABS.filter((tab) => !searchHidden.has(tab.key)).length;
  const provider = app.providerStatus;

  return (
    <dialog id="settings-dialog" className="settings-dialog" aria-labelledby="settings-dialog-title" ref={dialogRef} onClick={onBackdrop}>
      <h1 id="settings-dialog-title" className="sr-only">
        Settings
      </h1>
      <div className="settings-layout">
        <aside className="settings-side">
          <label className="settings-search">
            <Svg>
              <circle cx="11" cy="11" r="6" />
              <path d="m20 20-4-4" />
            </Svg>
            <span className="sr-only">Search settings</span>
            <input
              id="settings-search"
              type="search"
              placeholder="Search settings"
              autoComplete="off"
              value={query}
              onChange={(event) => onSearch(event.currentTarget.value)}
              onKeyDown={onSearchKeyDown}
            />
          </label>
          <nav className="settings-nav" role="tablist" aria-label="Settings sections" aria-orientation="vertical" data-subtabs="settings" onKeyDown={onNavKeyDown}>
            {NAV.map((entry, index) =>
              "label" in entry ? (
                <span key={`label-${entry.label}`} className={`settings-nav-label${labelHidden(index) ? " search-hidden" : ""}`}>
                  {entry.label}
                </span>
              ) : (
                <button
                  key={entry.key}
                  ref={(node) => {
                    if (node) tabRefs.current.set(entry.key, node);
                    else tabRefs.current.delete(entry.key);
                  }}
                  className={`nav-item${section === entry.key ? " active" : ""}${searchHidden.has(entry.key) ? " search-hidden" : ""}`}
                  type="button"
                  role="tab"
                  data-subtab-target={entry.key}
                  data-v22-only={entry.v22Only ? "" : undefined}
                  hidden={tabHidden(entry)}
                  aria-selected={section === entry.key}
                  tabIndex={section === entry.key ? 0 : -1}
                  onClick={() => choose(entry.key)}
                >
                  {entry.icon}
                  <span>{entry.title}</span>
                  {entry.dot ? (
                    <span id="provider-nav-dot" className="nav-dot warn" aria-label="Needs attention" hidden={!provider || provider.ready || provider.state === "unavailable"} />
                  ) : null}
                </button>
              ),
            )}
          </nav>
          <p id="settings-search-empty" className="panel-note" hidden={shown > 0}>
            No matching settings.
          </p>
        </aside>
        <div className="settings-body">
          {panel(
            "skills",
            <>
              <h2 className="settings-title">Skills</h2>
              <div id="settings-skills-library">{section === "skills" ? <SkillLibrary /> : null}</div>
            </>,
          )}
          {panel("account", <AccountPane />)}
          {panel("preferences", <PreferencesPane />)}
          {panel("notifications", <NotificationsPane />)}
          {panel(
            "general",
            <>
              <h2 className="settings-title">General</h2>
              <p className="settings-intro">Manage your private Prism workspace and connected services.</p>
              <div className="settings-card settings-links">
                {GENERAL_LINKS.map(([name, title, hint]) => (
                  <button key={name} type="button" data-settings-link={name} onClick={() => link(name)}>
                    <span>
                      <strong>{title}</strong>
                      <small>{hint}</small>
                    </span>
                    <span aria-hidden="true">›</span>
                  </button>
                ))}
              </div>
            </>,
          )}
          {panel(
            "teams",
            <PeoplePane />,
          )}
          {panel(
            "archived",
            <>
              <h2 className="settings-title">Archived Prisms</h2>
              {section === "archived" ? <ArchivedPrismsPane /> : null}
            </>,
          )}
          {panel("connections", <ConnectionsPane computers={modes.v24} onLink={link} />)}
          {panel("provider", <ProviderPane active={section === "provider"} />)}
          {panel("access", <AccessPane />)}
          {panel(
            "developer",
            <>
              <h2 className="settings-title">Developer</h2>
              <p className="settings-intro">Read-only tools for this Prism server.</p>
              <div className="settings-card conn-list">
                <div className="setting-row">
                  <div>
                    <strong>API reference</strong>
                    <p className="panel-note">Interactive documentation for every endpoint.</p>
                  </div>
                  <a className="button secondary" href="/docs" target="_blank" rel="noopener noreferrer">
                    Open docs
                  </a>
                </div>
                <div className="setting-row">
                  <div>
                    <strong>Health check</strong>
                    <p className="panel-note">Confirms the API is running.</p>
                  </div>
                  <a className="button secondary" href="/health" target="_blank" rel="noopener noreferrer">
                    Open /health
                  </a>
                </div>
                <div className="setting-row">
                  <div>
                    <strong>Operator access key</strong>
                    <p className="panel-note">Stored only in this browser. Manage it under Access.</p>
                  </div>
                  <button className="button secondary" type="button" data-settings-link="access" onClick={() => link("access")}>
                    Open Access
                  </button>
                </div>
              </div>
            </>,
          )}
        </div>
      </div>
      <button id="settings-close" className="icon-button settings-close" type="button" aria-label="Close settings" onClick={settings.close}>
        <Svg>
          <path d="M6 6l12 12M18 6 6 18" />
        </Svg>
      </button>
    </dialog>
  );
}
