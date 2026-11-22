import { useEffect, useRef, useState, type FormEvent } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { applyPeopleAnswer, everyone, initials, usePeople, type Person } from "./people-store";
import type { Schema } from "@/types";

type Answer = Pick<Schema<"PeopleRead">, "me" | "people">;

function PersonForm({ person, onClose }: { person: Person; onClose: () => void }) {
  const { setStatus } = useApp();
  const people = usePeople();
  const self = person.is_me;
  const [title, setTitle] = useState(person.title || "");
  const [department, setDepartment] = useState(person.department || "");
  const [manager, setManager] = useState(person.manager_id || "");
  const [responsibilities, setResponsibilities] = useState(person.responsibilities || "");
  const [notes, setNotes] = useState(person.notes || "");
  const [error, setError] = useState("");
  const titleRef = useRef<HTMLInputElement>(null);
  useEffect(() => titleRef.current?.focus(), []);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const changes: Record<string, string | null> = {};
    const compare = (key: "title" | "department" | "responsibilities" | "notes", value: string) => {
      if ((value || "") !== (person[key] || "")) changes[key] = value;
    };
    compare("title", title.trim());
    compare("department", department.trim());
    compare("responsibilities", responsibilities.trim());
    compare("notes", notes.trim());
    const nextManager = manager || null;
    if (nextManager !== (person.manager_id || null)) changes.manager_id = nextManager;
    try {
      if (Object.keys(changes).length) {
        applyPeopleAnswer(await agentApi<Answer>(`/api/v1/people/${person.id}`, { method: "PATCH", ...jsonBody(changes) }));
      }
      onClose();
      setStatus("Saved. Prism will use this from now on.");
    } catch (failure) {
      setError(errorMessage(failure));
    }
  };
  const reset = async () => {
    try {
      applyPeopleAnswer(await agentApi<Answer>(`/api/v1/people/${person.id}/reset`, { method: "POST" }));
      onClose();
      setStatus("Back to what Microsoft says.");
    } catch (failure) {
      setError(errorMessage(failure));
    }
  };

  return (
    <form id="person-edit-form" method="dialog" className="prism-editor-form" onSubmit={(event) => void save(event)}>
      <button id="person-edit-close" className="icon-button" type="button" aria-label="Close" onClick={onClose}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M6 6l12 12M18 6 6 18" />
        </svg>
      </button>
      <div className="editor-hero person-hero">
        <span id="person-edit-avatar" className="avatar large" aria-hidden="true">
          {initials(person.name)}
        </span>
        <h2 id="person-edit-name">{self ? `About you, ${person.name.split(" ")[0]}` : person.name}</h2>
        <p id="person-edit-note" className="panel-note">
          {self ? "Every Prism uses this to know who you are and how to work with you." : `${person.email} · ${person.relationship}`}
        </p>
      </div>
      <label htmlFor="person-edit-title">
        Job title
        <input id="person-edit-title" ref={titleRef} maxLength={255} autoComplete="off" value={title} onChange={(event) => setTitle(event.currentTarget.value)} />
      </label>
      <label htmlFor="person-edit-department">
        Department
        <input id="person-edit-department" maxLength={255} autoComplete="off" value={department} onChange={(event) => setDepartment(event.currentTarget.value)} />
      </label>
      <label htmlFor="person-edit-manager">
        Reports to
        <select id="person-edit-manager" value={manager} onChange={(event) => setManager(event.currentTarget.value)}>
          <option value="">Nobody / unknown</option>
          {everyone(people)
            .filter((other) => other.id !== person.id)
            .map((other) => (
              <option key={other.id} value={other.id}>
                {other.is_me ? `${other.name} (you)` : other.name}
              </option>
            ))}
        </select>
      </label>
      <label htmlFor="person-edit-responsibilities">
        <span id="person-edit-responsibilities-label">{self ? "What you do" : "What they do"}</span>
        <textarea
          id="person-edit-responsibilities"
          rows={3}
          maxLength={2000}
          placeholder="For example: Owns the billing service and on-call for payments."
          value={responsibilities}
          onChange={(event) => setResponsibilities(event.currentTarget.value)}
        />
      </label>
      <label htmlFor="person-edit-notes">
        <span id="person-edit-notes-label">{self ? "How you like to work" : "Notes for Prism"}</span>
        <textarea
          id="person-edit-notes"
          rows={2}
          maxLength={2000}
          placeholder={self ? "For example: Short messages, decisions in writing, no meetings before 10." : "For example: Prefers short messages, best reached in the morning."}
          value={notes}
          onChange={(event) => setNotes(event.currentTarget.value)}
        />
      </label>
      <p id="person-edit-error" className="inline-error" role="alert" hidden={!error}>
        {error}
      </p>
      <div className="dialog-actions">
        <button id="person-edit-reset" className="button secondary" type="button" hidden={!person.overrides.length} onClick={() => void reset()}>
          Reset to Microsoft
        </button>
        <button id="person-edit-cancel" className="button secondary" type="button" onClick={onClose}>
          Cancel
        </button>
        <button className="button" type="submit">
          Save
        </button>
      </div>
    </form>
  );
}

export interface PersonEditDialogProps {
  person: Person | null;
  onClose: () => void;
}

/** `<dialog id="person-edit-dialog">`; opens modally whenever `person` is set. */
export function PersonEditDialog({ person, onClose }: PersonEditDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (person && !dialog.open) dialog.showModal();
    else if (!person && dialog.open) dialog.close();
  }, [person]);
  return (
    <dialog id="person-edit-dialog" className="picker prism-editor-dialog" ref={ref} onClose={onClose}>
      {person ? <PersonForm key={person.id} person={person} onClose={() => ref.current?.close()} /> : null}
    </dialog>
  );
}
