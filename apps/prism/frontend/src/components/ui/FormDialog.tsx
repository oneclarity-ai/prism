import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { errorMessage } from "@/lib/api";
import { Button } from "./Button";

export interface FieldSpec {
  name: string;
  label: string;
  /** Input type (`text` default, `number`, `url`, `password`, ...) or `textarea`. Ignored when `options` is set. */
  type?: string;
  /** Initial value; null/undefined become an empty string. */
  value?: string | number | null;
  required?: boolean;
  /** Renders a `<select>` of `[value, label]` pairs. */
  options?: ReadonlyArray<readonly [value: string, label: string]>;
  maxLength?: number;
  min?: number | string;
  /** Number inputs only; defaults to `"any"`. */
  step?: number | string;
  placeholder?: string;
  /** Small note rendered under the control. */
  hint?: string;
}

export type FormValues = Record<string, string>;

export interface FormDialogOptions {
  /** Submit button label (default `Save`). */
  submit?: string;
  /** Intro paragraph under the heading. */
  description?: string;
}

export type OpenFormDialog = (
  title: string,
  fields: readonly FieldSpec[],
  onSave: (values: FormValues) => void | Promise<void>,
  options?: FormDialogOptions,
) => () => void;

interface DialogEntry {
  id: number;
  title: string;
  fields: readonly FieldSpec[];
  onSave: (values: FormValues) => void | Promise<void>;
  options: FormDialogOptions;
}

type Control = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

interface FormDialogViewProps extends Omit<DialogEntry, "id"> {
  onClosed: () => void;
  registerClose: (close: () => void) => void;
}

// Native <dialog> keeps focus trapped and restores it to the originating control.
function FormDialogView({ title, fields, onSave, options, onClosed, registerClose }: FormDialogViewProps) {
  const { submit = "Save", description = "" } = options;
  const dialogRef = useRef<HTMLDialogElement>(null);
  const controls = useRef(new Map<string, Control>());
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    registerClose(() => dialog.close());
  }, [registerClose]);

  const submitForm = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    const values: FormValues = Object.fromEntries([...controls.current].map(([key, input]) => [key, input.value]));
    try {
      await onSave(values);
      dialogRef.current?.close();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const handleClose = () => {
    for (const input of controls.current.values()) if (input.type === "password") input.value = "";
    onClosed();
  };

  return (
    <dialog
      ref={dialogRef}
      className="workspace-dialog"
      onCancel={(event) => {
        if (busyRef.current) event.preventDefault();
      }}
      onClose={handleClose}
    >
      <form className="workspace-form" onSubmit={submitForm}>
        <div className="workspace-dialog-heading">
          <h2>{title}</h2>
          <Button glyph="x" className="icon-button" title="Close" onClick={() => dialogRef.current?.close()} />
        </div>
        {description ? <p className="panel-note">{description}</p> : null}
        {fields.map((spec) => {
          const setRef = (node: Control | null) => {
            if (node) controls.current.set(spec.name, node);
            else controls.current.delete(spec.name);
          };
          const initial = spec.value ?? "";
          return (
            <label className="workspace-form-field" key={spec.name}>
              <span>{spec.label}</span>
              {spec.options ? (
                <select ref={setRef} name={spec.name} defaultValue={String(initial)} required={Boolean(spec.required)}>
                  {spec.options.map(([value, text]) => (
                    <option key={value} value={value}>
                      {text}
                    </option>
                  ))}
                </select>
              ) : spec.type === "textarea" ? (
                <textarea
                  ref={setRef}
                  name={spec.name}
                  defaultValue={String(initial)}
                  required={Boolean(spec.required)}
                  maxLength={spec.maxLength || undefined}
                  placeholder={spec.placeholder || undefined}
                />
              ) : (
                <input
                  ref={setRef}
                  name={spec.name}
                  type={spec.type || "text"}
                  defaultValue={String(initial)}
                  required={Boolean(spec.required)}
                  maxLength={spec.maxLength || undefined}
                  min={spec.min}
                  step={spec.type === "number" ? spec.step || "any" : undefined}
                  autoComplete={spec.type === "password" ? "new-password" : undefined}
                  placeholder={spec.placeholder || undefined}
                />
              )}
              {spec.hint ? <small className="panel-note">{spec.hint}</small> : null}
            </label>
          );
        })}
        <p className="inline-error" role="alert">
          {error}
        </p>
        <div className="workspace-form-footer">
          <Button text="Cancel" disabled={busy} onClick={() => dialogRef.current?.close()} />
          <button className="button" type="submit" disabled={busy}>
            {submit}
          </button>
        </div>
      </form>
    </dialog>
  );
}

const FormDialogContext = createContext<OpenFormDialog | null>(null);

/** Mount once near the root. Dialogs are portalled to `document.body` and unmounted when they close. */
export function FormDialogProvider({ children }: { children?: ReactNode }) {
  const [entries, setEntries] = useState<DialogEntry[]>([]);
  const nextId = useRef(0);
  const closers = useRef(new Map<number, () => void>());

  const open = useCallback<OpenFormDialog>((title, fields, onSave, options = {}) => {
    const id = (nextId.current += 1);
    setEntries((current) => [...current, { id, title, fields, onSave, options }]);
    return () => closers.current.get(id)?.();
  }, []);

  const view = useMemo(
    () =>
      entries.map((entry) => (
        <FormDialogView
          key={entry.id}
          title={entry.title}
          fields={entry.fields}
          onSave={entry.onSave}
          options={entry.options}
          registerClose={(close) => closers.current.set(entry.id, close)}
          onClosed={() => {
            closers.current.delete(entry.id);
            setEntries((current) => current.filter((item) => item.id !== entry.id));
          }}
        />
      )),
    [entries],
  );

  return (
    <FormDialogContext.Provider value={open}>
      {children}
      {createPortal(view, document.body)}
    </FormDialogContext.Provider>
  );
}

/** `openFormDialog(title, fields, onSave, { submit, description })` returns a function that closes the dialog. */
export function useFormDialog(): { openFormDialog: OpenFormDialog } {
  const open = useContext(FormDialogContext);
  if (!open) throw new Error("useFormDialog must be used inside FormDialogProvider");
  return useMemo(() => ({ openFormDialog: open }), [open]);
}
