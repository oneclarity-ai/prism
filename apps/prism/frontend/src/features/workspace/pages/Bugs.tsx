import { Fragment } from "react";
import { Button, Chip, Empty, Icon, SelectField } from "@/components/ui";
import { time, words } from "@/lib/format";
import { current, DateFilter, groupByDay, inPeriod, Toolbar, type WorkspacePageProps } from "./shared";

const COLUMNS = [
  ["steps", "Steps"],
  ["expected", "Expected"],
  ["actual", "Actual"],
] as const;
const INTEGRATIONS = [
  ["Email developer", "mail"],
  ["Raise Jira ticket", "ticket"],
  ["Send to manager", "send"],
] as const;

/** Only http(s) engine URLs become links; anything else is not rendered as one. */
export function safeTicketUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

export function BugsPage({ ctx }: WorkspacePageProps) {
  const severity = current(ctx, "severity");
  const status = current(ctx, "status");
  const items = inPeriod(ctx.data.bugs, current(ctx, "days", "30")).filter((item) => (!severity || item.severity === severity) && (!status || item.status === status));
  return (
    <>
      <Toolbar>
        <DateFilter ctx={ctx} />
        <SelectField
          label="Severity"
          options={[["", "All severities"], ...["critical", "high", "medium", "low"].map((key) => [key, words(key)] as const)]}
          value={severity}
          onChange={(value) => ctx.filter("severity", value)}
        />
        <SelectField
          label="Bug status"
          options={[["", "All statuses"], ...[...new Set(ctx.data.bugs.map((item) => item.status))].map((key) => [key, words(key)] as const)]}
          value={status}
          onChange={(value) => ctx.filter("status", value)}
        />
        <span className="workspace-result-count">{`${items.length} bugs`}</span>
      </Toolbar>
      {!items.length ? (
        <Empty title="No bugs in this view" description="Any issues found by your Prisms will appear here." glyph="bug" />
      ) : (
        [...groupByDay(items)].map(([day, group]) => (
          <Fragment key={day}>
            <h3 className="workspace-day-heading">
              <Icon name="calendar-days" />
              {`${day} · ${group.length} ${group.length === 1 ? "bug" : "bugs"}`}
            </h3>
            {group.map((item, index) => {
              const ticket = safeTicketUrl(item.external_url);
              return (
                <article className="workspace-panel workspace-bug" key={item.id ?? `${item.run_id}-${index}`}>
                  <div className="workspace-bug-heading">
                    <Icon name="bug" />
                    <strong>{item.title}</strong>
                    <Chip tone={["critical", "high"].includes(item.severity) ? "red" : "orange"}>{words(item.severity)}</Chip>
                    <Chip>{words(item.status)}</Chip>
                    <span className="workspace-bug-meta">{`${item.target_name || "Task"} · ${item.model || "Model"} · ${time(item.created_at)}`}</span>
                  </div>
                  <div className="workspace-bug-columns">
                    {COLUMNS.map(([key, title]) => (
                      <div key={key}>
                        <small>{title}</small>
                        <p className="workspace-prewrap">{item[key] || "—"}</p>
                      </div>
                    ))}
                  </div>
                  <div className="workspace-bug-footer">
                    {INTEGRATIONS.map(([text, glyph]) => (
                      <button key={text} type="button" className="mini-button" disabled title="This integration is not available yet.">
                        <Icon name={glyph} />
                        <span>{text}</span>
                      </button>
                    ))}
                    <Button text="Open run" glyph="circle-play" onClick={() => ctx.openRun(item.run_id)} />
                    <span className="panel-note">{item.task_title}</span>
                    {ticket ? (
                      <a className="workspace-text-link" href={ticket} target="_blank" rel="noopener noreferrer">
                        Open ticket
                      </a>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </Fragment>
        ))
      )}
    </>
  );
}
