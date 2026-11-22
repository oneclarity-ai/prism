import type { MicrosoftStatus, ProviderStatus, SettingsSection } from "@/lib/app-context";
import { connectionRows } from "./connections";
import { providerHeading } from "./providerLabels";

export interface SettingsIndexRow {
  label: string;
  /** Text of the row's `.panel-note`, used as extra search keywords. */
  note: string;
}

export interface SettingsIndexSection {
  section: SettingsSection;
  /** Nav button label. */
  title: string;
  /** Hidden until the Prism workspace (v2.2) is on. */
  v22Only: boolean;
  rows: SettingsIndexRow[];
}

export interface SettingsIndexInput {
  microsoft: MicrosoftStatus | null;
  provider: ProviderStatus | null;
  computers: boolean | null;
}

/**
 * What the old command palette scraped from the settings dialog: every section plus its
 * `.setting-row strong`, `.settings-group` and `.settings-links strong` labels (with the row note).
 */
export function settingsIndex({ microsoft, provider, computers }: SettingsIndexInput): SettingsIndexSection[] {
  const connected = Boolean(microsoft?.is_connected && microsoft.connection);
  const accountName = connected ? String(microsoft?.connection?.display_name ?? "") : "Microsoft account";
  const rows = connectionRows(microsoft, provider, computers);
  const noted = (label: string, note = ""): SettingsIndexRow => ({ label, note });
  return [
    {
      section: "account",
      title: "Account",
      v22Only: false,
      rows: [noted(accountName, connected ? String(microsoft?.connection?.user_principal_name ?? "") : "No Microsoft account connected")],
    },
    {
      section: "preferences",
      title: "Preferences",
      v22Only: false,
      rows: [
        noted("Appearance"),
        noted("Display size", "Make text and controls smaller or larger. Touch screens always use full-size controls."),
        noted("High contrast", "Increase contrast for improved visibility."),
        noted("Input options"),
        noted("Use Enter to add a new line", "Applies to Prism chat. Press Cmd/Ctrl + Enter to send."),
        noted("Display"),
        noted("Currency", "Used for spending and cost totals."),
        noted("Time zone", "Dates and times follow this browser."),
      ],
    },
    {
      section: "notifications",
      title: "Notifications",
      v22Only: false,
      rows: [
        noted("Approvals"),
        noted("Show waiting-approval counts", "Badges in the sidebar and Home when drafts or actions wait for you."),
        noted("Browser alerts"),
        noted("Desktop notifications", "Prism can alert you when a Prism needs you. Permission is managed by your browser."),
      ],
    },
    { section: "skills", title: "Skills", v22Only: true, rows: [] },
    {
      section: "general",
      title: "General",
      v22Only: false,
      rows: ["AI provider", "People and Microsoft Teams", "Spending", "Connections", "Access"].map((label) => noted(label)),
    },
    { section: "teams", title: "People", v22Only: false, rows: [] },
    { section: "archived", title: "Archived Prisms", v22Only: true, rows: [] },
    {
      section: "connections",
      title: "Connections",
      v22Only: false,
      rows: [noted("Microsoft Teams", rows.microsoft.detail), noted("AI provider", rows.provider.detail), noted("Computers", rows.engine.detail)],
    },
    {
      section: "provider",
      title: "AI provider",
      v22Only: false,
      rows: [noted(providerHeading(provider), provider ? provider.detail : "Loading safe configuration status.")],
    },
    {
      section: "access",
      title: "Access",
      v22Only: false,
      rows: [noted("Operator access key", "Required when this dashboard is exposed through ngrok. Stored only in this browser.")],
    },
    {
      section: "developer",
      title: "Developer",
      v22Only: false,
      rows: [
        noted("API reference", "Interactive documentation for every endpoint."),
        noted("Health check", "Confirms the API is running."),
        noted("Operator access key", "Stored only in this browser. Manage it under Access."),
      ],
    },
  ];
}
