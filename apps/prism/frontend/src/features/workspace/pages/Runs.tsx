import { DataTable, Empty, StatusChip, TitleCell, type DataTableRow } from "@/components/ui";
import { count, duration, money } from "@/lib/format";
import {
  agentName,
  current,
  DateFilter,
  groupByDay,
  inPeriod,
  PeriodCaption,
  RUN_STATES,
  runCost,
  StatusTabs,
  Toolbar,
  type WorkspacePageProps,
} from "./shared";

export function RunsPage({ ctx }: WorkspacePageProps) {
  const items = inPeriod(ctx.data.runs, current(ctx, "days", "30"));
  const shown = items.filter((item) => current(ctx, "status", "all") === "all" || item.status === current(ctx, "status"));
  const rows: DataTableRow[] = [];
  for (const [day, group] of groupByDay(shown)) {
    rows.push({ group: `${day} · ${group.length} runs`, key: `group-${day}` });
    group.forEach((item) =>
      rows.push({
        key: item.id,
        cells: [
          <TitleCell
            title={item.task_title || "Untitled run"}
            subtitle={`${String(item.id).slice(0, 8)}${item.kind === "orchestrator" ? " · parallel" : ""}`}
            onClick={() => ctx.openRun(item.id)}
          />,
          item.agent_name || agentName(ctx, item.agent_id),
          <StatusChip value={item.status} />,
          duration(item),
          count(item.total_tokens ?? Number(item.input_tokens || 0) + Number(item.output_tokens || 0)),
          money(runCost(item)),
          item.started_at ? new Date(item.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—",
        ],
      }),
    );
  }
  return (
    <>
      <Toolbar>
        <DateFilter ctx={ctx} />
      </Toolbar>
      <StatusTabs ctx={ctx} items={items} states={RUN_STATES} />
      {!shown.length ? (
        <Empty title="No runs in this view" description="Choose another status or date range." glyph="circle-play" />
      ) : (
        <>
          <DataTable headers={["Task", "Prism", "Status", "Duration", "Tokens", "Cost", "Started"]} rows={rows} />
          <PeriodCaption items={ctx.data.runs} noun="runs" />
        </>
      )}
    </>
  );
}
