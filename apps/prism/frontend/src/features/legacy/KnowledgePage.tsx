import { Fragment, useRef, useState, type FormEvent } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { categoryLabel, dateTime } from "./format";
import { useLegacyData } from "./LegacyDataProvider";
import type { KnowledgeEntry } from "./types";

interface DistributeResult {
  delivered: unknown[];
  skipped: unknown[];
  failures: unknown[];
  task_changes: number;
}

const EMPTY_FORM = { category: "team", title: "", content: "" };

function Multiline({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, index) => (
        <Fragment key={index}>
          {index ? <br /> : null}
          {line}
        </Fragment>
      ))}
    </>
  );
}

export function KnowledgePage() {
  const { setStatus, askDialog } = useApp();
  const { data, reload } = useLegacyData();
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);

  const resetForm = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const payload = { category: form.category.trim(), title: form.title.trim(), content: form.content.trim() };
    setBusy(true);
    try {
      const isEditing = Boolean(editingId);
      await agentApi(isEditing ? `/api/v1/management-context/${editingId}` : "/api/v1/management-context", {
        method: isEditing ? "PATCH" : "POST",
        ...jsonBody(payload),
      });
      resetForm();
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
    } finally {
      setBusy(false);
    }
  };

  const edit = (entry: KnowledgeEntry) => {
    setEditingId(entry.id);
    setForm({ category: entry.category, title: entry.title, content: entry.content });
    formRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    titleRef.current?.focus();
  };

  const remove = async (entry: KnowledgeEntry) => {
    if (!(await askDialog({ title: `Delete “${entry.title}”?`, message: "It will be removed from Prism's saved knowledge.", confirmLabel: "Delete", danger: true }))) return;
    try {
      await agentApi(`/api/v1/management-context/${entry.id}`, { method: "DELETE" });
      if (editingId === entry.id) resetForm();
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };

  const distribute = async (entry: KnowledgeEntry) => {
    if (!(await askDialog({ title: `Distribute “${entry.title}”?`, message: "It will be sent to its owners in the active automation run.", confirmLabel: "Distribute" }))) return;
    try {
      const result = await agentApi<DistributeResult>(`/api/v1/management-context/${entry.id}/distribute-deployment-list`, { method: "POST" });
      const failureText = result.failures.length ? ` ${result.failures.length} delivery failure(s); task state was not changed.` : "";
      setStatus(
        `Deployment list: ${result.delivered.length} delivered, ${result.skipped.length} already delivered, ${result.task_changes} task change(s).${failureText}`,
        Boolean(result.failures.length),
      );
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };

  const entries = data.knowledge;
  return (
    <aside className="panel quick-add">
      <div className="panel-heading">
        <div>
          <h2>Add context</h2>
          <p className="panel-note">Add the context, preferences, and working agreements Prism should keep in mind.</p>
        </div>
      </div>
      <form id="knowledge-context-form" className="knowledge-context-form" ref={formRef} onSubmit={submit}>
        <label>
          What is this about?
          <select name="category" required value={form.category} onChange={(event) => setForm({ ...form, category: event.currentTarget.value })}>
            <option value="team">Team context</option>
            <option value="work">Current work</option>
            <option value="people">Person or role</option>
            <option value="communication">Communication preference</option>
            <option value="escalation">Escalation guidance</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          Short title
          <input
            name="title"
            maxLength={200}
            placeholder="For example: How the connector work is divided"
            required
            ref={titleRef}
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.currentTarget.value })}
          />
        </label>
        <label>
          What should Prism know?
          <textarea
            name="content"
            maxLength={10000}
            placeholder="Write the background, preference, rule, or important detail here."
            required
            value={form.content}
            onChange={(event) => setForm({ ...form, content: event.currentTarget.value })}
          />
        </label>
        <div className="knowledge-form-footer">
          <span>Saved privately in your database.</span>
          <div className="knowledge-form-actions">
            <button id="cancel-knowledge-edit" className="button secondary" type="button" hidden={!editingId} onClick={resetForm}>
              Cancel
            </button>
            <button id="knowledge-submit-button" className="button" type="submit" disabled={busy}>
              {editingId ? "Update context" : "Save context"}
            </button>
          </div>
        </div>
      </form>
      <div className="knowledge-saved">
        <div className="knowledge-saved-heading">
          <span>Saved knowledge</span>
          <span id="knowledge-count" className="knowledge-count">
            {entries.length}
          </span>
        </div>
        {entries.length ? (
          <div id="knowledge-list" className="knowledge-list">
            {entries.map((entry) => (
              <article key={entry.id} className="knowledge-entry">
                <div className="knowledge-entry-heading">
                  <span className={`knowledge-category ${entry.category}`}>{categoryLabel(entry.category)}</span>
                  <time>{dateTime(entry.updated_at)}</time>
                </div>
                <h3>{entry.title}</h3>
                <p>
                  <Multiline text={entry.content} />
                </p>
                <div className="knowledge-entry-actions">
                  {entry.title.toLowerCase().startsWith("deployment list") ? (
                    <button className="mini-button" type="button" data-knowledge-action="distribute" data-id={entry.id} onClick={() => void distribute(entry)}>
                      Distribute list
                    </button>
                  ) : null}
                  <button className="mini-button" type="button" data-knowledge-action="edit" data-id={entry.id} onClick={() => edit(entry)}>
                    Edit
                  </button>
                  <button className="mini-button danger-button" type="button" data-knowledge-action="delete" data-id={entry.id} onClick={() => void remove(entry)}>
                    Delete
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div id="knowledge-list" className="knowledge-list empty-state">
            {data.totals ? "No context saved yet. Add something Prism should remember." : "No context saved yet."}
          </div>
        )}
      </div>
    </aside>
  );
}
