import { useImperativeHandle, useRef, useState, type ReactNode, type Ref } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { usePrismsInternal } from "./internal";
import type { DialogHandle } from "./TriggerDialog";

interface Health {
  monitoring: { last_checked_at: string | null; last_successful_run_at: string | null };
  metrics: {
    runs: number;
    failed: number;
    events_created: number;
    observations_created: number;
    notifications_delivered: number;
    drafts_prepared: number;
    skipped: number;
    graph_reads: number;
    alerts_deduplicated: number;
    false_positive_feedback: number;
    model_calls: number;
    avg_duration_ms: number | null;
  };
  microsoft: { connected: boolean };
  provider: { configured: boolean; signal_model_enabled: boolean };
  scheduler: { server_enabled: boolean; mode: string; mode_enabled: boolean };
  budget: Record<BudgetKey, number> & { runs_today: number };
  retention_days: number;
  review_required: boolean;
  diagnosis: string[];
}
interface Signal {
  signal_type: string;
  label: string;
  protected?: boolean;
  muted?: boolean;
  suppressed_count?: number;
  feedback: Record<string, number>;
  suggestion?: string | null;
}
type BudgetKey = "max_runs_per_day" | "max_model_calls_per_day" | "max_consecutive_failures";
const BUDGET_FIELDS: ReadonlyArray<readonly [BudgetKey, string]> = [
  ["max_runs_per_day", "Runs per day"],
  ["max_model_calls_per_day", "Model calls per day"],
  ["max_consecutive_failures", "Pause after failures in a row"],
];

type Body = { kind: "loading" } | { kind: "empty" } | { kind: "ready"; health: Health; signals: Signal[] };

const when = (value: string | null): string => (value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "never");

const Stat = ({ value, label }: { value: ReactNode; label: string }) => (
  <div className="health-stat">
    <strong>{String(value)}</strong>
    <span>{label}</span>
  </div>
);
const Kv = ({ label, value, tone }: { label: string; value: string; tone?: string }) => (
  <div className="health-kv">
    <span>{label}</span>
    <strong className={tone ? `tone-${tone}` : undefined}>{value}</strong>
  </div>
);
const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <section>
    <h3>{title}</h3>
    {children}
  </section>
);

/** `#prism-health-dialog`: why the selected Prism is quiet, delayed or failing (counts only). */
export function HealthDialog({ ref }: { ref?: Ref<DialogHandle> }) {
  const { setStatus } = useApp();
  const { selectedRef } = usePrismsInternal();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [body, setBody] = useState<Body>({ kind: "loading" });
  const [error, setError] = useState("");
  const [limits, setLimits] = useState<Record<BudgetKey, string>>({ max_runs_per_day: "", max_model_calls_per_day: "", max_consecutive_failures: "" });
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => {
    const prismId = selectedRef.current;
    if (!prismId) return;
    setError("");
    try {
      const [health, tuning] = await Promise.all([
        agentApi<Health>(`/api/v2/prisms/${prismId}/health`),
        agentApi<{ signals: Signal[] }>(`/api/v2/prisms/${prismId}/tuning`),
      ]);
      setLimits({
        max_runs_per_day: String(health.budget.max_runs_per_day),
        max_model_calls_per_day: String(health.budget.max_model_calls_per_day),
        max_consecutive_failures: String(health.budget.max_consecutive_failures),
      });
      setBody({ kind: "ready", health, signals: tuning.signals });
    } catch (failure) {
      setBody({ kind: "empty" });
      setError(errorMessage(failure));
    }
  };

  useImperativeHandle(ref, () => ({
    open() {
      setBody({ kind: "loading" });
      dialogRef.current?.showModal();
      return load();
    },
  }));

  const acknowledge = async () => {
    setBusy("review");
    try {
      await agentApi(`/api/v2/prisms/${selectedRef.current}/migration-review/acknowledge`, { method: "POST" });
      setStatus("Thanks. Automatic monitoring is now allowed for this Prism.");
      await load();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  };

  const toggleSignal = async (signal: Signal, muted: boolean) => {
    setBusy(signal.signal_type);
    try {
      await agentApi(`/api/v2/prisms/${selectedRef.current}/tuning/signals/${signal.signal_type}`, { method: "PUT", ...jsonBody({ muted }) });
      await load();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  };

  const saveLimits = async () => {
    setBusy("limits");
    setError("");
    try {
      await agentApi(`/api/v2/prisms/${selectedRef.current}/budget`, {
        method: "PUT",
        ...jsonBody(Object.fromEntries(BUDGET_FIELDS.map(([key]) => [key, Number(limits[key])]))),
      });
      setStatus("Limits saved for this Prism.");
      await load();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  };

  let content: ReactNode = null;
  if (body.kind === "loading") content = "Loading…";
  else if (body.kind === "ready") {
    const { health, signals } = body;
    const m = health.metrics;
    const mon = health.monitoring;
    const healthy = health.microsoft.connected && !health.review_required && !m.failed;
    content = (
      <>
        <div className={`health-hero ${healthy ? "ok" : "warn"}`}>
          <span className="health-dot" />
          <div>
            <strong>{health.diagnosis[0] || (healthy ? "Everything looks fine." : "Needs attention")}</strong>
            {health.diagnosis.slice(1).map((line, index) => (
              <p key={index}>{line}</p>
            ))}
            {health.review_required ? (
              <button className="button" type="button" disabled={busy === "review"} onClick={() => void acknowledge()}>
                I've reviewed this Prism
              </button>
            ) : null}
          </div>
        </div>
        <Section title="Last 24 hours">
          <div className="health-grid">
            <Stat value={m.runs} label="Runs" />
            <Stat value={m.failed} label="Failed" />
            <Stat value={m.events_created} label="New messages" />
            <Stat value={m.observations_created} label="Updates" />
            <Stat value={m.notifications_delivered} label="Alerts shown" />
            <Stat value={m.drafts_prepared} label="Drafts" />
          </div>
          <details className="health-more">
            <summary>More numbers</summary>
            <div className="health-grid">
              <Stat value={m.skipped} label="Skipped by limits" />
              <Stat value={m.graph_reads} label="Teams chats read" />
              <Stat value={m.alerts_deduplicated} label="Duplicates avoided" />
              <Stat value={m.false_positive_feedback} label="Marked not useful" />
              <Stat value={m.model_calls} label="Model calls" />
              <Stat value={m.avg_duration_ms === null ? "—" : `${m.avg_duration_ms} ms`} label="Avg run time" />
            </div>
          </details>
        </Section>
        <Section title="Status">
          <div className="health-card">
            <Kv label="Microsoft" value={health.microsoft.connected ? "Connected" : "Not connected"} tone={health.microsoft.connected ? "ok" : "warn"} />
            <Kv
              label="Model provider"
              value={health.provider.configured ? (health.provider.signal_model_enabled ? "Configured" : "Rules only") : "Not configured"}
              tone={health.provider.configured ? "ok" : "warn"}
            />
            <Kv
              label="Scheduler"
              value={`${health.scheduler.server_enabled ? "On" : "Off"} · ${health.scheduler.mode.replace("_", " ")}${health.scheduler.mode_enabled ? "" : " (disabled)"}`}
              tone={health.scheduler.server_enabled && health.scheduler.mode_enabled ? "ok" : "warn"}
            />
            <Kv label="Last checked Teams" value={when(mon.last_checked_at)} />
            <Kv label="Last successful run" value={when(mon.last_successful_run_at)} />
            <Kv label="Runs today" value={`${health.budget.runs_today} of ${health.budget.max_runs_per_day}`} />
          </div>
          <p className="health-note">{`Raw Teams activity is kept for ${health.retention_days} days. Updates and approvals are kept.`}</p>
        </Section>
        <Section title="Signals · switch off to mute">
          <div className="health-card">
            {signals.map((signal) => {
              const notes: string[] = [];
              if (signal.protected) notes.push("Safety signal: always on.");
              if (signal.muted) {
                const hid = signal.suppressed_count ? `; hid ${signal.suppressed_count} update${signal.suppressed_count === 1 ? "" : "s"}` : "";
                notes.push(`Muted by you${hid}.`);
              }
              const feedback = Object.entries(signal.feedback).map(([kind, count]) => `${count} ${kind.replaceAll("_", " ")}`);
              if (feedback.length) notes.push(`Feedback: ${feedback.join(", ")}.`);
              if (signal.suggestion) notes.push(signal.suggestion);
              return (
                <div className="health-signal" key={signal.signal_type}>
                  <div className="grow">
                    <strong>{signal.label}</strong>
                    {notes.length ? <small>{notes.join(" ")}</small> : null}
                  </div>
                  <input
                    className="toggle"
                    type="checkbox"
                    role="switch"
                    aria-label={`${signal.label} alerts`}
                    checked={!signal.muted}
                    disabled={Boolean(signal.protected) || busy === signal.signal_type}
                    onChange={(event) => void toggleSignal(signal, !event.currentTarget.checked)}
                  />
                </div>
              );
            })}
          </div>
        </Section>
        <Section title="Limits">
          <div className="health-card">
            <div className="health-budget">
              {BUDGET_FIELDS.map(([key, label]) => (
                <label key={key}>
                  {label}
                  <input
                    type="number"
                    min={key === "max_model_calls_per_day" ? "0" : "1"}
                    data-key={key}
                    value={limits[key]}
                    onChange={(event) => setLimits({ ...limits, [key]: event.currentTarget.value })}
                  />
                </label>
              ))}
            </div>
            <button className="button" type="button" disabled={busy === "limits"} onClick={() => void saveLimits()}>
              Save limits
            </button>
          </div>
        </Section>
      </>
    );
  }

  return (
    <dialog id="prism-health-dialog" className="picker prism-editor-dialog prism-health-dialog" ref={dialogRef}>
      <div className="prism-editor-form">
        <div className="dialog-heading">
          <div>
            <h2>Status &amp; tuning</h2>
            <p className="panel-note">Why this Prism is quiet, delayed, or failing. Counts only; no message text or secrets are shown.</p>
          </div>
          <button id="prism-health-close" className="icon-button" type="button" aria-label="Close" onClick={() => dialogRef.current?.close()}>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </div>
        <div id="prism-health-body" className="health-body" aria-live="polite">
          {content}
        </div>
        <p id="prism-health-error" className="form-error" role="alert" hidden={!error}>
          {error}
        </p>
      </div>
    </dialog>
  );
}
