import { Button, Chip, Empty, Icon, Metric, Panel, StatusChip, TitleCell } from "@/components/ui";
import { money, time, words } from "@/lib/format";
import { isOpenTask } from "../constants";
import { RosterCard, rosterItems } from "./Agents";
import { agentName, current, DateFilter, inPeriod, runCost, Toolbar, type PageContext, type WorkspacePageProps } from "./shared";
import type { Run } from "../types";

export function dashboardActions(ctx: PageContext) {
  return (
    <Toolbar>
      <DateFilter ctx={ctx} fallback="7" />
      <Button text="New task" glyph="plus" className="button" onClick={() => ctx.editTask()} />
    </Toolbar>
  );
}

function SummaryRow({ run, ctx }: { run: Run } & WorkspacePageProps) {
  return (
    <div className="workspace-summary-row">
      <span className="workspace-row-icon">
        <Icon name="bot" />
      </span>
      <TitleCell
        title={run.task_title || "Untitled run"}
        subtitle={`${run.agent_name || agentName(ctx, run.agent_id)} · ${time(run.created_at)} · ${money(runCost(run))}`}
        onClick={() => ctx.openRun(run.id)}
      />
      <StatusChip value={run.status} />
    </div>
  );
}

export function DashboardPage({ ctx }: WorkspacePageProps) {
  const days = current(ctx, "days", "7");
  const runs = inPeriod(ctx.data.runs, days);
  const bugs = inPeriod(ctx.data.bugs, days);
  const tasks = ctx.data.tasks.filter(isOpenTask);
  const cost = runs.reduce((sum, run) => sum + Number(runCost(run) ?? 0), 0);
  const period = days === "0" ? "All available" : `Last ${days} days`;
  const roster = rosterItems(ctx).slice(0, 6);
  return (
    <div>
      <div className="workspace-metrics four">
        <Metric title="Active Prisms" value={ctx.data.agents.filter((item) => item.status === "active").length} detail={`${tasks.length} open tasks`} glyph="bot" />
        <Metric
          title={`Runs · ${period}`}
          value={runs.length}
          detail={`${runs.filter((run) => run.status === "succeeded").length} succeeded · ${runs.filter((run) => run.status === "failed").length} failed`}
          glyph="circle-play"
        />
        <Metric title="Needs approval" value={(ctx.data.approvals || []).filter((item) => item.status === "pending").length} detail="Computer actions waiting on you" glyph="shield-check" />
        <Metric title="Cost" value={money(cost)} detail={`${money(runs.length ? cost / runs.length : 0)} per run`} glyph="coins" />
      </div>
      <div className="workspace-dashboard-columns">
        <Panel
          title="Recent runs"
          subtitle={`${period} · newest first`}
          action={<Button text="View all" glyph="arrow-right" className="workspace-text-link" onClick={() => ctx.navigate("runs")} />}
        >
          {runs.length ? runs.slice(0, 6).map((run) => <SummaryRow key={run.id} run={run} ctx={ctx} />) : <Empty title="No runs in this period" description="Start a task from a Prism conversation." glyph="circle-play" />}
        </Panel>
        <Panel
          title="Latest bugs"
          subtitle={`Last ${days === "0" ? "available" : days} days`}
          action={<Button text="View all" glyph="arrow-right" className="workspace-text-link" onClick={() => ctx.navigate("bugs")} />}
        >
          {!bugs.length ? (
            <Empty title="No bugs in this period." glyph="bug" />
          ) : (
            bugs.slice(0, 4).map((bug, index) => (
              <div className="workspace-summary-row" key={bug.id ?? index}>
                <TitleCell title={bug.title} subtitle={bug.target_name || "Task"} onClick={() => ctx.openRun(bug.run_id)} />
                <Chip tone={["critical", "high"].includes(bug.severity) ? "red" : "orange"}>{words(bug.severity)}</Chip>
              </div>
            ))
          )}
        </Panel>
      </div>
      <Panel title="Your Prisms" action={<Button text="Manage" glyph="arrow-right" className="workspace-text-link" onClick={() => ctx.navigate("agents")} />}>
        {roster.length ? (
          <div className="pc-grid">
            {roster.map((item) => (
              <RosterCard key={item.prism?.id ?? item.agent?.id} item={item} ctx={ctx} />
            ))}
          </div>
        ) : (
          <Empty title="No Prisms yet" description="Create a Prism to get started." glyph="bot" />
        )}
      </Panel>
    </div>
  );
}
