import type { KeyboardEvent } from "react";
import { Button, Chip, Empty, PrismLogo, SearchField, SelectField, StatusChip, Tabs } from "@/components/ui";
import { plainSummary, words } from "@/lib/format";
import { CLOSED_TASK_STATES } from "../constants";
import type { Agent, OrgMember } from "../types";
import { current, type PageContext, type WorkspacePageProps } from "./shared";

export interface RosterItem {
  prism: OrgMember | null;
  agent: Agent | undefined;
}

const isArchivedPrism = (prism: OrgMember) => String(prism.state).toLowerCase() === "archived";

export function linkedPrism(agent: Agent, ctx: PageContext): OrgMember | undefined {
  return ctx.prisms?.find(
    (item) =>
      agent.key === `prism-${String(item.id).replaceAll("-", "").slice(0, 8)}` ||
      agent.name?.replace(/^Prism:\s*/i, "").toLowerCase() === item.name.toLowerCase(),
  );
}

const STATES: Record<string, readonly [string, string]> = {
  active: ["Active", "green"],
  draft: ["Draft", "gray"],
  onboarding: ["Setting up", "blue"],
  awaiting_confirmation: ["Review needed", "orange"],
  paused: ["Paused", "gray"],
};

function StateChip({ prism }: { prism: OrgMember }) {
  const key = String(prism.state).toLowerCase();
  const [text, tone] = Object.hasOwn(STATES, key) ? STATES[key] : [words(prism.state), "gray"];
  return <Chip tone={tone}>{text}</Chip>;
}

/** Every Prism is listed, whether or not its computer exists yet; engine agents with no Prism still show. */
export function rosterItems(ctx: PageContext): RosterItem[] {
  const used = new Set<string>();
  const items: RosterItem[] = (ctx.prisms || [])
    .filter((prism) => !isArchivedPrism(prism))
    .map((prism) => {
      const agent = ctx.data.agents.find((item) => linkedPrism(item, ctx)?.id === prism.id);
      if (agent) used.add(agent.id);
      return { prism, agent };
    });
  for (const agent of ctx.data.agents) if (!used.has(agent.id)) items.push({ prism: null, agent });
  return items;
}

export function RosterCard({ item: { prism, agent }, ctx }: { item: RosterItem } & WorkspacePageProps) {
  const name = prism?.name || String(agent?.name || "").replace(/^Prism:\s*/i, "");
  const open = () => {
    if (prism) ctx.navigate("prism", prism.id);
    else if (agent) ctx.openAgent(agent);
  };
  const openTasks = agent
    ? ctx.data.tasks.filter((task) => task.agent_id === agent.id && !CLOSED_TASK_STATES.includes(task.status)).length
    : 0;
  const tools = prism ? (prism.tools_allowed ?? 0) : (agent?.tool_count ?? 0);
  const askFirst = prism ? (prism.tools_ask_first ?? 0) : (agent?.ask_first_count ?? 0);
  const budget = prism?.monthly_budget_usd ?? agent?.monthly_budget_usd;
  const stats: Array<[string | number, string]> = [
    [tools, "tools"],
    [askFirst, "ask first"],
    [openTasks, "open tasks"],
    [budget == null ? "—" : `$${Number(budget).toFixed(0)}`, "per month"],
  ];
  return (
    <article
      className="pc-card"
      tabIndex={0}
      role="link"
      aria-label={`${name}, open settings`}
      onClick={open}
      onKeyDown={(event: KeyboardEvent<HTMLElement>) => {
        if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          open();
        }
      }}
    >
      <div className="pc-head">
        <PrismLogo prism={prism || agent} className="prism-logo" />
        <div className="pc-who">
          <strong>{name}</strong>
          <span>{prism ? `${prism.job_role} · ${prism.department}` : words(agent?.role)}</span>
        </div>
        {prism ? <StateChip prism={prism} /> : <StatusChip value={agent?.status} />}
      </div>
      <p className="pc-summary">{plainSummary(prism?.description || agent?.description) || "No description yet."}</p>
      <div className="pc-stats">
        {stats.map(([value, label]) => (
          <span key={label}>
            <strong>{value}</strong>
            <small>{label}</small>
          </span>
        ))}
      </div>
      <div className="pc-foot">
        {prism ? (
          <Button
            text="Open chat"
            glyph="message-square"
            className="pc-link"
            onClick={(event) => {
              event.stopPropagation();
              ctx.openPrism(prism.id);
            }}
          />
        ) : null}
        <Button
          text="More settings"
          glyph="arrow-right"
          className="pc-link pc-link-end"
          onClick={(event) => {
            event.stopPropagation();
            open();
          }}
        />
      </div>
    </article>
  );
}

export function agentsActions(ctx: PageContext) {
  return <Button text="New Prism" glyph="plus" className="button" onClick={() => ctx.createPrism()} />;
}

const SETUP = ["draft", "onboarding", "awaiting_confirmation"];

export function AgentsPage({ ctx }: WorkspacePageProps) {
  const items = rosterItems(ctx);
  if (!items.length) return <Empty title="No Prisms yet" description="Create a Prism to add it to your team." glyph="bot" />;
  const stateOf = (item: RosterItem) =>
    String(item.prism?.state || (item.agent?.status === "active" ? "active" : item.agent?.status) || "").toLowerCase();
  const departments = [
    ...new Set(items.map((item) => item.prism?.department).filter((value): value is string => Boolean(value))),
  ].sort();
  const matches = (item: RosterItem) => {
    const query = current(ctx, "q").trim().toLowerCase();
    const text =
      `${item.prism?.name || item.agent?.name} ${item.prism?.job_role || ""} ${item.prism?.department || ""} ${plainSummary(item.prism?.description || item.agent?.description)}`.toLowerCase();
    const filter = current(ctx, "state", "all");
    const group = filter === "all" || (filter === "setup" ? SETUP.includes(stateOf(item)) : stateOf(item) === filter);
    return (
      (!query || text.includes(query)) && group && (!current(ctx, "dept") || item.prism?.department === current(ctx, "dept"))
    );
  };
  const shown = items.filter(matches);
  const states = [
    ["all", "All", items.length],
    ["active", "Active", items.filter((i) => stateOf(i) === "active").length],
    ["setup", "Setting up", items.filter((i) => SETUP.includes(stateOf(i))).length],
    ["paused", "Paused", items.filter((i) => stateOf(i) === "paused").length],
  ] as const;
  return (
    <div className="pc-page">
      <div className="pc-toolbar">
        <SearchField label="Search Prisms" value={current(ctx, "q")} onChange={(value) => ctx.filter("q", value)} />
        {departments.length > 1 ? (
          <SelectField
            label="Department"
            options={[["", "All departments"], ...departments.map((d) => [d, d] as const)]}
            value={current(ctx, "dept")}
            onChange={(value) => ctx.filter("dept", value)}
          />
        ) : null}
        <Tabs options={states} value={current(ctx, "state", "all")} onChange={(value) => ctx.filter("state", value)} />
      </div>
      <div className="pc-grid">
        {shown.length ? (
          shown.map((item) => <RosterCard key={item.prism?.id ?? item.agent?.id} item={item} ctx={ctx} />)
        ) : (
          <Empty title="No Prisms match" description="Try a different search or filter." glyph="search" />
        )}
      </div>
    </div>
  );
}
