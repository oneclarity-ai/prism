import { Chip, DataTable, Empty, Icon, Metric, Panel, SelectField } from "@/components/ui";
import { count, duration, money, words } from "@/lib/format";
import type { Analytics, UsageCount, UsageDay, UsageRow } from "../types";
import { choices, current, DateFilter, Toolbar, type PageContext, type WorkspacePageProps } from "./shared";

const percent = (value: unknown) => `${Math.round(Number(value || 0) * 100)}%`;

export function UsageChart({ analytics }: { analytics: Analytics }) {
  const days: UsageDay[] = analytics.by_day || [];
  if (!days.length) return <Empty title="No usage in this period" description="Your first run will appear here." glyph="trending-up" />;
  const maxRuns = Math.max(4, Math.ceil(Math.max(...days.map((day) => Number(day.runs || 0))) / 4) * 4);
  const maxCost = Math.max(0.01, ...days.map((day) => Number(day.cost_usd || 0)));
  const width = 1000 / days.length;
  const points = days.map((day, i) => `${50 + width * i + width / 2},${220 - (200 * Number(day.cost_usd || 0)) / maxCost}`);
  return (
    <div className="workspace-usage-chart">
      <svg viewBox="0 0 1100 260" role="img" aria-label="Daily runs as bars and cost as a line. Exact amounts are in the data table below.">
        {[0, 1, 2, 3, 4].map((i) => {
          const y = 220 - i * 50;
          return (
            <g key={i}>
              <line x1={50} x2={1050} y1={y} y2={y} className="workspace-chart-grid" />
              <text x={36} y={y + 4} textAnchor="end" className="workspace-chart-label">
                {String(Math.round((maxRuns * i) / 4))}
              </text>
              <text x={1060} y={y + 4} className="workspace-chart-label">{`$${((maxCost * i) / 4).toFixed(maxCost < 0.04 ? 3 : 2)}`}</text>
            </g>
          );
        })}
        {days.map((day, i) => {
          const x = 50 + width * i;
          const height = (200 * Number(day.runs || 0)) / maxRuns;
          return (
            <g key={`${day.date}-${i}`}>
              <rect x={x + width * 0.17} y={220 - height} width={Math.max(1, width * 0.66)} height={height} rx={3} className="workspace-chart-bar">
                <title>{`${day.date}: ${day.runs || 0} runs, ${money(day.cost_usd)}`}</title>
              </rect>
              {i % Math.max(1, Math.ceil(days.length / 10)) === 0 ? (
                <text x={x + width / 2} y={246} textAnchor="middle" className="workspace-chart-label">
                  {new Date(`${day.date}T12:00:00`).toLocaleDateString([], { day: "numeric", month: "short" })}
                </text>
              ) : null}
            </g>
          );
        })}
        <polyline points={points.join(" ")} fill="none" className="workspace-chart-cost" strokeWidth={2} />
      </svg>
      <div className="workspace-chart-legend">
        <Chip tone="red">Cost ($)</Chip>
        <Chip tone="blue">Runs</Chip>
      </div>
    </div>
  );
}

export function usageActions(ctx: PageContext) {
  return (
    <Toolbar>
      <SelectField label="Prism" options={choices(ctx.data.agents, "All Prisms")} value={current(ctx, "agent")} onChange={(value) => ctx.filter("agent", value, true)} />
      <DateFilter ctx={ctx} fallback="30" analytics />
    </Toolbar>
  );
}

function Breakdown({ title, rows, field }: { title: string; rows: UsageCount[]; field: "status" | "severity" }) {
  return (
    <Panel title={title}>
      {rows.map((item, index) => (
        <div className="workspace-breakdown-row" key={index}>
          <span>{words(item[field])}</span>
          <strong>{item.count || 0}</strong>
        </div>
      ))}
      {!rows.length ? <p className="panel-note">No data yet.</p> : null}
    </Panel>
  );
}

function UsageTable({ title, rows, name }: { title: string; rows: UsageRow[]; name: "agent_name" | "model" }) {
  return (
    <Panel title={title}>
      <DataTable
        headers={["Name", "Runs", "Tokens", "Cost", "Success rate"]}
        rows={rows.map((item) => [
          item[name] || "Unknown",
          item.runs || 0,
          count(Number(item.input_tokens || 0) + Number(item.output_tokens || 0)),
          money(item.cost_usd),
          percent(item.success_rate),
        ])}
      />
    </Panel>
  );
}

export function UsagePage({ ctx }: WorkspacePageProps) {
  const analytics: Analytics = ctx.analytics || ctx.data.analytics || {};
  const totals = analytics.totals || {};
  return (
    <>
      <div className="workspace-vault workspace-runtime">
        <Icon name="circle-check" />
        <div>{`${ctx.data.status?.workers_online || 0} workers online · ${ctx.data.status?.azure_configured ? "Azure OpenAI connected" : "Computer service connected"}`}</div>
      </div>
      <div className="workspace-metrics six">
        <Metric title="Total cost" value={money(totals.cost_usd)} detail={`${money(totals.avg_cost_per_run)} per run`} glyph="coins" />
        <Metric title="Runs" value={totals.runs || 0} detail={`${totals.succeeded || 0} succeeded · ${totals.failed || 0} failed`} glyph="circle-play" />
        <Metric title="Success rate" value={percent(totals.success_rate)} detail="of finished runs" glyph="trending-up" />
        <Metric
          title="Tokens"
          value={count(Number(totals.input_tokens || 0) + Number(totals.output_tokens || 0))}
          detail={`${count(totals.input_tokens)} in · ${count(totals.output_tokens)} out`}
          glyph="cpu"
        />
        <Metric title="Avg duration" value={duration(totals)} detail="per finished run" glyph="timer" />
        <Metric title="Bugs found" value={totals.bugs || 0} detail={`${totals.tests_pass || 0} tests passed`} glyph="bug" />
      </div>
      <Panel title="Cost and runs per day" subtitle={`Last ${current(ctx, "days", "30")} days`}>
        <UsageChart analytics={analytics} />
      </Panel>
      <div className="workspace-breakdowns">
        <Breakdown title="Runs by outcome" rows={analytics.by_status || []} field="status" />
        <Breakdown title="Test results" rows={analytics.tests_by_status || []} field="status" />
        <Breakdown title="Bugs by severity" rows={analytics.bugs_by_severity || []} field="severity" />
      </div>
      <UsageTable title="By Prism" rows={analytics.by_agent || []} name="agent_name" />
      <UsageTable title="By model" rows={analytics.by_model || []} name="model" />
      <details className="workspace-exact-usage">
        <summary>Daily usage data</summary>
        <DataTable
          headers={["Date", "Runs", "Cost", "Input tokens", "Output tokens"]}
          rows={(analytics.by_day || []).map((day) => [day.date, day.runs || 0, `$${Number(day.cost_usd || 0).toFixed(4)}`, day.input_tokens || 0, day.output_tokens || 0])}
        />
      </details>
    </>
  );
}
