/** Public interface of the computers feature (port of qa-tester.js). Imported by the chat feature. */
export {
  checkAvailability,
  computersEnabled,
  focusRun,
  initQa,
  isQaPrism,
  onPrism,
  planRequest,
  setOpen,
  useComputerButton,
  useComputerOpen,
  useComputersEnabled,
  type ComputerButtonState,
} from "./store";
export { renderQaMessage } from "./renderQaMessage";
export { ComputerButton, ComputerPanel } from "./Panel";
export type { ChatMessageLike, ChatScroll, ComputersHost } from "./types";
