import { useEffect, useRef, type RefObject } from "react";

/**
 * Keeps a native `<dialog>` in sync with an `open` flag: showModal() when it turns true, close() when
 * false. Escape and any other close path report back through `onClose`.
 */
export function useModalDialog(ref: RefObject<HTMLDialogElement | null>, open: boolean, onClose: () => void): void {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const openRef = useRef(open);
  openRef.current = open;

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [ref, open]);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    // Only a user-initiated close (Escape...) is reported; our own close() follows `open` already.
    const onNativeClose = () => {
      if (openRef.current) closeRef.current();
    };
    dialog.addEventListener("close", onNativeClose);
    return () => dialog.removeEventListener("close", onNativeClose);
  }, [ref]);
}
