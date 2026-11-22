import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Chip, Empty, Panel } from "@/components/ui";
import { agentApi, errorMessage } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { LIBRARY_URL, useSkillEditor, type LibrarySkill } from "./skills";

/** Settings > Skills body (and the Workspace > Skills page): the shared skill library. */
export function SkillLibrary() {
  const { setStatus, askDialog, settings } = useApp();
  const { editSkill, setLibraryArchived } = useSkillEditor();
  const [skills, setSkills] = useState<LibrarySkill[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const alive = useRef(true);

  const load = useCallback(async () => {
    try {
      const rows = await agentApi<LibrarySkill[]>(LIBRARY_URL);
      if (!alive.current) return;
      setFailure(null);
      setSkills(rows);
    } catch (error) {
      if (alive.current) setFailure(errorMessage(error));
    }
  }, []);
  const reload = useCallback(async () => {
    setSkills(null);
    setFailure(null);
    await load();
  }, [load]);

  useEffect(() => {
    alive.current = true;
    void load();
    return () => {
      alive.current = false;
    };
  }, [load]);

  // The old code refreshed the library every time the Skills section was opened.
  const visible = settings.isOpen && settings.section === "skills";
  const wasVisible = useRef(visible);
  useEffect(() => {
    if (visible && !wasVisible.current) void reload();
    wasVisible.current = visible;
  }, [visible, reload]);

  const toggleArchive = async (skill: LibrarySkill) => {
    const yes = await askDialog({
      title: skill.archived ? "Restore this skill?" : "Archive this shared skill?",
      message: skill.archived
        ? "It becomes available in the library. Review its assignments before using it again."
        : "It stops being used by every Prism. Their chat history and tool permissions stay intact.",
      confirmLabel: skill.archived ? "Restore" : "Archive",
    });
    if (!yes) return;
    try {
      await setLibraryArchived(skill, !skill.archived);
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };

  if (failure !== null) {
    return (
      <>
        <Empty title="Skills could not load" description={failure} glyph="brain" />
        <Button text="Try again" onClick={() => void reload()} />
      </>
    );
  }
  if (!skills) return <p className="panel-note">Loading skills…</p>;

  return (
    <>
      <Panel title="Workspace skills" subtitle="Reusable know-how for every department. Each Prism chooses its own skills and keeps its context private.">
        <Button text="Add skill" glyph="plus" className="button" onClick={() => editSkill(null, reload)} />
      </Panel>
      <div className="skill-list">
        {!skills.length ? (
          <Empty
            title="No shared skills yet"
            description="Add reusable instructions here. Skills created from onboarding stay private in each Prism’s settings."
            glyph="brain"
          />
        ) : null}
        {skills.map((skill) => (
          <article className="skill-row" key={skill.id}>
            <div className="skill-info">
              <strong>{skill.name}</strong>
              <Chip tone="gray">{skill.archived ? "Archived skill" : "Skill"}</Chip>
              <p className="panel-note">{skill.description}</p>
              <details>
                <summary>{`Instructions · revision ${skill.revision}`}</summary>
                <p className="skill-instructions">{skill.instructions}</p>
              </details>
              {skill.required_tools.length || skill.required_connections.length ? (
                <p className="panel-note">{`Requires: ${[...skill.required_tools, ...skill.required_connections].join(", ")}`}</p>
              ) : null}
            </div>
            <div className="skill-actions">
              <Button text="Edit" glyph="pencil" onClick={() => editSkill(skill, reload)} />
              <Button text={skill.archived ? "Restore" : "Archive"} onClick={() => void toggleArchive(skill)} />
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
