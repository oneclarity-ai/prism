import { useEffect, type FormEvent, type MouseEventHandler, type ReactNode } from "react";
import { getState, loadRun, useStoreVersion } from "./store";
import type { ChatMessageLike, QaRun } from "./types";

/** Small building blocks shared by the chat cards and the computer panel (plain markup, same classes as the old DOM). */

export function QaChip({ tone = "gray", children }: { tone?: string; children?: ReactNode }) {
  return <span className={`qa-chip tag-${tone}`}>{children}</span>;
}

interface BtnProps {
  label: string;
  className?: string;
  onClick?: MouseEventHandler<HTMLButtonElement>;
  disabled?: boolean;
  title?: string;
  type?: "button" | "submit";
}

export function Btn({ label, className, onClick, disabled, title, type = "button" }: BtnProps) {
  return (
    <button className={className} type={type} onClick={onClick} disabled={disabled} title={title}>
      {label}
    </button>
  );
}

export function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <p className="qa-fact">
      <span className="qa-fact-label">{label}</span>
      <span>{value}</span>
    </p>
  );
}

export function EditField({ label, check = false, children }: { label: string; check?: boolean; children: ReactNode }) {
  return (
    <label className={check ? "qa-edit-field qa-edit-check" : "qa-edit-field"}>
      <span>{label}</span>
      {children}
    </label>
  );
}

export const onSubmit = (handler: () => void) => (event: FormEvent) => {
  event.preventDefault();
  handler();
};

export function metaString(message: ChatMessageLike, key: string): string | undefined {
  const value = message.message_metadata?.[key];
  return typeof value === "string" ? value : undefined;
}

/** The run a chat card refers to; asks the store to load it when this tab has not seen it yet. */
export function useRun(runId: string | undefined): QaRun | undefined {
  const version = useStoreVersion();
  const run = runId ? getState().runs.get(runId) : undefined;
  useEffect(() => {
    if (!run && runId) void loadRun(runId);
  }, [run, runId, version]);
  return run;
}
