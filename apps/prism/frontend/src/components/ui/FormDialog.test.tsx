import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { installDialogPolyfill, pressEscape } from "@/test/dialog";
import { FormDialogProvider, useFormDialog, type FieldSpec, type FormValues } from "./index";

beforeAll(installDialogPolyfill);

const fields: FieldSpec[] = [
  { name: "title", label: "Title", required: true, maxLength: 20, value: "Initial", placeholder: "Name it", hint: "Short please" },
  { name: "notes", label: "Notes", type: "textarea", value: "n1" },
  { name: "limit", label: "Limit", type: "number", min: 1, value: 5 },
  { name: "env", label: "Environment", options: [["dev", "Dev"], ["prod", "Prod"]], value: "prod" },
  { name: "secret", label: "Secret", type: "password" },
  { name: "url", label: "URL", type: "url" },
];

function Harness(props: {
  onSave?: (values: FormValues) => void | Promise<void>;
  fields?: FieldSpec[];
  options?: { submit?: string; description?: string };
  onOpen?: (close: () => void) => void;
}) {
  const { openFormDialog } = useFormDialog();
  return (
    <button
      onClick={() => {
        const close = openFormDialog("Edit thing", props.fields ?? fields, props.onSave ?? (() => {}), props.options);
        props.onOpen?.(close);
      }}
    >
      open
    </button>
  );
}

const setup = (props: Parameters<typeof Harness>[0] = {}) => {
  render(
    <FormDialogProvider>
      <Harness {...props} />
    </FormDialogProvider>,
  );
  return userEvent.setup();
};
const dialog = () => document.body.querySelector("dialog.workspace-dialog") as HTMLDialogElement | null;

describe("FormDialog", () => {
  it("renders the frozen DOM into document.body and opens modally", async () => {
    const user = setup({ options: { submit: "Add", description: "Intro text" } });
    expect(dialog()).toBeNull();
    await user.click(screen.getByText("open"));
    const d = dialog() as HTMLDialogElement;
    expect(d.parentElement).toBe(document.body);
    expect(d.open).toBe(true);
    expect(d.querySelector("form.workspace-form > .workspace-dialog-heading > h2")).toHaveTextContent("Edit thing");
    const close = d.querySelector(".workspace-dialog-heading button.icon-button") as HTMLButtonElement;
    expect(close.getAttribute("aria-label")).toBe("Close");
    expect(d.querySelector("form > p.panel-note")).toHaveTextContent("Intro text");
    expect(d.querySelectorAll("label.workspace-form-field")).toHaveLength(6);
    expect(d.querySelector("p.inline-error")).toHaveAttribute("role", "alert");
    const footer = d.querySelector(".workspace-form-footer") as HTMLElement;
    expect([...footer.children].map((c) => c.textContent)).toEqual(["Cancel", "Add"]);
    expect(footer.lastElementChild).toHaveAttribute("type", "submit");
    expect(footer.lastElementChild).toHaveClass("button");
  });

  it("maps field specs to controls", async () => {
    const user = setup();
    await user.click(screen.getByText("open"));
    const title = screen.getByLabelText(/Title/) as HTMLInputElement;
    expect(title).toMatchObject({ type: "text", name: "title", required: true, maxLength: 20, value: "Initial", placeholder: "Name it" });
    expect(screen.getByText("Short please")).toHaveClass("panel-note");
    const notes = screen.getByLabelText("Notes") as HTMLTextAreaElement;
    expect(notes.tagName).toBe("TEXTAREA");
    expect(notes.value).toBe("n1");
    const limit = screen.getByLabelText("Limit") as HTMLInputElement;
    expect(limit).toMatchObject({ type: "number", min: "1", step: "any", value: "5" });
    const env = screen.getByLabelText("Environment") as HTMLSelectElement;
    expect(env.tagName).toBe("SELECT");
    expect(env.value).toBe("prod");
    expect([...env.options].map((o) => o.textContent)).toEqual(["Dev", "Prod"]);
    const secret = screen.getByLabelText("Secret") as HTMLInputElement;
    expect(secret.type).toBe("password");
    expect(secret.autocomplete).toBe("new-password");
    expect((screen.getByLabelText("URL") as HTMLInputElement).type).toBe("url");
  });

  it("submits current values and closes (removing the dialog)", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const user = setup({ onSave });
    await user.click(screen.getByText("open"));
    await user.clear(screen.getByLabelText(/Title/));
    await user.type(screen.getByLabelText(/Title/), "Hello");
    await user.selectOptions(screen.getByLabelText("Environment"), "dev");
    await user.type(screen.getByLabelText("Secret"), "pw");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(dialog()).toBeNull());
    expect(onSave).toHaveBeenCalledOnce();
    expect(onSave).toHaveBeenCalledWith({ title: "Hello", notes: "n1", limit: "5", env: "dev", secret: "pw", url: "" });
  });

  it("blocks submit when a required field is empty", async () => {
    const onSave = vi.fn();
    const user = setup({ onSave });
    await user.click(screen.getByText("open"));
    await user.clear(screen.getByLabelText(/Title/));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(dialog()?.open).toBe(true);
  });

  it("shows the error, stays open and re-enables buttons when save fails", async () => {
    const onSave = vi.fn().mockRejectedValue(new Error("Server said no"));
    const user = setup({ onSave });
    await user.click(screen.getByText("open"));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Server said no");
    expect(dialog()?.open).toBe(true);
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
  });

  it("disables buttons and ignores Escape while saving", async () => {
    let finish: () => void = () => {};
    const onSave = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    const user = setup({ onSave });
    await user.click(screen.getByText("open"));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    act(() => pressEscape(dialog() as HTMLDialogElement));
    expect(dialog()?.open).toBe(true);
    finish();
    await waitFor(() => expect(dialog()).toBeNull());
  });

  it("cancel button, close button and Escape all remove the dialog without saving", async () => {
    const onSave = vi.fn();
    const user = setup({ onSave });
    await user.click(screen.getByText("open"));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(dialog()).toBeNull();
    await user.click(screen.getByText("open"));
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(dialog()).toBeNull();
    await user.click(screen.getByText("open"));
    act(() => pressEscape(dialog() as HTMLDialogElement));
    expect(dialog()).toBeNull();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("returns a close function", async () => {
    let close: () => void = () => {};
    const user = setup({ onOpen: (fn) => { close = fn; } });
    await user.click(screen.getByText("open"));
    expect(dialog()).not.toBeNull();
    act(() => close());
    expect(dialog()).toBeNull();
  });

  it("throws outside the provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Harness />)).toThrow(/FormDialogProvider/);
    spy.mockRestore();
  });
});
