import type { ProviderStatus } from "@/lib/app-context";
import { humanize } from "@/features/legacy/format";

export function providerLabel(provider: string): string {
  return provider === "azure_openai" ? "Azure OpenAI" : provider === "openai" ? "OpenAI" : provider === "codex_local" ? "Local Codex" : humanize(provider);
}

/** `#provider-status-name`: "Label · model", or the static copy until the status arrived. */
export function providerHeading(status: ProviderStatus | null): string {
  if (!status) return "Checking provider…";
  const label = providerLabel(status.provider);
  return status.model ? `${label} · ${status.model}` : label;
}
