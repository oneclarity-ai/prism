import { useState } from "react";
import { money, isWork, stateText, stripScheme } from "./helpers";
import { Btn, EditField, Fact, QaChip, metaString, onSubmit, useRun } from "./parts";
import { beginPlanEdit, cancelRun, finishPlanEdit, getState, startRun, watchRun } from "./store";
import type { ChatMessageLike, PlanEdits, QaRun } from "./types";

const SEP = "  ·  ";
const splitList = (value: string, separator: string | RegExp): string[] =>
  value
    .split(separator)
    .map((v) => v.trim())
    .filter(Boolean);

function WorkPlanBody({ run }: { run: QaRun }) {
  const plan = run.plan || {};
  const sites = [...(plan.sites || []).map(stripScheme), ...(plan.any_public_site ? ["any public website"] : [])];
  return (
    <div className="qa-card">
      <div className="qa-card-head">
        <strong>{plan.title || "Task"}</strong>
      </div>
      <Fact label="Steps" value="" />
      <ol className="qa-criteria">
        {(plan.steps || []).map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ol>
      <Fact label="Sites" value={sites.join(SEP) || "None"} />
      <Fact label="Uses" value={(plan.uses || []).join(SEP)} />
      {(plan.asks_first || []).length ? <Fact label="Asks you first" value={(plan.asks_first || []).join(", ")} /> : null}
      <Fact label="Limits" value={`up to ${plan.max_turns} steps · ${money(plan.budget_usd)} · ${plan.max_minutes || 30} min at most`} />
    </div>
  );
}

function PlanBody({ run }: { run: QaRun }) {
  if (isWork(run)) return <WorkPlanBody run={run} />;
  const plan = run.plan || {};
  const production = plan.environment === "production";
  const automatic = plan.discovery_mode === "automatic";
  return (
    <div className="qa-card">
      <div className="qa-card-head">
        <strong>{plan.host || "Website test"}</strong>
        <QaChip tone={production ? "orange" : "gray"}>
          {production ? (automatic ? "Live site · dummy data" : "Live site · read-only") : plan.environment || ""}
        </QaChip>
      </div>
      {automatic ? (
        <>
          <Fact label="Pages" value="Discover pages automatically" />
          <Fact label="Starting pages" value={(plan.pages || ["/"]).join(SEP)} />
          <Fact label="Scope" value="Internal pages on this site. I'll ask before opening subdomains or other sites." />
          <Fact label="Actions" value="Dummy data only. Login and important changes need your approval." />
        </>
      ) : (
        <Fact label="Pages" value={(plan.pages || ["/"]).join(SEP)} />
      )}
      <Fact label="Checks" value={(plan.features || []).join(", ") || "General smoke test"} />
      {(plan.acceptance_criteria || []).length ? (
        <>
          <Fact label="Make sure" value="" />
          <ul className="qa-criteria">
            {(plan.acceptance_criteria || []).map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}
      <Fact label="Limits" value={`up to ${plan.max_turns} steps · ${money(plan.budget_usd)} budget`} />
      <Fact label="Bug filing" value={plan.allow_bug_filing ? "On, I'll ask you first" : "Off"} />
    </div>
  );
}

function WorkEditForm({ run, onDone }: { run: QaRun; onDone: (edits: PlanEdits | null) => void }) {
  const plan = run.plan || {};
  const [steps, setSteps] = useState((plan.steps || []).join("\n"));
  const [sites, setSites] = useState((plan.sites || []).join(", "));
  const [anySite, setAnySite] = useState(Boolean(plan.any_public_site));
  const [turns, setTurns] = useState(String(plan.max_turns ?? ""));
  const [budget, setBudget] = useState(String(plan.budget_usd ?? ""));
  return (
    <form
      className="qa-edit"
      onSubmit={onSubmit(() =>
        onDone({
          steps: splitList(steps, "\n"),
          sites: splitList(sites, ","),
          any_public_site: anySite,
          max_turns: Number(turns) || undefined,
          budget_usd: Number(budget) || undefined,
        }),
      )}
    >
      <EditField label="Steps (one per line)">
        <textarea rows={5} value={steps} onChange={(event) => setSteps(event.target.value)} />
      </EditField>
      <EditField label="Sites I may use (comma separated)">
        <textarea rows={2} value={sites} onChange={(event) => setSites(event.target.value)} />
      </EditField>
      <EditField label="Any public website, if needed" check>
        <input type="checkbox" checked={anySite} onChange={(event) => setAnySite(event.target.checked)} />
      </EditField>
      <EditField label="Max steps">
        <input type="number" min="5" max="150" value={turns} onChange={(event) => setTurns(event.target.value)} />
      </EditField>
      <EditField label="Budget ($)">
        <input type="number" min="0.1" max="3" step="0.1" value={budget} onChange={(event) => setBudget(event.target.value)} />
      </EditField>
      <div className="qa-actions">
        <Btn label="Save changes" className="button" type="submit" />
        <Btn label="Cancel" className="button secondary" onClick={() => onDone(null)} />
      </div>
    </form>
  );
}

function QaEditForm({ run, onDone }: { run: QaRun; onDone: (edits: PlanEdits | null) => void }) {
  const plan = run.plan || {};
  const [pages, setPages] = useState((plan.pages || []).join(", "));
  const [criteria, setCriteria] = useState((plan.acceptance_criteria || []).join("\n"));
  const [turns, setTurns] = useState(String(plan.max_turns ?? ""));
  const [budget, setBudget] = useState(String(plan.budget_usd ?? ""));
  const [bugs, setBugs] = useState(Boolean(plan.allow_bug_filing));
  const mayFileBugs = Boolean(plan.may_file_bugs) && plan.environment !== "production";
  return (
    <form
      className="qa-edit"
      onSubmit={onSubmit(() =>
        onDone({
          pages: splitList(pages, ","),
          acceptance_criteria: splitList(criteria, "\n"),
          max_turns: Number(turns) || undefined,
          budget_usd: Number(budget) || undefined,
          ...(mayFileBugs ? { allow_bug_filing: bugs } : {}),
        }),
      )}
    >
      <EditField label={plan.discovery_mode === "automatic" ? "Starting pages (optional; I'll discover the rest)" : "Pages (comma separated)"}>
        <textarea rows={2} value={pages} onChange={(event) => setPages(event.target.value)} />
      </EditField>
      <EditField label="What to make sure of (one per line)">
        <textarea rows={3} value={criteria} onChange={(event) => setCriteria(event.target.value)} />
      </EditField>
      <EditField label="Max steps">
        <input type="number" min="5" max="150" value={turns} onChange={(event) => setTurns(event.target.value)} />
      </EditField>
      <EditField label="Budget ($)">
        <input type="number" min="0.1" max="3" step="0.1" value={budget} onChange={(event) => setBudget(event.target.value)} />
      </EditField>
      {mayFileBugs ? (
        <EditField label="Let me ask to file bugs" check>
          <input type="checkbox" checked={bugs} onChange={(event) => setBugs(event.target.checked)} />
        </EditField>
      ) : null}
      <div className="qa-actions">
        <Btn label="Save changes" className="button" type="submit" />
        <Btn label="Cancel" className="button secondary" onClick={() => onDone(null)} />
      </div>
    </form>
  );
}

function PlanActions({ run }: { run: QaRun }) {
  const [starting, setStarting] = useState(false);
  const start = async () => {
    setStarting(true);
    const started = await startRun(run, getState().edits.get(run.id) || {});
    if (!started) setStarting(false);
  };
  return (
    <div className="qa-actions">
      <Btn label={isWork(run) ? "Start" : "Start testing"} className="button" disabled={starting} onClick={() => void start()} />
      <Btn label="Edit" className="button secondary" onClick={() => beginPlanEdit(run.id)} />
      <Btn
        label="Not now"
        className="button ghost"
        onClick={() => void cancelRun(run).then(() => getState().host?.rerenderChat({ scroll: "keep" }))}
      />
    </div>
  );
}

function PlanStatus({ run }: { run: QaRun }) {
  const cases = run.cases;
  return (
    <div className="qa-status">
      <QaChip tone={run.state === "succeeded" ? "green" : run.active ? "blue" : "gray"}>{stateText(run)}</QaChip>
      {cases?.total ? (
        <span className="qa-muted">{`${cases.total} checks · ${cases.pass || 0} passed${cases.fail ? ` · ${cases.fail} failed` : ""}`}</span>
      ) : null}
      {run.active ? (
        <>
          <Btn label="Watch" className="mini-button" onClick={() => watchRun(run)} />
          <Btn label="Stop" className="mini-button" onClick={() => void cancelRun(run)} />
        </>
      ) : null}
    </div>
  );
}

/** `qa_plan` / `work_plan` message card: the plan, then Start / Edit / Not now, then the live status. */
export function PlanCard({ message }: { message: ChatMessageLike }) {
  const run = useRun(metaString(message, "qa_run_id"));
  if (!run) {
    return (
      <div className="qa-plan">
        <p className="qa-muted">Loading the plan…</p>
      </div>
    );
  }
  const editing = run.state === "planned" && getState().planEdits.has(run.id);
  return (
    <div className="qa-plan">
      <PlanBody run={run} />
      {run.state !== "planned" ? (
        <PlanStatus run={run} />
      ) : editing ? (
        isWork(run) ? (
          <WorkEditForm run={run} onDone={(edits) => finishPlanEdit(run, edits)} />
        ) : (
          <QaEditForm run={run} onDone={(edits) => finishPlanEdit(run, edits)} />
        )
      ) : (
        <PlanActions run={run} />
      )}
    </div>
  );
}
