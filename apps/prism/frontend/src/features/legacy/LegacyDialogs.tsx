import { useRef, useState, type FormEvent } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { today } from "./format";
import { useLegacyData } from "./LegacyDataProvider";
import { payloadFor, RECORD_FORMS, RECORD_KINDS, type OptionSource, type RecordField, type RecordKind } from "./recordForms";
import { useModalDialog } from "./useModalDialog";
import type { LegacyDataset } from "./types";

function optionsFor(source: OptionSource, data: LegacyDataset): Array<[string, string]> {
  switch (source) {
    case "employees":
      return data.employees.map((employee) => [employee.id, `${employee.name} — ${employee.role}`]);
    case "projects":
      return data.projects.map((project) => [project.id, project.name]);
    case "tasks":
      return data.tasks.map((task) => [task.id, task.title]);
    case "blockers":
      return data.blockers.map((blocker) => [blocker.id, blocker.description.slice(0, 70)]);
  }
}

function Field({ field, data }: { field: RecordField; data: LegacyDataset }) {
  const kind = field.kind ?? "text";
  let control;
  if (kind === "textarea") {
    control = <textarea name={field.name} required={field.required} />;
  } else if (kind === "select") {
    control = (
      <select name={field.name} required={field.required}>
        {field.from ? <option value="">{field.from.empty}</option> : null}
        {field.from
          ? optionsFor(field.from.source, data).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))
          : field.options?.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
      </select>
    );
  } else {
    control = (
      <input
        name={field.name}
        type={kind}
        placeholder={field.placeholder}
        required={field.required}
        defaultValue={field.today ? today() : undefined}
      />
    );
  }
  return (
    <label>
      {field.label}
      {control}
    </label>
  );
}

function RecordForm({ kind }: { kind: RecordKind }) {
  const { setStatus } = useApp();
  const { data, reload, closeRecord } = useLegacyData();
  const [busy, setBusy] = useState(false);
  const spec = RECORD_FORMS[kind];

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    try {
      await agentApi(spec.endpoint, { method: "POST", ...jsonBody(payloadFor(new FormData(form))) });
      form.reset();
      closeRecord();
      setStatus("Saved successfully.");
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form data-endpoint={spec.endpoint} data-kind={kind} onSubmit={submit}>
      {spec.fields.map((field) => (
        <Field key={field.name} field={field} data={data} />
      ))}
      <button className="button" type="submit" data-tooltip={spec.tooltip} disabled={busy}>
        {spec.submit}
      </button>
    </form>
  );
}

function RecordDialog() {
  const { recordOpen, closeRecord, version } = useLegacyData();
  const [kind, setKind] = useState<RecordKind>("employee");
  const ref = useRef<HTMLDialogElement>(null);
  useModalDialog(ref, recordOpen, closeRecord);
  return (
    <dialog id="record-dialog" className="wide" ref={ref}>
      <div className="dialog-body">
        <div>
          <h2>New record</h2>
          <p>Add employees, projects, tasks, and other records by hand.</p>
        </div>
        <label htmlFor="form-selector">What do you want to add?</label>
        <select id="form-selector" value={kind} onChange={(event) => setKind(event.currentTarget.value as RecordKind)}>
          {RECORD_KINDS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        {/* Keyed on the data version so a reload re-renders the form (and its option lists) from scratch. */}
        <div id="form-container">
          <RecordForm key={`${kind}-${version}`} kind={kind} />
        </div>
        <div className="dialog-actions">
          <button id="record-close" className="button secondary" type="button" onClick={closeRecord}>
            Close
          </button>
        </div>
      </div>
    </dialog>
  );
}

function RevisionDialog() {
  const { setStatus } = useApp();
  const { revisionFor, closeRevision, reload } = useLegacyData();
  const ref = useRef<HTMLDialogElement>(null);
  const [fields, setFields] = useState({ reason: "", description: "", deadline: "" });
  const [openedFor, setOpenedFor] = useState<string | null>(null);
  useModalDialog(ref, revisionFor !== null, closeRevision);

  // A fresh dialog starts empty (old `revisionForm.reset()` before showModal).
  if (revisionFor !== openedFor) {
    setOpenedFor(revisionFor);
    if (revisionFor !== null) setFields({ reason: "", description: "", deadline: "" });
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const reason = fields.reason.trim();
    const description = fields.description.trim();
    const { deadline } = fields;
    if (!revisionFor || !reason || !description || !deadline) return;
    try {
      await agentApi(`/api/v1/commitments/${revisionFor}/mark-missed`, { method: "POST", ...jsonBody({ reason }) });
      await agentApi(`/api/v1/commitments/${revisionFor}/revisions`, {
        method: "POST",
        ...jsonBody({ description, missed_reason: reason, deadline: new Date(deadline).toISOString() }),
      });
      closeRevision();
      setStatus("Missed commitment and revised ETA saved with full history.");
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };

  return (
    <dialog id="revision-dialog" ref={ref}>
      <form id="revision-form" method="dialog" onSubmit={submit}>
        <h2>Record missed commitment and revised ETA</h2>
        <p className="subtle">This keeps the original promise and creates a new linked commitment.</p>
        <label>
          Why was the commitment missed?
          <textarea id="revision-reason" required value={fields.reason} onChange={(event) => setFields({ ...fields, reason: event.currentTarget.value })} />
        </label>
        <label>
          New commitment
          <textarea id="revision-description" required value={fields.description} onChange={(event) => setFields({ ...fields, description: event.currentTarget.value })} />
        </label>
        <label>
          Revised deadline
          <input id="revision-deadline" type="datetime-local" required value={fields.deadline} onChange={(event) => setFields({ ...fields, deadline: event.currentTarget.value })} />
        </label>
        <div className="dialog-actions">
          <button id="revision-cancel" className="button secondary" type="button" data-tooltip="Close this window without saving." onClick={closeRevision}>
            Cancel
          </button>
          <button className="button" type="submit" data-tooltip="Keep the old commitment and save the new deadline.">
            Save revised ETA
          </button>
        </div>
      </form>
    </dialog>
  );
}

export function LegacyDialogs() {
  return (
    <>
      <RevisionDialog />
      <RecordDialog />
    </>
  );
}
