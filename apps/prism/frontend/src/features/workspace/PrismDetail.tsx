// A Prism's settings: separate job skills from app permissions. Record text is rendered as React text.
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { Button, DataTable, Empty, Icon, Markdown, Panel, StatusChip, TitleCell } from "@/components/ui";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { emit } from "@/lib/events";
import { age } from "@/lib/format";
import { PrismSkillRows } from "@/features/prisms/skills";
import { isOpenTask, PRISM_TABS } from "./constants";
import type { PageContext } from "./pages/shared";
import type { Agent, OrgMember, PrismTool } from "./types";

const GRANTS = [
  { value: "allowed", label: "Allowed", glyph: "circle-check", hint: "Uses it freely" },
  { value: "ask_first", label: "Ask first", glyph: "shield-check", hint: "Waits for your approval" },
  { value: "off", label: "Off", glyph: "ban", hint: "Never gets the tool" },
] as const;
const DEFAULT_LIMITS = { max_turns: 150, run_budget_usd: 3, monthly_budget_usd: 100 };

type Grants = Record<string, string>;

async function patchPrism(prism: OrgMember, body: Record<string, unknown>): Promise<OrgMember> {
  const updated = await agentApi<OrgMember>(`/api/v2/prisms/${prism.id}`, {
    method: "PATCH",
    ...jsonBody({ expected_lifecycle_version: prism.lifecycle_version, ...body }),
  });
  emit("prisms-changed");
  return updated;
}
const patchProfile = (prism: Pick<OrgMember, "id">, body: Record<string, unknown>) =>
  agentApi<OrgMember>(`/api/v2/prisms/${prism.id}/profile`, { method: "PATCH", ...jsonBody(body) });

function SaveBar({ dirty, busy, onSave, onDiscard }: { dirty: boolean; busy: boolean; onSave: () => void; onDiscard: () => void }) {
  return (
    <div className={`pd-savebar${dirty ? " dirty" : ""}`} hidden={!dirty}>
      <span className="pd-dirty">{busy ? "Saving…" : dirty ? "Unsaved changes" : "All changes saved"}</span>
      <Button text="Discard" className="button secondary" disabled={!dirty || busy} onClick={onDiscard} />
      <Button text="Save changes" className="button" disabled={!dirty || busy} onClick={onSave} />
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="pd-field">
      <span className="pd-label">{label}</span>
      {children}
      {hint ? <small className="pd-hint">{hint}</small> : null}
    </label>
  );
}

/** A number with a unit on one side, so "turns" and "$" read as part of the field. */
function UnitInput({
  value,
  onChange,
  unit,
  side = "end",
  ...range
}: {
  value: string;
  onChange: (value: string) => void;
  unit: string;
  side?: "start" | "end";
  min: number;
  max: number;
  step: number;
}) {
  const input = <input type="number" value={value} onChange={(event) => onChange(event.currentTarget.value)} {...range} />;
  return (
    <div className={`pd-unit pd-unit-${side}`}>
      {side === "start" ? <span>{unit}</span> : null}
      {input}
      {side === "end" ? <span>{unit}</span> : null}
    </div>
  );
}

interface RichText {
  value: string;
  setValue: (value: string) => void;
  setEditing: (on: boolean, focus?: boolean) => void;
  pencil: ReactNode;
  box: ReactNode;
}

/** Long text (job description, instructions): shown rendered; the pencil switches to editing. */
function useRichText(initial: string, { placeholder = "", rows = 12, max = 8000 }: { placeholder?: string; rows?: number; max?: number }): RichText {
  const [value, setValue] = useState(initial);
  const [editing, setEditingState] = useState(!initial.trim());
  const input = useRef<HTMLTextAreaElement>(null);
  const focusNext = useRef(false);
  useEffect(() => {
    if (editing && focusNext.current) input.current?.focus();
    focusNext.current = false;
  }, [editing]);
  const setEditing = (on: boolean, focus = true) => {
    focusNext.current = on && focus;
    setEditingState(on);
  };
  return {
    value,
    setValue,
    setEditing,
    pencil: (
      <Button
        glyph={editing ? "circle-check" : "pencil"}
        className="icon-button pd-pencil"
        title={editing ? "Done editing" : "Edit"}
        onClick={() => setEditing(!editing)}
      />
    ),
    box: (
      <div className="pd-rich">
        <Markdown className="pd-rich-view" source={value} hidden={editing} />
        <textarea
          ref={input}
          className="pd-rich-input"
          rows={rows}
          maxLength={max}
          placeholder={placeholder}
          spellCheck={false}
          hidden={!editing}
          value={value}
          onChange={(event) => setValue(event.currentTarget.value)}
        />
      </div>
    ),
  };
}

interface TabProps {
  ctx: PageContext;
  prism: OrgMember;
  tools: readonly PrismTool[];
  agent: Agent | undefined;
  openTasks: number;
  reload: () => Promise<void>;
}

function OverviewTab({ ctx, prism, tools, openTasks, reload }: TabProps) {
  const { setStatus } = useApp();
  const [name, setName] = useState(prism.name);
  const [role, setRole] = useState(prism.job_role);
  const [department, setDepartment] = useState(prism.department);
  const [reports, setReports] = useState(prism.reports_to_prism_id || "");
  const [turns, setTurns] = useState(String(prism.max_turns ?? DEFAULT_LIMITS.max_turns));
  const [runBudget, setRunBudget] = useState(String(prism.run_budget_usd ?? DEFAULT_LIMITS.run_budget_usd));
  const [monthly, setMonthly] = useState(String(prism.monthly_budget_usd ?? DEFAULT_LIMITS.monthly_budget_usd));
  const rich = useRichText(prism.description, { placeholder: "What does this Prism do? Write it, or press Generate with AI.", rows: 12 });
  const description = rich.value;
  const [generating, setGenerating] = useState(false);
  const [busy, setBusy] = useState(false);
  const fail = (error: unknown) => setStatus(errorMessage(error), true);

  const snapshot = () => JSON.stringify([name.trim(), role.trim(), department.trim(), reports, description, turns, runBudget, monthly]);
  const start = useRef(snapshot()).current;
  const dirty = snapshot() !== start;

  const allowed = tools.filter((tool) => tool.grant === "allowed").length;
  const ask = tools.filter((tool) => tool.grant === "ask_first").length;
  const stats = [
    [allowed, "tools allowed", "circle-check"],
    [ask, "ask first", "shield-check"],
    [openTasks, "open tasks", "list-checks"],
    [`$${Number(prism.monthly_budget_usd ?? DEFAULT_LIMITS.monthly_budget_usd).toFixed(0)}`, "monthly budget", "coins"],
  ] as const;

  const blocked = new Set([prism.id]);
  for (let changed = true; changed; ) {
    changed = false;
    for (const row of ctx.prisms) {
      if (row.reports_to_prism_id && blocked.has(row.reports_to_prism_id) && !blocked.has(row.id)) {
        blocked.add(row.id);
        changed = true;
      }
    }
  }
  const managers = ctx.prisms.filter((item) => !blocked.has(item.id) && String(item.state).toLowerCase() !== "archived");

  const canGenerate = Boolean(name.trim() && role.trim());
  const generate = async () => {
    if (!canGenerate) return;
    setGenerating(true);
    try {
      const result = await agentApi<{ description: string }>("/api/v2/prisms/generate-description", {
        method: "POST",
        ...jsonBody({ name: name.trim(), role: role.trim(), department: department.trim(), notes: description.slice(0, 4000) }),
      });
      rich.setValue(result.description);
      rich.setEditing(false);
      setStatus("Job description drafted. Review it, then save.");
    } catch (error) {
      fail(error);
    } finally {
      setGenerating(false);
    }
  };
  const save = async () => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = { name: name.trim(), description: description.trim(), job_role: role.trim(), department: department.trim() };
      if ((reports || null) !== (prism.reports_to_prism_id || null)) body.reports_to_prism_id = reports || null;
      const current = await patchPrism(prism, body);
      await patchProfile(current, { max_turns: Number(turns), run_budget_usd: Number(runBudget), monthly_budget_usd: Number(monthly) });
      setStatus(`${current.name} saved.`);
      await reload();
    } catch (error) {
      fail(error);
      setBusy(false);
    }
  };

  return (
    <>
      <div className="pd-stats">
        {stats.map(([value, label, glyph]) => (
          <div className="pd-stat" key={label}>
            <Icon name={glyph} />
            <strong>{value}</strong>
            <span>{label}</span>
          </div>
        ))}
      </div>
      <div className="pd-grid">
        <Panel title="Profile" subtitle="Who this Prism is and what it is for" className="pd-card">
          <div className="pd-row">
            <Field label="Name">
              <input type="text" maxLength={120} value={name} onChange={(event) => setName(event.currentTarget.value)} />
            </Field>
            <Field label="Role">
              <input type="text" maxLength={120} value={role} disabled={prism.is_chief_of_staff} onChange={(event) => setRole(event.currentTarget.value)} />
            </Field>
            <Field label="Department">
              <input type="text" maxLength={100} value={department} onChange={(event) => setDepartment(event.currentTarget.value)} />
            </Field>
            <Field label="Reports to">
              <select value={reports} disabled={prism.is_chief_of_staff} onChange={(event) => setReports(event.currentTarget.value)}>
                <option value="">Choose a Prism</option>
                {managers.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="pd-field">
            <div className="pd-desc-head">
              <span className="pd-label">Job description</span>
              <button
                type="button"
                className="button ghost ai"
                disabled={generating || !canGenerate}
                title={canGenerate ? "" : "Fill in name and role first"}
                onClick={() => void generate()}
              >
                <Icon name="sparkles" />
                <span>{generating ? "Writing a job description…" : description.trim() ? "Regenerate with AI" : "Generate with AI"}</span>
              </button>
              {rich.pencil}
            </div>
            {rich.box}
          </div>
        </Panel>
        <Panel title="Limits" subtitle="Guardrails enforced on every run" className="pd-card">
          <Field label="Steps per run" hint="A run stops after this many steps.">
            <UnitInput value={turns} onChange={setTurns} unit="turns" min={5} max={300} step={1} />
          </Field>
          <Field label="Budget per run" hint="A run stops when it reaches this.">
            <UnitInput value={runBudget} onChange={setRunBudget} unit="$" side="start" min={0.5} max={50} step={0.5} />
          </Field>
          <Field label="Monthly budget" hint="Across all of this Prism's runs.">
            <UnitInput value={monthly} onChange={setMonthly} unit="$" side="start" min={1} max={100000} step={1} />
          </Field>
        </Panel>
      </div>
      <SaveBar dirty={dirty} busy={busy} onSave={() => void save()} onDiscard={() => void reload()} />
    </>
  );
}

function InstructionsTab({ prism, reload }: TabProps) {
  const { setStatus } = useApp();
  const saved = prism.role_instructions || "";
  const rich = useRichText(saved, {
    placeholder: "You are …\n- Always cite where you found something\n- Ask before sending anything\n- Keep replies short",
    rows: 20,
    max: 20000,
  });
  const [busy, setBusy] = useState(false);
  const text = rich.value;
  const save = async () => {
    setBusy(true);
    try {
      await patchProfile(prism, { role_instructions: text });
      setStatus("Instructions saved. The Prism follows them on its next run.");
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
      setBusy(false);
    }
  };
  return (
    <>
      <Panel
        title="Instructions"
        subtitle="The playbook this Prism follows. It is sent to the model at the start of every run, after its job description and your house rules."
        className="pd-card"
        action={rich.pencil}
      >
        {rich.box}
        <small className="pd-hint">{`${text.length.toLocaleString()} characters`}</small>
      </Panel>
      <SaveBar
        dirty={text !== saved}
        busy={busy}
        onSave={() => void save()}
        onDiscard={() => {
          rich.setValue(saved);
          rich.setEditing(!saved.trim(), false);
        }}
      />
    </>
  );
}

function SkillsTab({ prism, onCount }: TabProps & { onCount: (count: number) => void }) {
  return (
    <Panel title="Skills" subtitle="How this Prism does its job. Created from your chat onboarding answers and editable here.">
      <div className="prism-skill-rows">
        <PrismSkillRows prism={prism} onCount={onCount} />
      </div>
    </Panel>
  );
}

function ToolsTab({ prism, tools, reload }: TabProps) {
  const { setStatus } = useApp();
  const initial: Grants = Object.fromEntries(tools.map((tool) => [tool.name, tool.grant]));
  const [grants, setGrants] = useState<Grants>(initial);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(grants) !== JSON.stringify(initial);
  const save = async () => {
    setBusy(true);
    try {
      await patchProfile(prism, { tool_grants: grants });
      setStatus("Tools saved. The Prism uses them on its next run.");
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
      setBusy(false);
    }
  };
  let group = "";
  return (
    <>
      <Panel title="Tool access" subtitle="Which apps and actions this Prism may use. Skills never change these permissions. Messages and external changes still require approval.">
        <div className="pd-counts">
          {GRANTS.map((grant) => (
            <div className="pd-count" key={grant.value}>
              <strong>{Object.values(grants).filter((value) => value === grant.value).length}</strong>
              <span>{grant.label}</span>
              <small className="panel-note">{grant.hint.toLowerCase()}</small>
            </div>
          ))}
        </div>
        <div className="pd-tools">
          {tools.map((tool) => {
            const heading = tool.group !== group;
            group = tool.group;
            return (
              <Fragment key={tool.name}>
                {heading ? <div className="pd-group">{tool.group}</div> : null}
                <div className="pd-tool-row">
                  <div className="pd-tool-info">
                    <strong>{tool.label}</strong>
                    <span className="badge">Tool access</span>
                    <code>{tool.name}</code>
                    <p className="panel-note">{tool.description}</p>
                  </div>
                  <div className="segmented pd-grant" role="group" aria-label={`${tool.label} permission`}>
                    {GRANTS.map((grant) => (
                      <Button
                        key={grant.value}
                        text={grant.label}
                        className={`${grants[tool.name] === grant.value ? "active " : ""}grant-${grant.value}`}
                        aria-pressed={grants[tool.name] === grant.value}
                        disabled={prism.state === "archived"}
                        onClick={() => setGrants((current) => ({ ...current, [tool.name]: grant.value }))}
                      />
                    ))}
                  </div>
                </div>
              </Fragment>
            );
          })}
        </div>
      </Panel>
      <SaveBar dirty={dirty} busy={busy} onSave={() => void save()} onDiscard={() => setGrants(initial)} />
    </>
  );
}

function TasksTab({ ctx, prism, agent }: TabProps) {
  const mine = agent ? ctx.data.tasks.filter((task) => task.agent_id === agent.id) : [];
  return (
    <Panel
      title="Assigned tasks"
      subtitle={mine.length ? `${mine.filter(isOpenTask).length} open of ${mine.length}` : `Everything ${prism.name} is responsible for`}
      className="pd-card"
      action={<Button text="New task" glyph="plus" className="button" onClick={() => ctx.editTask(null, { agent_id: agent?.id })} />}
    >
      {!agent ? (
        <Empty title="Its computer is not set up yet" description="Tasks appear here once this Prism has been given work." glyph="circle-play" />
      ) : !mine.length ? (
        <Empty title="No tasks yet" description="Create a task, or ask this Prism in its chat." glyph="list-checks" />
      ) : (
        <DataTable
          headers={["Task", "Status", "Created"]}
          rows={mine.map((task) => ({
            key: task.id,
            cells: [<TitleCell title={task.title} subtitle={task.goal ?? ""} onClick={() => ctx.editTask(task)} />, <StatusChip value={task.status} />, age(task.created_at)],
          }))}
        />
      )}
    </Panel>
  );
}

export interface PrismDetailProps {
  ctx: PageContext;
  prism: OrgMember;
  tools: readonly PrismTool[];
  agent: Agent | undefined;
  tab: string;
  setTab: (tab: string) => void;
  reload: () => Promise<void>;
}

export function PrismDetail({ ctx, prism, tools, agent, tab, setTab, reload }: PrismDetailProps) {
  const [skillCount, setSkillCount] = useState(0);
  const openTasks = agent ? ctx.data.tasks.filter((task) => task.agent_id === agent.id && isOpenTask(task)).length : 0;
  const counts: Record<string, number> = { tools: tools.filter((tool) => tool.grant !== "off").length, tasks: openTasks };
  const props: TabProps = { ctx, prism, tools, agent, openTasks, reload };
  return (
    <div className="prism-detail">
      <div className="pd-nav" role="tablist" aria-label="Prism sections">
        {PRISM_TABS.map(([key, text]) => (
          <button key={key} type="button" className={`pd-tab${key === tab ? " active" : ""}`} role="tab" aria-selected={key === tab} onClick={() => setTab(key)}>
            <span>{text}</span>
            {counts[key] ? <em className="pd-tab-count">{counts[key]}</em> : null}
            {key === "skills" ? (
              <em className="pd-tab-count" data-skill-count="" hidden={tab !== "skills" || !skillCount}>
                {tab === "skills" && skillCount ? skillCount : ""}
              </em>
            ) : null}
          </button>
        ))}
      </div>
      <div className="pd-body">
        {tab === "instructions" ? (
          <InstructionsTab {...props} />
        ) : tab === "skills" ? (
          <SkillsTab {...props} onCount={setSkillCount} />
        ) : tab === "tools" ? (
          <ToolsTab {...props} />
        ) : tab === "tasks" ? (
          <TasksTab {...props} />
        ) : (
          <OverviewTab {...props} />
        )}
      </div>
    </div>
  );
}
