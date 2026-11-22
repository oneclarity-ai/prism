// Shared library definitions and private onboarding skills; permissions remain in Tools.
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Chip, Empty, useFormDialog, type FieldSpec, type FormValues } from "@/components/ui";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { emit } from "@/lib/events";
import { splitNames } from "./helpers";
import type { Prism } from "./types";

export const LIBRARY_URL = "/api/v2/prisms/skills/library";
export const skillUrl = (prism: Pick<Prism, "id">): string => `/api/v2/prisms/${prism.id}/skills`;

/** A shared library skill (`GET /api/v2/prisms/skills/library`). */
export interface LibrarySkill {
  id: string;
  name: string;
  description: string;
  instructions: string;
  required_tools: string[];
  required_connections: string[];
  revision: number;
  archived: boolean;
  owner_prism_id?: string | null;
}

/** One row of a Prism's skills (`GET /api/v2/prisms/{id}/skills`): the library skill plus this Prism's assignment. */
export interface PrismSkill extends LibrarySkill {
  assignment_revision?: number | null;
  enabled?: boolean;
  approved_revision?: number | null;
  approved_definition?: LibrarySkill | null;
  missing: string[];
}
interface PrismSkillsData {
  skills: PrismSkill[];
  tool_labels?: Record<string, string>;
}
interface FromOnboardingResult {
  skills_created?: number;
}

const changed = () => emit("skills-changed");

type SkillFields = Pick<LibrarySkill, "name" | "description" | "instructions"> &
  Partial<Pick<LibrarySkill, "required_tools" | "required_connections">>;

function skillFields(skill: Partial<SkillFields> = {}): FieldSpec[] {
  return [
    { name: "name", label: "Skill name", required: true, maxLength: 120, value: skill.name },
    { name: "description", label: "What this skill does", required: true, maxLength: 500, value: skill.description },
    { name: "instructions", label: "Reusable instructions", type: "textarea", required: true, maxLength: 2000, value: skill.instructions },
    {
      name: "required_tools",
      label: "Required tool identifiers, separated by commas",
      value: skill.required_tools?.join(", "),
      placeholder: "For example: teams_read_chat, save_file",
    },
    {
      name: "required_connections",
      label: "Required connections, separated by commas",
      value: skill.required_connections?.join(", "),
      placeholder: "For example: teams, computer, outlook",
    },
  ];
}
const content = (values: FormValues) => ({
  ...values,
  required_tools: splitNames(values.required_tools),
  required_connections: splitNames(values.required_connections),
});
/** The form values a skill would produce unchanged (used to re-save a skill with one flag flipped). */
const valuesOf = (skill: LibrarySkill): FormValues =>
  Object.fromEntries(skillFields(skill).map((field) => [field.name, String(field.value ?? "")]));

export interface SkillEditor {
  /** Add (`null`) or edit a shared library skill; `reload` runs after a successful save. */
  editSkill: (skill: LibrarySkill | null, reload: () => Promise<void> | void) => void;
  /** Edit a skill that is private to one Prism. */
  editPrivateSkill: (prism: Prism, skill: PrismSkill, reload: () => Promise<void> | void) => void;
  /** PUT the library skill unchanged except for its archived flag (the "Archive"/"Restore" action). */
  setLibraryArchived: (skill: LibrarySkill, archived: boolean) => Promise<void>;
}

export function useSkillEditor(): SkillEditor {
  const { openFormDialog } = useFormDialog();
  const editSkill = useCallback<SkillEditor["editSkill"]>(
    (skill, reload) => {
      openFormDialog(
        skill ? "Edit shared skill" : "Add shared skill",
        skillFields(skill || {}),
        async (values) => {
          await agentApi(skill ? `${LIBRARY_URL}/${skill.id}` : LIBRARY_URL, {
            method: skill ? "PUT" : "POST",
            ...jsonBody({ ...content(values), ...(skill ? { expected_revision: skill.revision, archived: skill.archived } : {}) }),
          });
          changed();
          await reload();
        },
        {
          description:
            "Shared workspace instructions. Keep private details out. Saving never changes tool access. Library edits require explicit adoption by each Prism.",
        },
      );
    },
    [openFormDialog],
  );
  const editPrivateSkill = useCallback<SkillEditor["editPrivateSkill"]>(
    (prism, skill, reload) => {
      openFormDialog(
        "Edit skill",
        skillFields(skill),
        async (values) => {
          await agentApi(`${skillUrl(prism)}/${skill.id}/definition`, {
            method: "PUT",
            ...jsonBody({
              ...content(values),
              expected_revision: skill.revision,
              expected_assignment_revision: skill.assignment_revision,
              archived: skill.archived,
            }),
          });
          changed();
          await reload();
        },
        { description: `Changes apply only to ${prism.name}, starting with its next task. Tool access and action approvals stay unchanged.` },
      );
    },
    [openFormDialog],
  );
  const setLibraryArchived = useCallback<SkillEditor["setLibraryArchived"]>(async (skill, archived) => {
    await agentApi(`${LIBRARY_URL}/${skill.id}`, {
      method: "PUT",
      ...jsonBody({ ...content(valuesOf(skill)), expected_revision: skill.revision, archived }),
    });
    changed();
  }, []);
  return { editSkill, editPrivateSkill, setLibraryArchived };
}

export interface SkillSetup {
  /** POST /skills/from-onboarding: create the three private skills from the confirmed onboarding chat. */
  createSkillsFromOnboarding: (prism: Prism) => Promise<FromOnboardingResult>;
  /** Old compatibility export: creates the skills (no questionnaire), then `onComplete`; errors become a toast. */
  openSkillSetup: (prism: Prism, onComplete?: () => Promise<void> | void) => Promise<void>;
}

export function useSkillSetup(): SkillSetup {
  const { setStatus } = useApp();
  const createSkillsFromOnboarding = useCallback<SkillSetup["createSkillsFromOnboarding"]>(
    async (prism) => {
      const result = await agentApi<FromOnboardingResult>(`${skillUrl(prism)}/from-onboarding`, { method: "POST", body: "{}" });
      changed();
      setStatus(result.skills_created ? "3 skills created from onboarding. Edit them here in Skills." : "Your existing skills are already configured.");
      return result;
    },
    [setStatus],
  );
  const openSkillSetup = useCallback<SkillSetup["openSkillSetup"]>(
    async (prism, onComplete = async () => {}) => {
      try {
        await createSkillsFromOnboarding(prism);
        await onComplete();
      } catch (error) {
        setStatus(errorMessage(error), true);
      }
    },
    [createSkillsFromOnboarding, setStatus],
  );
  return { createSkillsFromOnboarding, openSkillSetup };
}

export interface PrismSkillRowsProps {
  prism: Prism;
  /** Called with the number of enabled skills after every load. */
  onCount?: (enabled: number) => void;
}

/**
 * Skill cards of one Prism (old `prismSkillRows(root, prism, onCount)`). Renders a fragment: stats, toolbar,
 * the Prism's own skills and the workspace library picker; the caller provides the wrapping element.
 */
export function PrismSkillRows({ prism, onCount }: PrismSkillRowsProps) {
  const { setStatus, askDialog } = useApp();
  const { editSkill, editPrivateSkill } = useSkillEditor();
  const { createSkillsFromOnboarding } = useSkillSetup();
  const [data, setData] = useState<PrismSkillsData | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const alive = useRef(true);
  const countRef = useRef(onCount);
  countRef.current = onCount;
  const prismRef = useRef(prism);
  prismRef.current = prism;

  const load = useCallback(async () => {
    try {
      const result = await agentApi<PrismSkillsData>(skillUrl(prismRef.current));
      if (!alive.current) return;
      setFailure(null);
      setData(result);
      countRef.current?.(result.skills.filter((skill) => skill.assignment_revision && skill.enabled).length);
    } catch (error) {
      if (alive.current) setFailure(errorMessage(error));
    }
  }, []);
  const reload = useCallback(async () => {
    setData(null);
    setFailure(null);
    await load();
  }, [load]);

  useEffect(() => {
    alive.current = true;
    setData(null);
    setFailure(null);
    void load();
    return () => {
      alive.current = false;
    };
  }, [prism.id, load]);

  if (failure !== null) {
    return (
      <>
        <Empty title="Skills unavailable" description={failure} glyph="brain" />
        <Button text="Try again" onClick={() => void reload()} />
      </>
    );
  }
  if (!data) return <p className="panel-note">Loading skills…</p>;

  const readonly = prism.state === "archived";
  const assigned = data.skills.filter((skill) => skill.assignment_revision);
  const available = data.skills.filter((skill) => !skill.assignment_revision && !skill.archived);
  const enabled = assigned.filter((skill) => skill.enabled);
  const labels = data.tool_labels || {};
  const readable = (value: string): string => labels[value] || value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
  const issueLabel = (issue: string): string => {
    if (issue.startsWith("Tool access is off: ")) return `Enable ${readable(issue.slice(20))} in Tools`;
    if (issue.startsWith("Connection not supported yet: ")) return `${readable(issue.slice(30))} integration is not available yet`;
    return issue;
  };

  const apply = async (skill: PrismSkill, enable: boolean) => {
    setPendingId(skill.id);
    try {
      await agentApi(`${skillUrl(prism)}/${skill.id}`, {
        method: "PUT",
        ...jsonBody({ enabled: enable, expected_skill_revision: skill.revision, expected_assignment_revision: skill.assignment_revision }),
      });
      changed();
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
    } finally {
      if (alive.current) setPendingId(null);
    }
  };

  const createFromOnboarding = async () => {
    setCreating(true);
    try {
      await createSkillsFromOnboarding(prism);
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
    } finally {
      if (alive.current) setCreating(false);
    }
  };

  const reviewUpdate = async (skill: PrismSkill) => {
    const required = [...skill.required_tools, ...skill.required_connections].map(readable).join(", ") || "no additional tools";
    const yes = await askDialog({
      title: `Use revision ${skill.revision} of ${skill.name}?`,
      message: `${skill.description}\n\n${skill.instructions}\n\nRequires: ${required}`,
      confirmLabel: "Use this revision",
    });
    if (yes) await apply(skill, true);
  };

  const card = (skill: PrismSkill, inLibrary = false) => {
    const approved = skill.enabled ? skill.approved_definition || skill : skill;
    const toggleLabel = skill.enabled ? "Disable" : "Enable";
    return (
      <article className="prism-skill-card" key={skill.id}>
        <div className="prism-skill-heading">
          <h4>{approved.name}</h4>
          <Chip tone={skill.enabled && !skill.missing.length ? "green" : "gray"}>
            {skill.archived ? "Archived" : skill.enabled ? (skill.missing.length ? "Needs access" : "Enabled") : "Not enabled"}
          </Chip>
        </div>
        <p className="panel-note">{approved.description}</p>
        <small className="panel-note">{skill.owner_prism_id ? "Private to this Prism · From onboarding" : "From workspace library"}</small>
        <details>
          <summary>Instructions</summary>
          <p className="skill-instructions">{approved.instructions}</p>
        </details>
        {skill.missing.length ? (
          <details className="skill-requirements">
            <summary>{`${skill.missing.length} access ${skill.missing.length === 1 ? "requirement" : "requirements"}`}</summary>
            <ul>
              {skill.missing.map((issue) => (
                <li key={issue}>{issueLabel(issue)}</li>
              ))}
            </ul>
          </details>
        ) : null}
        {skill.enabled && skill.approved_revision !== skill.revision ? (
          <p className="panel-note">{`Using revision ${skill.approved_revision}. Library revision ${skill.revision} is available.`}</p>
        ) : null}
        <div className="skill-actions">
          {!inLibrary ? (
            <Button
              text="Edit skill"
              glyph="pencil"
              disabled={readonly || skill.archived}
              onClick={() => (skill.owner_prism_id ? editPrivateSkill(prism, skill, reload) : editSkill(skill, reload))}
            />
          ) : null}
          <Button
            text={toggleLabel}
            aria-label={`${toggleLabel} ${approved.name}`}
            aria-pressed={Boolean(skill.enabled)}
            disabled={readonly || skill.archived || pendingId === skill.id}
            onClick={() => void apply(skill, !skill.enabled)}
          />
          {skill.enabled && skill.approved_revision !== skill.revision ? (
            <Button text="Review update" disabled={readonly || pendingId === skill.id} onClick={() => void reviewUpdate(skill)} />
          ) : null}
        </div>
      </article>
    );
  };

  return (
    <>
      <div className="skill-stats">
        {(
          [
            [enabled.length, "Enabled skills"],
            [enabled.filter((skill) => skill.missing.length).length, "Need access"],
            [available.length, "In workspace library"],
          ] as const
        ).map(([value, label]) => (
          <div className="skill-stat" key={label}>
            <strong>{value}</strong>
            <span className="panel-note">{label}</span>
          </div>
        ))}
      </div>
      <div className="skill-toolbar">
        <p className="panel-note">Edit how this Prism works here. Manage app permissions separately in Tools.</p>
        {!assigned.length ? (
          <>
            <Button
              text={creating ? "Creating skills…" : "Create 3 skills from onboarding"}
              glyph="plus"
              className="button"
              disabled={creating || readonly || prism.state !== "active"}
              aria-busy={creating ? "true" : undefined}
              onClick={() => void createFromOnboarding()}
            />
            {prism.state !== "active" && !readonly ? <p className="panel-note">Finish onboarding in chat to create your first three skills.</p> : null}
          </>
        ) : null}
      </div>
      <div className="prism-skill-grid">
        {assigned.map((skill) => card(skill))}
        {!assigned.length ? (
          <Empty
            title="Your skills will appear here"
            description="Three skills are created from your confirmed chat onboarding. No extra questions are needed."
            glyph="brain"
          />
        ) : null}
      </div>
      <details className="skill-library-picker">
        <summary>{`Workspace library · ${available.length} available`}</summary>
        <div className="prism-skill-grid">
          {available.map((skill) => card(skill, true))}
          {!available.length ? <p className="panel-note">No additional shared skills.</p> : null}
        </div>
        <Button text="Add shared skill" glyph="plus" disabled={readonly} onClick={() => editSkill(null, reload)} />
      </details>
    </>
  );
}
