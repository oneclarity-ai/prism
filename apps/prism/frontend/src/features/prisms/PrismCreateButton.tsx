import { useApp } from "@/lib/app-context";
import { usePrismsInternal } from "./internal";

export function PrismCreateButton() {
  const { modes } = useApp();
  const { commands } = usePrismsInternal();
  return (
    <button
      id="prism-create-button"
      className="icon-button"
      type="button"
      aria-label="Create Prism"
      data-tooltip="Create Prism"
      data-v22-only=""
      hidden={modes.v22 !== true}
      onClick={() => commands.current.openCreate?.()}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 5v14M5 12h14" />
      </svg>
    </button>
  );
}
