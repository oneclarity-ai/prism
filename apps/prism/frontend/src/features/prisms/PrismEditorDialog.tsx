import { useImperativeHandle, useRef, useState, type Ref } from "react";
import { ColorPicker, PrismLogo } from "@/components/ui";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { prismColorKey } from "@/lib/prism-logo";
import { isArchived } from "./helpers";
import { usePrismsInternal } from "./internal";
import type { OrganizationData, Prism } from "./types";

export interface PrismEditorHandle {
  openCreate: () => void;
  openEditor: (prism: Prism) => void;
}

interface Form {
  name: string;
  role: string;
  department: string;
  reportsTo: string;
  description: string;
  how: string;
  capFiles: boolean;
  capTeams: boolean;
  logins: string;
  color: string;
}

/** Facts fixed when the dialog opens (old module-level `computersOn` / `oneStepOnboarding()` at that moment). */
interface Session {
  prism: Prism | null;
  templateRole: string;
  computersOn: boolean;
  oneStep: boolean;
  title: string;
  note: string;
}

const WORK_ROLES = new Set(["blank", "executive_assistant"]);
const BLANK_FORM: Form = {
  name: "",
  role: "",
  department: "Operations",
  reportsTo: "",
  description: "",
  how: "",
  capFiles: false,
  capTeams: false,
  logins: "never",
  color: "purple",
};
const CHIEF_DESCRIPTION = "Coordinate my Prism team across departments and keep me informed about its work.";

const isChiefRole = (role: string): boolean => role.trim().toLowerCase().replace(/\s+/g, " ") === "chief of staff";

function workFields(role: string, prism: Prism | null): Pick<Form, "capFiles" | "capTeams" | "logins" | "how"> {
  const caps = prism?.capabilities || (role === "executive_assistant" ? ["browser", "teams"] : ["browser"]);
  return { capFiles: caps.includes("files"), capTeams: caps.includes("teams"), logins: prism?.logins_policy || "never", how: prism?.role_instructions || "" };
}

/** `#prism-editor-dialog`: create a Prism, or edit/view an existing one. */
export function PrismEditorDialog({ ref }: { ref?: Ref<PrismEditorHandle> }) {
  const app = useApp();
  const { addAndSelect, loadPrisms } = usePrismsInternal();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const requestSeq = useRef(0);
  const computersOn = useRef(false);
  const queried = useRef(false);

  const [form, setForm] = useState<Form>(BLANK_FORM);
  const [session, setSession] = useState<Session>({ prism: null, templateRole: "blank", computersOn: false, oneStep: false, title: "Create a Prism", note: "", });
  const [org, setOrg] = useState<OrganizationData | null>(null);
  const [orgFailed, setOrgFailed] = useState(false);
  const [ownerOption, setOwnerOption] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [writing, setWriting] = useState(false);

  const { prism, oneStep } = session;
  const archived = Boolean(prism && isArchived(prism));
  const creating = !prism;
  const qa = session.templateRole === "qa_tester";
  const workHidden = !session.computersOn || !(qa || WORK_ROLES.has(session.templateRole)) || (!prism && oneStep);
  const howHidden = !prism || !session.computersOn || !WORK_ROLES.has(session.templateRole);
  const orgReady = org !== null;
  const chief = orgReady && isChiefRole(form.role);
  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((current) => ({ ...current, [key]: value }));

  // The old module asked once, at startup, whether every Prism has a computer.
  if (!queried.current) {
    queried.current = true;
    agentApi<{ computers?: boolean }>("/api/v2/qa/status").then(
      (status) => {
        computersOn.current = Boolean(status.computers);
      },
      () => {},
    );
  }

  /** Keep role / department / reporting line consistent (old syncEditorReporting). */
  const applyReporting = (next: Form, data: OrganizationData, hadOwnerOption: boolean): Form => {
    if (isChiefRole(next.role)) {
      setOwnerOption(true);
      return { ...next, reportsTo: "", department: "Leadership" };
    }
    if (hadOwnerOption) {
      setOwnerOption(false);
      return { ...next, reportsTo: data.chief_of_staff_id || "" };
    }
    return next;
  };

  const loadOrganization = async (target: Prism | null) => {
    const request = requestSeq.current;
    setOrgFailed(false);
    try {
      const data = await agentApi<OrganizationData>("/api/v2/prisms/organization");
      if (request !== requestSeq.current || !dialogRef.current?.open) return;
      const firstChief = !target && !data.chief_of_staff_id;
      setOrg(data);
      setForm((current) => {
        const next: Form = {
          ...current,
          role: target?.job_role || (firstChief ? "Chief of Staff" : ""),
          department: target?.department || (firstChief ? "Leadership" : "Operations"),
          reportsTo: target?.reports_to_prism_id || data.chief_of_staff_id || "",
          name: firstChief ? current.name || "Chief of Staff" : current.name,
          description: firstChief ? current.description || CHIEF_DESCRIPTION : current.description,
        };
        return applyReporting(next, data, false);
      });
    } catch (failure) {
      if (request === requestSeq.current) {
        setOrgFailed(true);
        setError(`Could not load your team: ${errorMessage(failure)}`);
      }
    }
  };

  const reset = () => {
    requestSeq.current += 1;
    setOrg(null);
    setOrgFailed(false);
    setOwnerOption(false);
    setError("");
    setBusy(false);
    setWriting(false);
  };

  useImperativeHandle(ref, () => ({
    openCreate() {
      reset();
      const oneStepOnboarding = computersOn.current && app.modes.v24 === true;
      setSession({
        prism: null,
        templateRole: "blank",
        computersOn: computersOn.current,
        oneStep: oneStepOnboarding,
        title: oneStepOnboarding ? "Onboard a new Prism" : "Create a Prism",
        note: oneStepOnboarding
          ? "Give it a colour, a name and a job. It will ask a few questions in chat to learn how you work."
          : "Create a Prism, give it a colour, a name and a job. It will ask a few questions to learn how you work.",
      });
      setForm({ ...BLANK_FORM, ...workFields("blank", null), color: prismColorKey({ name: String(Date.now()) }) });
      dialogRef.current?.showModal();
      void loadOrganization(null);
      nameRef.current?.focus();
    },
    openEditor(target) {
      reset();
      const isArch = isArchived(target);
      setSession({
        prism: target,
        templateRole: target.template_key,
        computersOn: computersOn.current,
        oneStep: computersOn.current && app.modes.v24 === true,
        title: isArch ? "Archived Prism" : "Edit Prism",
        note: isArch ? "Archived Prisms are read-only. You can still review their original role." : "Update its role, department, reporting line, and responsibilities.",
      });
      setForm({ ...BLANK_FORM, ...workFields(target.template_key, target), color: prismColorKey(target), name: target.name, description: target.description });
      dialogRef.current?.showModal();
      void loadOrganization(target);
      if (!isArch) nameRef.current?.focus();
    },
  }));

  const close = () => dialogRef.current?.close();

  const onRole = (value: string) => {
    if (!org) {
      set("role", value);
      return;
    }
    setForm((current) => applyReporting({ ...current, role: value }, org, ownerOption));
  };

  const generate = async () => {
    setWriting(true);
    setError("");
    try {
      const result = await agentApi<{ description: string }>("/api/v2/prisms/generate-description", {
        method: "POST",
        ...jsonBody({ name: form.name.trim(), role: form.role.trim(), department: form.department.trim(), notes: form.description.slice(0, 4000) }),
      });
      set("description", result.description);
      app.setStatus("Job description drafted. Review and edit it before creating.");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setWriting(false);
    }
  };

  const workPayload = () =>
    workHidden ? {} : { capabilities: [form.capFiles && "files", form.capTeams && "teams"].filter(Boolean), logins_policy: form.logins || "never" };

  const submit = async () => {
    const payload: Record<string, unknown> = {
      name: form.name,
      description: form.description,
      color: form.color,
      job_role: form.role,
      department: form.department,
      reports_to_prism_id: form.reportsTo || null,
    };
    if (!org || !form.role.trim() || !form.department.trim()) {
      setError("Choose a role, department, and reporting line for this Prism.");
      return;
    }
    if (!form.name.trim() || !form.description.trim()) {
      setError("Give this Prism both a name and a short responsibility.");
      return;
    }
    if (prism) payload.expected_lifecycle_version = Number(prism.lifecycle_version);
    else {
      payload.template_key = "blank";
      Object.assign(payload, workPayload());
    }
    setError("");
    setBusy(true);
    try {
      let saved = await agentApi<Prism>(prism ? `/api/v2/prisms/${prism.id}` : "/api/v2/prisms", { method: prism ? "PATCH" : "POST", ...jsonBody(payload) });
      if (prism && !workHidden) {
        saved = await agentApi<Prism>(`/api/v2/prisms/${prism.id}/profile`, { method: "PATCH", ...jsonBody({ ...workPayload(), role_instructions: form.how }) });
      }
      close();
      if (!prism) addAndSelect(saved);
      app.setStatus(prism ? `${saved.name} updated.` : `${saved.name} is ready. Let’s set it up.`);
      await loadPrisms();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  };

  const ready = Boolean(form.name.trim() && form.role.trim());
  const members = (() => {
    if (!org) return [];
    const blocked = new Set<string>(prism ? [prism.id] : []);
    let changed = true;
    while (changed) {
      changed = false;
      for (const row of org.members) {
        if (row.reports_to_prism_id && blocked.has(row.reports_to_prism_id) && !blocked.has(row.id)) {
          blocked.add(row.id);
          changed = true;
        }
      }
    }
    return org.members.filter((row) => !blocked.has(row.id));
  })();

  return (
    <dialog id="prism-editor-dialog" className="picker prism-editor-dialog" ref={dialogRef}>
      <form
        id="prism-editor-form"
        method="dialog"
        className="prism-editor-form prism-editor-split"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <button id="prism-editor-close" className="icon-button" type="button" aria-label="Close Prism editor" onClick={close}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
        <div className="editor-side">
          <div className="editor-hero">
            <span id="prism-editor-logo" className="editor-logo" aria-hidden="true">
              <PrismLogo colorKey={form.color} className="prism-logo" />
            </span>
            <div id="prism-editor-colors">
              <ColorPicker selected={form.color} onPick={(key) => set("color", key)} name="prism-editor-color" />
            </div>
            <h2 id="prism-editor-title">{session.title}</h2>
            <p id="prism-editor-note" className="panel-note">
              {session.note}
            </p>
          </div>
          <input id="prism-editor-id" type="hidden" value={prism?.id ?? ""} readOnly />
          <input id="prism-editor-version" type="hidden" value={prism ? String(prism.lifecycle_version) : ""} readOnly />
          <div id="prism-editor-basics">
            <label htmlFor="prism-editor-name">
              Name
              <input
                id="prism-editor-name"
                ref={nameRef}
                maxLength={120}
                required
                placeholder="For example: Executive Assistant Prism"
                disabled={archived}
                value={form.name}
                onChange={(event) => set("name", event.currentTarget.value)}
              />
            </label>
            <label htmlFor="prism-editor-role">
              Role
              <input
                id="prism-editor-role"
                maxLength={120}
                required
                placeholder="For example: Sales Outreach Specialist"
                disabled={orgReady && Boolean(prism && (archived || prism.is_chief_of_staff))}
                value={form.role}
                onChange={(event) => onRole(event.currentTarget.value)}
              />
            </label>
            <label htmlFor="prism-editor-department">
              Department
              <input
                id="prism-editor-department"
                list="prism-department-options"
                maxLength={100}
                required
                placeholder="For example: Sales"
                disabled={orgReady && archived}
                readOnly={chief}
                value={form.department}
                onChange={(event) => set("department", event.currentTarget.value)}
              />
            </label>
            <datalist id="prism-department-options">
              {(org?.departments || []).map((department) => (
                <option key={department} value={department} />
              ))}
            </datalist>
            <label htmlFor="prism-editor-reports-to">
              Reports to
              <select
                id="prism-editor-reports-to"
                required={!chief}
                disabled={!orgReady || chief || archived}
                value={form.reportsTo}
                onChange={(event) => set("reportsTo", event.currentTarget.value)}
              >
                {!org ? (
                  <option value="">Loading your team…</option>
                ) : (
                  <>
                    {ownerOption ? (
                      <option value="" data-owner-option="true">
                        {`${org.owner_name} · You`}
                      </option>
                    ) : null}
                    <option value="">Choose a Prism</option>
                    {members.map((manager) => (
                      <option key={manager.id} value={manager.id}>
                        {`${manager.name}${manager.is_chief_of_staff && manager.name.trim().toLowerCase() !== "chief of staff" ? " · Chief of Staff" : ""}`}
                      </option>
                    ))}
                  </>
                )}
              </select>
            </label>
          </div>
        </div>
        <div className="editor-main">
          <div id="prism-editor-ai" className="job-description-bar" hidden={!oneStep}>
            <button id="prism-editor-generate" className="button ghost ai" type="button" disabled={!ready || writing} onClick={() => void generate()}>
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" />
              </svg>
              <span>{writing ? "Writing a job description…" : form.description.trim() ? "Regenerate with AI" : "Generate with AI"}</span>
            </button>
            <span id="prism-editor-ai-note" className="panel-note">
              {ready ? "Uses the name, role and anything you already wrote." : "Fill in name and role first."}
            </span>
          </div>
          <label htmlFor="prism-editor-description">
            <span id="prism-editor-description-label">{oneStep && creating ? "What does this Prism do?" : "What is this Prism responsible for?"}</span>
            <textarea
              id="prism-editor-description"
              rows={5}
              maxLength={8000}
              required
              placeholder="For example: Keep me updated on important work across Microsoft Teams in a friendly, concise tone."
              disabled={archived}
              value={form.description}
              onChange={(event) => set("description", event.currentTarget.value)}
            />
          </label>
          <div id="prism-editor-work" className="prism-work-fields" hidden={workHidden}>
            <fieldset id="prism-editor-uses" className="prism-fieldset" hidden={qa}>
              <legend>What can it use?</legend>
              <label className="check-row">
                <input type="checkbox" defaultChecked disabled />
                <span>
                  Web browsing <em>its own browser, always on</em>
                </span>
              </label>
              <label className="check-row">
                <input id="prism-cap-files" type="checkbox" checked={form.capFiles} onChange={(event) => set("capFiles", event.currentTarget.checked)} />
                <span>
                  Files and reports <em>CSV and documents it makes for you</em>
                </span>
              </label>
              <label className="check-row">
                <input
                  id="prism-cap-teams"
                  type="checkbox"
                  checked={form.capTeams}
                  disabled={session.templateRole === "executive_assistant"}
                  onChange={(event) => set("capTeams", event.currentTarget.checked)}
                />
                <span>
                  Microsoft Teams <em>read your chats, draft messages for your approval</em>
                </span>
              </label>
              <label className="check-row is-muted">
                <input type="checkbox" disabled />
                <span>
                  Outlook email <em>coming soon</em>
                </span>
              </label>
            </fieldset>
            <fieldset className="prism-fieldset">
              <legend>Signing in to websites</legend>
              <label className="check-row">
                <input type="radio" name="prism-logins" value="never" checked={form.logins === "never"} onChange={() => set("logins", "never")} />
                <span>
                  Never sign in <em>public pages only</em>
                </span>
              </label>
              <label className="check-row">
                <input type="radio" name="prism-logins" value="ask" checked={form.logins === "ask"} onChange={() => set("logins", "ask")} />
                <span>
                  Sign in when needed <em>with logins I give in the chat, kept encrypted</em>
                </span>
              </label>
            </fieldset>
            <label id="prism-editor-how-field" htmlFor="prism-editor-how" hidden={howHidden}>
              How I'll work
              <textarea id="prism-editor-how" rows={6} maxLength={6000} value={form.how} onChange={(event) => set("how", event.currentTarget.value)} />
            </label>
          </div>
        </div>
        <p id="prism-editor-error" className="inline-error" role="alert" hidden={!error}>
          {error}
        </p>
        <div className="dialog-actions">
          <button id="prism-editor-back" className="button secondary" type="button" hidden onClick={() => {}}>
            Back
          </button>
          <button id="prism-editor-cancel" className="button secondary" type="button" onClick={close}>
            Cancel
          </button>
          <button id="prism-editor-submit" className="button" type="submit" disabled={busy || archived || !orgReady || orgFailed}>
            {creating ? "Create prism" : archived ? "Close" : "Save changes"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
