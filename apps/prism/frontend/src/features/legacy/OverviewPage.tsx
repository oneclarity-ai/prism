import { useEffect, useState } from "react";
import { agentApi, errorMessage } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { emit } from "@/lib/events";
import type { Schema } from "@/types";
import { humanize } from "./format";
import { useLegacyData } from "./LegacyDataProvider";
import { ActionButton, Item, ListBox } from "./parts";
import { SetupCallout } from "./SetupCallout";
import type { AttentionEntry, Brief } from "./types";

function AgentFoundationPanel() {
  const { foundation } = useLegacyData();
  return (
    <section id="agent-foundation-panel" className="panel agent-activity" hidden={!foundation}>
      <div className="panel-heading">
        <div>
          <h2>Prism activity</h2>
          <p className="panel-note">Every review, approval, edit, and delivery is stored for audit and safe recovery.</p>
        </div>
      </div>
      <div className="stats compact-stats">
        <article className="stat-card">
          <span>Prism conversations</span>
          <strong id="foundation-thread-count">{foundation?.threads ?? 0}</strong>
        </article>
        <article className="stat-card">
          <span>Reviews</span>
          <strong id="foundation-job-count">{foundation?.jobs ?? 0}</strong>
        </article>
        <article className="stat-card warning">
          <span>Awaiting approval</span>
          <strong id="foundation-approval-count">{foundation?.pending_approvals ?? 0}</strong>
        </article>
        <article className="stat-card">
          <span>Messages sent</span>
          <strong id="foundation-execution-count">{foundation?.executions ?? 0}</strong>
        </article>
      </div>
    </section>
  );
}

interface AgentThread {
  id: string;
  source_label?: string | null;
  updated_at?: string | null;
}

const formatTime = (value?: string | null) => (value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");

function TodayAgentPanel() {
  const app = useApp();
  const { foundation } = useLegacyData();
  const [thread, setThread] = useState<AgentThread | null>(null);
  const v21 = app.modes.v21 === true;
  useEffect(() => {
    if (!v21) return;
    let current = true;
    agentApi<AgentThread>("/api/v2/agent/conversation")
      .then((value) => current && setThread(value))
      .catch(() => {});
    return () => {
      current = false;
    };
  }, [v21, foundation?.threads, app.refreshKey]);
  const pending = foundation?.pending_approvals ?? 0;
  // Before the first foundation answer the old static copy shows.
  const known = foundation !== null;
  const openPrism = () => {
    app.setActiveTab("agent");
    emit("new-chat");
  };
  return (
    <section className="panel today-agent" data-v21-only hidden={app.modes.v21 !== true}>
      <div className="panel-heading">
        <div>
          <h2>Prism</h2>
          <p className="panel-note">Continue one conversation with Prism. Teams chats are work sources, not separate Prism chats.</p>
        </div>
        <button className="button" type="button" data-agent-new onClick={openPrism}>
          Open Prism
        </button>
      </div>
      <div className="callout approval-banner">
        <span className="callout-icon" aria-hidden="true">
          📝
        </span>
        <div className="callout-body">
          <strong id="approval-banner-title">
            {known ? (pending ? `${pending} draft${pending === 1 ? "" : "s"} waiting for your approval` : "No drafts waiting") : "No drafts waiting"}
          </strong>
          <p id="approval-banner-text" className="panel-note">
            {known
              ? pending
                ? "Open Prism to review each draft, edit it if needed, then approve to send."
                : "Choose a Teams chat and ask Prism what needs your attention."
              : "Open Prism to ask a question or continue your work."}
          </p>
        </div>
        <button
          id="approval-banner-button"
          className={`button${known && pending ? "" : " secondary"}`}
          type="button"
          onClick={() => {
            if (foundation?.pending_approvals) app.setActiveTab("agent");
            else emit("new-chat");
          }}
        >
          {known ? (pending ? "Review drafts" : "Start a review") : "Open Prism"}
        </button>
      </div>
      <h3 className="subhead">Prism conversation</h3>
      {thread ? (
        <div id="today-thread-list" className="list">
          <button type="button" className="list-item thread-row" onClick={() => app.setActiveTab("agent")}>
            <strong>Continue with Prism</strong>
            <div className="meta">{`${thread.source_label ? `Source constraint: ${thread.source_label} · ` : ""}${formatTime(thread.updated_at)}`}</div>
          </button>
        </div>
      ) : (
        <div id="today-thread-list" className="list empty-state">
          No activity yet. Open Prism to begin.
        </div>
      )}
    </section>
  );
}

function AttentionList({ entries }: { entries: readonly AttentionEntry[] }) {
  if (!entries.length) {
    return (
      <div id="intelligence-attention-list" className="attention-list empty-state">
        Nothing currently needs your intervention.
      </div>
    );
  }
  return (
    <div id="intelligence-attention-list" className="attention-list">
      {entries.map((entry) => {
        const { risk } = entry;
        const people = entry.people?.length ? entry.people.join(", ") : "No person linked";
        const actions = entry.agent_actions?.length ? entry.agent_actions.join(" · ") : "No Prism action recorded yet";
        return (
          <article key={risk.id} className={`attention-card ${risk.severity}`}>
            <div className="attention-card-heading">
              <span className="risk-level">{humanize(risk.severity)}</span>
              <span>{people}</span>
            </div>
            <h3>{risk.summary}</h3>
            <p>{entry.impact}</p>
            <dl>
              <div>
                <dt>Prism action</dt>
                <dd>{actions}</dd>
              </div>
              <div>
                <dt>Expected now</dt>
                <dd>{entry.current_expectation}</dd>
              </div>
              <div>
                <dt>Why you see this</dt>
                <dd>{entry.why_visible}</dd>
              </div>
            </dl>
            {entry.manager_options?.length ? (
              <div className="manager-options">
                {entry.manager_options.map((option, index) => (
                  <span key={index}>{option}</span>
                ))}
              </div>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}

function briefSections(brief: Brief): Array<[string, string[]]> {
  const sections: Array<[string, string[] | undefined]> = [
    ["Needs attention", brief.needs_attention],
    ["Important changes", brief.important_changes],
    ["Completed", brief.completed],
    ["In progress", brief.in_progress],
    ["New blockers", brief.new_blockers],
    ["Resolved blockers", brief.resolved_blockers],
    ["Missed commitments", brief.missed_commitments],
    ["Changed ETAs", brief.changed_etas],
    ["Dependencies at risk", brief.dependencies_at_risk],
    ["People waiting", brief.people_waiting],
    ["No action required", brief.no_action_required],
  ];
  return sections.filter((section): section is [string, string[]] => Boolean(section[1] && section[1].length));
}

function BriefBox({ brief }: { brief: Brief | null }) {
  if (!brief) {
    return (
      <div id="intelligence-brief" className="brief-grid empty-state">
        No management brief is available yet.
      </div>
    );
  }
  const sections = briefSections(brief);
  if (!sections.length) {
    return (
      <div id="intelligence-brief" className="brief-grid empty-state">
        No material management changes recorded today.
      </div>
    );
  }
  return (
    <div id="intelligence-brief" className="brief-grid">
      {sections.map(([title, values]) => (
        <section key={title} className="brief-section">
          <h3>{title}</h3>
          <ul>
            {values.map((value, index) => (
              <li key={index}>{value}</li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export function OverviewPage() {
  const app = useApp();
  const { data, reload } = useLegacyData();
  const [running, setRunning] = useState(false);
  const totals = data.totals;
  const missing = data.employees.filter((employee) => !data.updates.some((update) => update.employee_id === employee.id));

  const runIntelligence = async () => {
    setRunning(true);
    try {
      const result = await agentApi<Schema<"IntelligenceCycleResult">>("/api/v2/management/intelligence/run", { method: "POST" });
      app.setStatus(
        `Intelligence refreshed: ${result.active_risks} active risk(s), ${result.decisions_created} new decision(s), ${result.no_action} no-action decision(s). No Teams messages were sent.`,
      );
      await reload();
    } catch (error) {
      app.setStatus(errorMessage(error), true);
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <SetupCallout />
      <AgentFoundationPanel />
      <div id="legacy-today" hidden={app.modes.v22 === true}>
        <TodayAgentPanel />

        <p className="section-label">Team pulse</p>
        <section className="stats" aria-label="Team overview">
          <article className="stat-card">
            <span>Team members</span>
            <strong id="stat-employees">{totals?.employees ?? "—"}</strong>
          </article>
          <article className="stat-card">
            <span>Updates today</span>
            <strong id="stat-updates">{data.totals?.updates ?? "—"}</strong>
          </article>
          <article className="stat-card warning">
            <span>Open blockers</span>
            <strong id="stat-blockers">{totals?.blockers ?? "—"}</strong>
          </article>
          <article className="stat-card warning">
            <span>Open commitments</span>
            <strong id="stat-commitments">{totals?.commitments ?? "—"}</strong>
          </article>
          <article className="stat-card danger">
            <span>Open escalations</span>
            <strong id="stat-escalations">{totals?.escalations ?? "—"}</strong>
          </article>
        </section>

        <section className="panel intelligence-attention">
          <div className="panel-heading">
            <div>
              <h2>Needs your attention</h2>
              <p className="panel-note">Only issues where manager involvement may improve the outcome.</p>
            </div>
            <div className="intelligence-heading-actions">
              <button
                id="run-intelligence-button"
                className="mini-button"
                type="button"
                data-tooltip="Recalculate risks and management decisions. This does not send Teams messages."
                disabled={running}
                onClick={runIntelligence}
              >
                Refresh intelligence
              </button>
              <span id="intelligence-attention-count" className="badge">
                {data.attention.length}
              </span>
            </div>
          </div>
          <AttentionList entries={data.attention} />
        </section>

        <section className="panel intelligence-brief-panel">
          <div className="panel-heading">
            <div>
              <h2>Daily management brief</h2>
              <p className="panel-note">Changes and consequences, without repeating every update.</p>
            </div>
            <time id="intelligence-brief-date" className="brief-date">
              {data.brief ? new Date(`${data.brief.date}T00:00:00`).toLocaleDateString([], { dateStyle: "medium" }) : ""}
            </time>
          </div>
          <BriefBox brief={data.brief} />
        </section>

        <details className="panel daily-review">
          <summary className="panel-heading">
            <div>
              <h2>Daily manager review</h2>
              <p className="panel-note">People without an update today appear here. Send a reminder only when needed.</p>
            </div>
            <span id="missing-updates-count" className="badge">
              {missing.length}
            </span>
          </summary>
          <ListBox
            id="missing-updates-list"
            items={missing}
            empty="Everyone has submitted an update today."
            render={(employee) => (
              <Item
                key={employee.id}
                title={employee.name}
                meta={`${employee.role} has not sent an update today.`}
                actions={<ActionButton label="Record Teams reminder" action="daily-reminder" id={employee.id} />}
              />
            )}
          />
        </details>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Flagged by rules</h2>
              <p className="panel-note">Deterministic checks on current work, separate from Prism's judgement.</p>
            </div>
            <span id="findings-count" className="badge">
              {data.findings.length}
            </span>
          </div>
          <ListBox
            id="findings-list"
            items={data.findings}
            empty="No active rule findings."
            render={(finding, index) => (
              <Item
                key={index}
                title={finding.reason}
                meta={finding.severity.replace("_", " ")}
              />
            )}
          />
        </section>
      </div>
    </>
  );
}
