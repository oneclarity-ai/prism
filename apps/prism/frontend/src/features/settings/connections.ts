import type { MicrosoftStatus, ProviderStatus } from "@/lib/app-context";

export interface ConnectionRow {
  detail: string;
  badge: string;
  /** `green` / `orange` / `""` (appended to `badge`). */
  tone: "green" | "orange" | "";
}

export interface ConnectionRows {
  microsoft: ConnectionRow;
  provider: ConnectionRow;
  engine: ConnectionRow;
}

function row(ready: boolean | null, detail: string): ConnectionRow {
  return { detail, badge: ready === null ? "Unknown" : ready ? "Connected" : "Needs attention", tone: ready ? "green" : ready === false ? "orange" : "" };
}

/**
 * Settings > Connections (old preferences.js `renderStatus`). Rows whose status has not arrived keep the
 * static "Checking ..." copy.
 */
export function connectionRows(microsoft: MicrosoftStatus | null, provider: ProviderStatus | null, computers: boolean | null): ConnectionRows {
  return {
    microsoft: microsoft
      ? row(
          Boolean(microsoft.is_connected),
          microsoft.is_connected
            ? `Signed in as ${microsoft.connection?.user_principal_name || "your Microsoft account"}.`
            : "Connect your account so Prism can read Teams chats and send replies you approve.",
        )
      : { detail: "Checking connection.", badge: "Checking", tone: "" },
    provider: provider
      ? row(Boolean(provider.ready), provider.detail || "AI provider status unavailable.")
      : { detail: "Checking provider.", badge: "Checking", tone: "" },
    engine:
      computers === null
        ? { detail: "Checking availability.", badge: "Checking", tone: "" }
        : row(
            Boolean(computers),
            computers ? "Prisms can use computers for approved browser tasks." : "Computer features are not enabled on this server.",
          ),
  };
}
