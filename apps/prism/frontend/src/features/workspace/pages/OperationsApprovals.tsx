import { Button, Empty, Panel, StatusChip, Tabs } from "@/components/ui";
import { time, words } from "@/lib/format";
import type { ApprovalPayload, EngineApproval, ManagedApproval, PayloadKey } from "../types";
import { current, DateFilter, inPeriod, Toolbar, type WorkspacePageProps } from "./shared";

/** Engine approval, optionally joined with its Prism-side record (`managed`). */
interface CombinedApproval extends EngineApproval {
  managed?: ManagedApproval;
}

const DETAIL_KEYS: readonly PayloadKey[] = ["site", "reason", "summary", "question"];

export function combineApprovals(engine: readonly EngineApproval[], managed: readonly ManagedApproval[]): CombinedApproval[] {
  const combined: CombinedApproval[] = engine.map((item) => ({ ...item, managed: managed.find((entry) => entry.engine_approval_id === item.id) }));
  managed
    .filter((item) => !combined.some((entry) => entry.managed?.id === item.id))
    .forEach((item) =>
      combined.push({
        ...item,
        task_title: item.run_title,
        payload: { arguments: item.payload } as ApprovalPayload,
        managed: item,
      }),
    );
  return combined;
}

export function ApprovalsWorkspacePage({ ctx }: WorkspacePageProps) {
  const combined = combineApprovals(ctx.data.approvals, ctx.managedApprovals);
  const filtered = inPeriod(combined, current(ctx, "days", "30"));
  const status = current(ctx, "status", "pending");
  const shown = filtered.filter((item) => item.status === status);
  return (
    <>
      <Toolbar>
        <Tabs
          options={["pending", "approved", "rejected"].map((key) => [key, words(key).replace(/^./, (letter) => letter.toUpperCase()), filtered.filter((item) => item.status === key).length] as const)}
          value={status}
          onChange={(value) => ctx.filter("status", value)}
        />
        <DateFilter ctx={ctx} />
      </Toolbar>
      {!shown.length ? (
        <Empty
          title={status === "pending" ? "Nothing waiting for you" : "No decisions in this period"}
          description="Actions that need your approval appear here. Sign-ins and questions continue in the Prism conversation."
          glyph="shield-check"
        />
      ) : (
        shown.map((item) => {
          const args = item.payload?.arguments || {};
          const managed = item.managed;
          return (
            <Panel
              key={item.id}
              title={args.title || args.summary || args.question || item.task_title || words(item.action)}
              subtitle={`${managed?.prism_name || item.task_title || "Prism"} · ${time(item.created_at)}`}
            >
              <StatusChip value={item.status} />
              {DETAIL_KEYS.map((key) => (args[key] ? <p className="workspace-prewrap" key={key}>{`${words(key)}: ${args[key]}`}</p> : null))}
              <Toolbar>
                {item.status === "pending" && managed?.can_decide_here ? (
                  <>
                    <Button text="Reject" onClick={() => ctx.decide(managed, "reject")} />
                    <Button text="Approve" className="button" onClick={() => ctx.decide(managed, "approve")} />
                  </>
                ) : null}
                {managed ? (
                  <Button text="Open in Prism" onClick={() => ctx.openPrism(managed.prism_id, managed.run_id)} />
                ) : item.run_id ? (
                  <Button text="Open run" onClick={() => ctx.openRun(item.run_id as string)} />
                ) : null}
              </Toolbar>
            </Panel>
          );
        })
      )}
    </>
  );
}
