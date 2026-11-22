/** jsdom has no HTMLDialogElement.showModal/close; install a minimal stand-in (call once, e.g. in beforeAll). */
export function installDialogPolyfill(): void {
  const proto = HTMLDialogElement.prototype;
  proto.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  proto.close = function close(this: HTMLDialogElement, returnValue?: string) {
    if (returnValue !== undefined) this.returnValue = returnValue;
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}

/** Simulate the Escape key: fire a cancelable `cancel`, then close unless it was prevented. */
export function pressEscape(dialog: HTMLDialogElement): void {
  const event = new Event("cancel", { cancelable: true });
  dialog.dispatchEvent(event);
  if (!event.defaultPrevented) dialog.close();
}
