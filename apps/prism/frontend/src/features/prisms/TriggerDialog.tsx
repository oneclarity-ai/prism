import { useImperativeHandle, useRef, useState, type Ref } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { usePrismsInternal } from "./internal";
import type { TriggerPolicy } from "./types";

export interface DialogHandle {
  open: () => void | Promise<void>;
}

interface Form {
  mode: string;
  enabled: boolean;
  timezone: string;
  time: string;
  missed: string;
  interval: string;
  coalesce: string;
}

const DEFAULTS: Form = { mode: "manual", enabled: true, timezone: "Asia/Kolkata", time: "09:00", missed: "run_once", interval: "300", coalesce: "180" };

/** `#prism-trigger-dialog`: when the selected Prism checks Teams for new activity. */
export function TriggerDialog({ ref }: { ref?: Ref<DialogHandle> }) {
  const { setStatus } = useApp();
  const { monitoring, selectedRef, prismsRef } = usePrismsInternal();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [form, setForm] = useState<Form>(DEFAULTS);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((current) => ({ ...current, [key]: value }));

  useImperativeHandle(ref, () => ({
    async open() {
      const known = monitoring.live.current.triggerPolicy;
      if (!known || known === "error") await monitoring.loadRunStatus();
      const policy = monitoring.live.current.triggerPolicy;
      if (!policy || typeof policy !== "object") {
        setStatus("Monitoring schedule is unavailable. Try again.", true);
        return;
      }
      setForm({
        mode: policy.mode,
        enabled: policy.enabled,
        timezone: policy.timezone,
        time: policy.daily_time,
        missed: policy.missed_run_policy,
        interval: String(policy.continuous_interval_seconds),
        coalesce: String(policy.event_coalesce_seconds),
      });
      setError("");
      dialogRef.current?.showModal();
    },
  }));

  const close = () => dialogRef.current?.close();

  const save = async () => {
    const policy = monitoring.live.current.triggerPolicy;
    const prismId = selectedRef.current;
    if (!prismId || !prismsRef.current.some((item) => item.id === prismId) || !policy || typeof policy !== "object") return;
    setBusy(true);
    setError("");
    try {
      const saved = await agentApi<TriggerPolicy>(`/api/v2/prisms/${prismId}/trigger-policy`, {
        method: "PUT",
        ...jsonBody({
          expected_revision: policy.revision,
          mode: form.mode,
          enabled: form.enabled,
          timezone: form.timezone,
          daily_time: form.time,
          missed_run_policy: form.missed,
          continuous_interval_seconds: Number(form.interval),
          event_coalesce_seconds: Number(form.coalesce),
        }),
      });
      monitoring.setTriggerPolicy(saved);
      close();
      setStatus("Monitoring schedule saved. It only reads Teams; it cannot send messages.");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog id="prism-trigger-dialog" className="picker prism-editor-dialog" ref={dialogRef}>
      <div className="prism-editor-form">
        <div>
          <h2>Monitoring schedule</h2>
          <p className="panel-note">Runs only read Teams under this Prism’s scope. They never send a message or perform an action.</p>
        </div>
        <label htmlFor="prism-trigger-mode">
          Run mode
          <select id="prism-trigger-mode" value={form.mode} onChange={(event) => set("mode", event.currentTarget.value)}>
            <option value="manual">Manual only</option>
            <option value="scheduled">Daily schedule</option>
            <option value="continuous">Continuous local checks</option>
            <option value="event_driven">Coalesced event checks</option>
          </select>
        </label>
        <label className="switch-row" htmlFor="prism-trigger-enabled">
          <span>
            <strong>Enable this monitoring mode</strong>
            <small>Turn it off to pause checks without losing the settings.</small>
          </span>
          <input id="prism-trigger-enabled" className="toggle" type="checkbox" role="switch" checked={form.enabled} onChange={(event) => set("enabled", event.currentTarget.checked)} />
        </label>
        <div id="prism-trigger-schedule-fields" className="prism-trigger-fields" hidden={form.mode !== "scheduled"}>
          <label htmlFor="prism-trigger-timezone">
            Timezone
            <input id="prism-trigger-timezone" type="text" maxLength={80} placeholder="Asia/Kolkata" value={form.timezone} onChange={(event) => set("timezone", event.currentTarget.value)} />
          </label>
          <label htmlFor="prism-trigger-time">
            Daily time
            <input id="prism-trigger-time" type="time" value={form.time} onChange={(event) => set("time", event.currentTarget.value)} />
          </label>
          <label htmlFor="prism-trigger-missed">
            If Prism was offline
            <select id="prism-trigger-missed" value={form.missed} onChange={(event) => set("missed", event.currentTarget.value)}>
              <option value="run_once">Run once on return</option>
              <option value="skip">Skip the missed run</option>
            </select>
          </label>
        </div>
        <div id="prism-trigger-continuous-fields" className="prism-trigger-fields" hidden={form.mode !== "continuous"}>
          <label htmlFor="prism-trigger-interval">
            Check every (seconds)
            <input id="prism-trigger-interval" type="number" min={60} max={86400} value={form.interval} onChange={(event) => set("interval", event.currentTarget.value)} />
          </label>
        </div>
        <div id="prism-trigger-event-fields" className="prism-trigger-fields" hidden={form.mode !== "event_driven"}>
          <label htmlFor="prism-trigger-coalesce">
            Wait for quiet period (seconds)
            <input id="prism-trigger-coalesce" type="number" min={30} max={86400} value={form.coalesce} onChange={(event) => set("coalesce", event.currentTarget.value)} />
          </label>
        </div>
        <p id="prism-trigger-error" className="form-error" role="alert" hidden={!error}>
          {error}
        </p>
        <div className="dialog-actions">
          <button id="prism-trigger-cancel" className="button secondary" type="button" onClick={close}>
            Cancel
          </button>
          <button id="prism-trigger-save" className="button" type="button" disabled={busy} onClick={() => void save()}>
            Save monitoring schedule
          </button>
        </div>
      </div>
    </dialog>
  );
}
