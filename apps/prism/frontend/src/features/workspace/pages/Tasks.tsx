import { Button, DataTable, Empty, SearchField, SelectField, StatusChip, TitleCell } from "@/components/ui";
import { age } from "@/lib/format";
import {
  agentName,
  choices,
  current,
  PeriodCaption,
  StatusTabs,
  targetName,
  TASK_STATES,
  Toolbar,
  type PageContext,
  type WorkspacePageProps,
} from "./shared";

export function tasksActions(ctx: PageContext) {
  return <Button text="New task" glyph="plus" className="button" onClick={() => ctx.editTask()} />;
}

export function TasksPage({ ctx }: WorkspacePageProps) {
  const view = current(ctx, "view", "list");
  const query = current(ctx, "query").toLowerCase();
  const filtered = ctx.data.tasks.filter(
    (item) =>
      (!current(ctx, "agent") || item.agent_id === current(ctx, "agent")) &&
      (!current(ctx, "target") || item.target_app_id === current(ctx, "target")) &&
      `${item.title} ${item.goal}`.toLowerCase().includes(query),
  );
  const shown = filtered.filter((item) => current(ctx, "status", "all") === "all" || item.status === current(ctx, "status"));
  return (
    <>
      <Toolbar>
        <SearchField label="Search tasks…" value={current(ctx, "query")} onChange={(value) => ctx.filter("query", value)} />
        <SelectField label="Prism" options={choices(ctx.data.agents, "All Prisms")} value={current(ctx, "agent")} onChange={(value) => ctx.filter("agent", value)} />
        <SelectField label="Target app" options={choices(ctx.data.targets, "All targets")} value={current(ctx, "target")} onChange={(value) => ctx.filter("target", value)} />
        <div className="workspace-view-modes">
          {(
            [
              ["list", "list"],
              ["board", "columns-3"],
            ] as const
          ).map(([mode, glyph]) => (
            <Button
              key={mode}
              glyph={glyph}
              className={`mini-button${view === mode ? " active" : ""}`}
              title={mode === "list" ? "List view" : "Board view"}
              aria-pressed={view === mode}
              onClick={() => ctx.filter("view", mode)}
            />
          ))}
        </div>
      </Toolbar>
      <div>
        <StatusTabs ctx={ctx} items={filtered} states={TASK_STATES} />
        {!shown.length ? (
          <Empty title="No tasks match" description="Try another filter, or create your first task." />
        ) : (
          <>
            {view === "board" ? (
              <div className="workspace-task-board">
                {TASK_STATES.slice(1).map(([key, title]) => {
                  const entries = shown.filter((item) => item.status === key);
                  return (
                    <section className="workspace-board-column" key={key}>
                      <h3>{`${title} · ${entries.length}`}</h3>
                      {entries.map((task) => (
                        <button type="button" className="workspace-board-task" key={task.id} onClick={() => ctx.editTask(task)}>
                          <strong>{task.title}</strong>
                          <span className="panel-note">{agentName(ctx, task.agent_id)}</span>
                        </button>
                      ))}
                    </section>
                  );
                })}
              </div>
            ) : (
              <DataTable
                headers={["Task", "Prism", "Target", "Status", "Created"]}
                rows={shown.map((item) => ({
                  key: item.id,
                  cells: [
                    <TitleCell title={item.title} subtitle={item.goal ?? ""} onClick={() => ctx.editTask(item)} />,
                    agentName(ctx, item.agent_id),
                    targetName(ctx, item.target_app_id),
                    <StatusChip value={item.status} />,
                    age(item.created_at),
                  ],
                }))}
              />
            )}
            <PeriodCaption items={ctx.data.tasks} noun="tasks" />
          </>
        )}
      </div>
    </>
  );
}
