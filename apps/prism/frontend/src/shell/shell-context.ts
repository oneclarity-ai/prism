import { createContext, useContext } from "react";
import type { AskDialogOptions, PageHeading } from "@/lib/app-context";

export interface ToastState {
  message: string;
  isError: boolean;
  show: boolean;
}

export interface ConfirmRequest {
  options: AskDialogOptions;
  resolve: (value: true | string | null) => void;
}

/** Shell-only state (layout chrome); features use `useApp()` instead. */
export interface ShellState {
  /** `data-view` of #app: the active tab, or "route-error". */
  view: string;
  heading: PageHeading | null;
  routeError: string | null;
  refreshing: boolean;
  toast: ToastState;
  confirmRequest: ConfirmRequest | null;
  clearConfirm: () => void;
  sidebarCollapsed: boolean;
  sidebarOpenNarrow: boolean;
  toggleSidebar: (open: boolean) => void;
  /** Changes whenever the profile menu should close (tab switch, settings open). */
  profileMenuResetKey: number;
  setPageActionsRoot: (element: HTMLElement | null) => void;
  singleExecutive: boolean;
}

export const ShellContext = createContext<ShellState | null>(null);

export function useShell(): ShellState {
  const value = useContext(ShellContext);
  if (!value) throw new Error("useShell must be used inside <AppProvider>");
  return value;
}
