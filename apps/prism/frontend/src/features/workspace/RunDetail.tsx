import { useEffect, useRef, useState } from "react";
import { useApp } from "@/lib/app-context";
import { agentApi, errorMessage, operatorHeaders } from "@/lib/api";
import { time as date, words as label } from "@/lib/format";

const ACTIVE = new Set(["queued", "running", "waiting_children", "waiting_approval"]);
const POLL_MS = 3000;

interface RunRecord {
  id?: string;
  task_title?: string | null;
  agent_name?: string | null;
  status?: string | null;
  model?: string | null;
  cost_usd?: unknown;
  total_cost_usd?: unknown;
  input_tokens?: unknown;
  output_tokens?: unknown;
  total_tokens?: unknown;
  created_at?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  active_tool?: string | null;
  summary?: string | null;
  error?: string | null;
}
interface TitledItem {
  title?: string;
  status?: string;
  severity?: string;
}
export interface RunDetailData {
  run?: RunRecord;
  subagents?: Array<{ label?: string; status?: string; activity?: string }>;
  test_cases?: TitledItem[];
  bugs?: TitledItem[];
  events?: Array<{ created_at?: string; tool?: string; status?: string; type?: string }>;
  artifacts?: Array<{ id: string; kind?: string; created_at?: string }>;
}

type View = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ok"; data: RunDetailData };

const dollars = (value: unknown) => `$${Number(value || 0).toFixed(4)}`;

function badgeTone(value: string): string {
  if (["succeeded", "pass", "active", "approved"].includes(value)) return "green";
  if (["failed", "error", "rejected", "critical"].includes(value)) return "red";
  if (["running", "queued"].includes(value)) return "blue";
  return "gray";
}

function Field({ title, value }: { title: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <p className="operations-field">
      <strong>{`${title}: `}</strong>
      {String(value)}
    </p>
  );
}

function Section<T>({ title, items, make }: { title: string; items: readonly T[] | undefined; make: (item: T) => string }) {
  if (!items?.length) return null;
  return (
    <section className="operations-detail-section">
      <h3 className="operations-section-title">{`${title} · ${items.length}`}</h3>
      {items.map((item, index) => (
        <p className="operations-event" key={index}>
          {make(item)}
        </p>
      ))}
    </section>
  );
}

async function downloadArtifact(id: string): Promise<void> {
  const response = await fetch(`/api/v2/operations/artifacts/${id}/file`, { headers: operatorHeaders() });
  if (!response.ok) throw new Error("File unavailable");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `prism-artifact-${id.slice(0, 8)}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export interface RunDetailProps {
  runId: string;
  /** False while the operations tab is not showing: polling stops. */
  active: boolean;
  onBack: () => void;
}

/** Run detail; refreshes every 3 seconds while the run is still going. */
export function RunDetail({ runId, active, onBack }: RunDetailProps) {
  const { setStatus } = useApp();
  const [view, setView] = useState<View>({ kind: "loading" });
  const statusRef = useRef(setStatus);
  statusRef.current = setStatus;

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const open = async (refresh: boolean) => {
      if (!refresh) setView({ kind: "loading" });
      try {
        const data = await agentApi<RunDetailData>(`/api/v2/operations/runs/${runId}`);
        if (cancelled) return;
        setView({ kind: "ok", data });
        if (ACTIVE.has(String(data.run?.status))) timer = setTimeout(() => void open(true), POLL_MS);
      } catch (error) {
        if (!cancelled) setView({ kind: "error", message: `Run detail could not load: ${errorMessage(error)}` });
      }
    };
    void open(false);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [runId, active]);

  if (view.kind === "loading") return <p className="panel-note">Loading run detail…</p>;
  if (view.kind === "error") return <p className="operations-empty">{view.message}</p>;

  const { data } = view;
  const run = data.run || {};
  const status = String(run.status || "unknown");
  return (
    <>
      <button type="button" className="mini-button" onClick={onBack}>
        ← Back to runs
      </button>
      <article className="operations-card">
        <h3>{run.task_title || "Run"}</h3>
        <p className="panel-note">{`${run.agent_name || "Prism"} · ${date(run.created_at)}`}</p>
        <span className={`qa-chip tag-${badgeTone(status)}`}>{label(status)}</span>
        <Field title="Model" value={run.model} />
        <Field title="Cost" value={dollars(run.total_cost_usd ?? run.cost_usd)} />
        <Field title="Tokens" value={run.total_tokens ?? Number(run.input_tokens || 0) + Number(run.output_tokens || 0)} />
        <Field title="Started" value={date(run.started_at)} />
        <Field title="Ended" value={run.ended_at && date(run.ended_at)} />
        <Field title="Current tool" value={run.active_tool} />
        <Field title="Summary" value={run.summary} />
        {run.error ? <Field title="Error" value={run.error} /> : null}
      </article>
      <Section title="Parallel Prisms" items={data.subagents} make={(item) => `${item.label || "Prism"}: ${label(item.status)}${item.activity ? ` · ${item.activity}` : ""}`} />
      <Section title="Test cases" items={data.test_cases} make={(item) => `${item.title}: ${label(item.status)}`} />
      <Section title="Bugs" items={data.bugs} make={(item) => `${item.title}: ${label(item.severity)} · ${label(item.status)}`} />
      <Section title="Timeline" items={data.events} make={(item) => `${date(item.created_at)} · ${item.tool || item.status || label(item.type)}`} />
      {data.artifacts?.length ? (
        <section className="operations-detail-section">
          <h3 className="operations-section-title">{`Files · ${data.artifacts.length}`}</h3>
          {data.artifacts.map((item) => (
            <button
              type="button"
              className="mini-button"
              key={item.id}
              onClick={async () => {
                try {
                  await downloadArtifact(item.id);
                } catch (error) {
                  statusRef.current(errorMessage(error), true);
                }
              }}
            >
              {`${label(item.kind)} · ${date(item.created_at)}`}
            </button>
          ))}
        </section>
      ) : null}
    </>
  );
}
