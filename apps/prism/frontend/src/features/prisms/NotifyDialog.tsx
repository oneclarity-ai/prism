import { useImperativeHandle, useRef, useState, type Ref } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { usePrismsInternal } from "./internal";
import { notificationPermission } from "./PrismsProvider";
import type { DialogHandle } from "./TriggerDialog";

interface NotificationSetting {
  enabled: boolean;
  min_urgency: string;
}

function permissionCopy(): string {
  const copy: Record<string, string> = {
    unsupported: "This browser does not support notifications, so updates appear only inside Prism.",
    denied: "Notifications are blocked for this site in your browser settings. Updates still appear inside Prism.",
    granted: "Browser permission is allowed.",
    default: "Your browser will ask for permission when you save with alerts on.",
  };
  return copy[notificationPermission()] ?? "";
}

/** `#prism-notify-dialog`: browser alerts for one Prism. Permission is requested only from the Save click, once. */
export function NotifyDialog({ ref }: { ref?: Ref<DialogHandle> }) {
  const { setStatus } = useApp();
  const { selectedId } = usePrismsInternal();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [enabled, setEnabled] = useState(false);
  const [urgency, setUrgency] = useState("low");
  const [permission, setPermission] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [prismId, setPrismId] = useState<string | null>(null);

  useImperativeHandle(ref, () => ({
    async open() {
      if (!selectedId) return;
      setError("");
      try {
        const setting = await agentApi<NotificationSetting>(`/api/v2/prisms/${selectedId}/notification-settings`);
        setEnabled(setting.enabled);
        setUrgency(setting.min_urgency);
        setPermission(permissionCopy());
        setPrismId(selectedId);
        dialogRef.current?.showModal();
      } catch (failure) {
        setStatus(errorMessage(failure), true);
      }
    },
  }));

  const save = async () => {
    setBusy(true);
    try {
      if (enabled && notificationPermission() === "default") await Notification.requestPermission();
      await agentApi(`/api/v2/prisms/${prismId}/notification-settings`, { method: "PUT", ...jsonBody({ enabled, min_urgency: urgency }) });
      dialogRef.current?.close();
      setStatus(
        enabled && notificationPermission() !== "granted"
          ? "Alerts saved. Browser permission is off, so updates appear only inside Prism."
          : enabled
            ? "Browser alerts are on while a Prism page is open."
            : "Browser alerts are off.",
      );
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog id="prism-notify-dialog" className="picker prism-editor-dialog" ref={dialogRef} data-prism-id={prismId ?? undefined}>
      <div className="prism-editor-form">
        <div>
          <h2>Notifications</h2>
          <p className="panel-note">
            Browser alerts appear only while a Prism page is open on this computer. Every update is saved in this Prism’s conversation either way, and alerts
            never include Teams message text.
          </p>
        </div>
        <label className="switch-row" htmlFor="prism-notify-enabled">
          <span>
            <strong>Browser alerts</strong>
            <small>Alert me about new updates from this Prism.</small>
          </span>
          <input id="prism-notify-enabled" className="toggle" type="checkbox" role="switch" checked={enabled} onChange={(event) => setEnabled(event.currentTarget.checked)} />
        </label>
        <label htmlFor="prism-notify-urgency">
          Alert me when urgency is at least
          <select id="prism-notify-urgency" value={urgency} onChange={(event) => setUrgency(event.currentTarget.value)}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </label>
        <p id="prism-notify-permission" className="panel-note" role="status">
          {permission}
        </p>
        <p id="prism-notify-error" className="form-error" role="alert" hidden={!error}>
          {error}
        </p>
        <div className="dialog-actions">
          <button id="prism-notify-cancel" className="button secondary" type="button" onClick={() => dialogRef.current?.close()}>
            Cancel
          </button>
          <button id="prism-notify-save" className="button" type="button" disabled={busy} onClick={() => void save()}>
            Save
          </button>
        </div>
      </div>
    </dialog>
  );
}
