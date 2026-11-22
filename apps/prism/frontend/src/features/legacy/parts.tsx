import { useState, type ReactNode } from "react";
import type { LegacyAction } from "./types";
import { useLegacyData } from "./LegacyDataProvider";

/** `.list` container: the empty text replaces the items (old `renderList`). */
export function ListBox<T>({
  id,
  items,
  empty,
  render,
}: {
  id: string;
  items: readonly T[];
  empty: string;
  render: (item: T, index: number) => ReactNode;
}) {
  if (!items.length) {
    return (
      <div id={id} className="list empty-state">
        {empty}
      </div>
    );
  }
  return (
    <div id={id} className="list">
      {items.map(render)}
    </div>
  );
}

export function Item({ title, meta, actions }: { title: ReactNode; meta: ReactNode; actions?: ReactNode }) {
  return (
    <div className="list-item">
      <strong>{title}</strong>
      <div className="meta">{meta}</div>
      {actions ? <div className="item-actions">{actions}</div> : null}
    </div>
  );
}

const HELP: Record<LegacyAction, string> = {
  "daily-reminder": "Send this person a simple Teams reminder for today's update.",
  "resolve-blocker": "Mark this blocker as fixed.",
  "blocker-follow-up": "Send the dependency owner a Teams follow-up.",
  "mark-missed": "Mark this commitment as missed.",
  "revise-commitment": "Keep the old promise and enter a new deadline.",
  "acknowledge-escalation": "Mark that you have seen this escalation.",
  "resolve-escalation": "Close this escalation as resolved.",
};

/** `data-action` button; disabled while its action runs (old `handleAction`). */
export function ActionButton({ label, action, id }: { label: string; action: LegacyAction; id: string }) {
  const { runAction } = useLegacyData();
  const [busy, setBusy] = useState(false);
  return (
    <button
      className="mini-button"
      type="button"
      data-action={action}
      data-id={id}
      data-tooltip={HELP[action]}
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await runAction(action, id);
        } finally {
          setBusy(false);
        }
      }}
    >
      {label}
    </button>
  );
}

export function Badge({ id, children }: { id: string; children: ReactNode }) {
  return (
    <span id={id} className="badge">
      {children}
    </span>
  );
}
