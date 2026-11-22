import { useEffect, useRef, useState, type FormEvent } from "react";
import { useShell } from "./shell-context";

/** `<dialog id="confirm-dialog">`: promise-based confirm/prompt behind `useApp().askDialog`. */
export function ConfirmDialog() {
  const { confirmRequest, clearConfirm } = useShell();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const ok = useRef<HTMLButtonElement>(null);
  const [value, setValue] = useState("");
  const options = confirmRequest?.options;
  const field = options?.field ?? null;

  useEffect(() => {
    const node = dialog.current;
    if (!confirmRequest || !node) return;
    setValue(confirmRequest.options.field?.value ?? "");
    node.returnValue = "";
    if (!node.open) node.showModal();
    (confirmRequest.options.field ? input.current : ok.current)?.focus();
  }, [confirmRequest]);

  const settle = () => {
    const node = dialog.current;
    if (!confirmRequest || !node) return;
    const confirmed = node.returnValue === "ok";
    const resolve = confirmRequest.resolve;
    clearConfirm();
    resolve(confirmed ? (field ? value : true) : null);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    dialog.current?.close("ok");
  };

  return (
    <dialog id="confirm-dialog" ref={dialog} onClose={settle}>
      <form id="confirm-form" method="dialog" onSubmit={submit}>
        <div>
          <h2 id="confirm-title">{options?.title ?? "Are you sure?"}</h2>
          <p id="confirm-message" hidden={!options?.message}>
            {options?.message ?? ""}
          </p>
        </div>
        <label id="confirm-field" hidden={!field}>
          <span id="confirm-field-label">{field ? field.label : ""}</span>
          <input
            id="confirm-input"
            ref={input}
            autoComplete="off"
            type={field?.type || "text"}
            placeholder={field?.placeholder || ""}
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </label>
        <div className="dialog-actions">
          <button id="confirm-cancel" className="button secondary" type="button" onClick={() => dialog.current?.close("cancel")}>
            Cancel
          </button>
          <button id="confirm-ok" ref={ok} className={`button${options?.danger ? " danger" : ""}`} type="submit" value="ok">
            {options?.confirmLabel ?? "Confirm"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
