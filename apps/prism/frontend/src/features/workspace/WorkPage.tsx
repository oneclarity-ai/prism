import { useEffect, useState } from "react";
import { agentApi, errorMessage } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { emit } from "@/lib/events";
import { usePrisms } from "@/features/prisms/PrismsContext";
import {
  loadApprovals,
  loadRuns,
  setPrismFilter,
  setWorkStatus,
  syncPrismList,
  useUnifiedWork,
  type WorkRun,
} from "./unified-work";

const timestamp = (value: string | null | undefined): string => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "" : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
};

function runTone(run: WorkRun): string {
  return run.active ? "blue" : run.state === "succeeded" ? "green" : run.state === "failed" || run.state === "error" ? "red" : "gray";
}

/** Open a Prism's chat (and optionally its computer run) from a unified-work card. */
export function useOpenWorkPrism(): (prismId: string, runId?: string | null) => void {
  const { setActiveTab } = useApp();
  const { prisms } = useUnifiedWork();
  return (prismId, runId = null) => {
    const prism = prisms.get(prismId);
    if (!prism) return;
    setActiveTab("agent");
    emit("open-agent", { prism });
    if (runId) emit("focus-computer-run", { runId });
  };
}

function RunCard({ run, onOpen }: { run: WorkRun; onOpen: (prismId: string, runId: string) => void }) {
  const [stopping, setStopping] = useState(false);
  const stop = async () => {
    setStopping(true);
    try {
      await agentApi(`/api/v2/qa/runs/${run.id}/cancel`, { method: "POST" });
      await loadRuns();
    } catch (error) {
      setWorkStatus(errorMessage(error), true);
      setStopping(false);
    }
  };
  return (
    <article className="unified-work-card">
      <div className="unified-work-head">
        <div className="unified-work-title">
          <h3>{run.title || "Prism task"}</h3>
          <span className={`qa-chip tag-${runTone(run)}`}>{String(run.state || "unknown").replaceAll("_", " ")}</span>
        </div>
        <span className="panel-note">{run.prism_name || "Prism"}</span>
      </div>
      <div className="unified-work-meta">
        <span>{run.kind === "qa" ? "Website test" : "Computer task"}</span>
        {run.created_at ? <span>{timestamp(run.created_at)}</span> : null}
        <span>{`$${Number(run.cost_usd || 0).toFixed(4)}`}</span>
      </div>
      {run.activity ? <p className="unified-work-activity">{run.activity}</p> : null}
      {run.error ? <p className="inline-error">{run.error}</p> : null}
      {run.report?.summary ? <p className="unified-work-summary">{run.report.summary}</p> : null}
      <div className="unified-work-actions">
        <button type="button" className="mini-button" onClick={() => onOpen(run.prism_id, run.id)}>
          Open this work
        </button>
        {run.active ? (
          <button type="button" className="mini-button primary" onClick={() => onOpen(run.prism_id, run.id)}>
            Watch computer
          </button>
        ) : null}
        {run.active ? (
          <button type="button" className="mini-button danger" disabled={stopping} onClick={() => void stop()}>
            Stop run
          </button>
        ) : null}
      </div>
    </article>
  );
}

/** Inner content of `data-tab="work"`. */
export function WorkPage() {
  const { activeTab } = useApp();
  const { prisms, loading } = usePrisms();
  const work = useUnifiedWork();
  const openPrism = useOpenWorkPrism();

  useEffect(() => {
    if (activeTab === "work") {
      void loadRuns();
      void loadApprovals();
    }
  }, [activeTab]);
  useEffect(() => {
    if (!loading) syncPrismList(prisms);
  }, [prisms, loading]);

  const list = work.runs;
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Work across your Prisms</h2>
          <p className="panel-note">Track computer tasks, live progress, results, and cost in one place.</p>
        </div>
        <div className="unified-work-toolbar">
          <label className="sr-only" htmlFor="work-prism-filter">
            Filter by Prism
          </label>
          <select id="work-prism-filter" value={work.prismFilter} onChange={(event) => setPrismFilter(event.currentTarget.value)}>
            <option value="">All Prisms</option>
            {[...work.prisms.values()].map((prism) => (
              <option key={prism.id} value={prism.id}>
                {prism.name}
              </option>
            ))}
          </select>
          <button id="work-refresh" className="mini-button" type="button" onClick={() => void loadRuns()}>
            Refresh
          </button>
        </div>
      </div>
      <div id="work-runtime-status" className={`callout${work.runtime.tone ? ` ${work.runtime.tone}` : ""}`} role="status" aria-live="polite">
        {work.runtime.text}
      </div>
      <p id="work-status" className={`panel-note${work.workStatus.error ? " error" : ""}`} role="status" aria-live="polite">
        {work.workStatus.text}
      </p>
      <div id="work-run-list" className="list empty-state">
        {list.kind === "initial" ? (
          "Loading Prism work…"
        ) : list.kind === "loading" ? (
          <p className="panel-note">Loading work…</p>
        ) : list.kind === "error" ? (
          <p className="inline-error">{list.message}</p>
        ) : !list.items.length ? (
          <p className="empty-state">No Prism work yet. Start a task from a Prism conversation and it will appear here.</p>
        ) : (
          list.items.map((run) => <RunCard key={run.id} run={run} onOpen={openPrism} />)
        )}
      </div>
    </>
  );
}
