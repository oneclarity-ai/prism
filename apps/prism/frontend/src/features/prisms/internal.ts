import { createContext, useContext, type RefObject } from "react";
import type { MonitoringApi } from "./monitoring";
import type { PrismUpdateSummary } from "./PrismsContext";
import type { Prism } from "./types";

export interface PageCommands {
  openCreate: () => void;
  openEditor: (prism: Prism) => void;
  openTrigger: () => void;
  openNotify: () => void;
  openHealth: () => void;
}

/** Everything the directory's own components (sidebar, page, dialogs) share; not part of the public PrismsApi. */
export interface PrismsInternal {
  prisms: Prism[];
  loading: boolean;
  selectedId: string | null;
  selectedPrism: Prism | undefined;
  summaries: ReadonlyMap<string, PrismUpdateSummary>;
  archivedPressed: boolean;
  /** Bumped by every selectPrism call (even for the same Prism): the page restarts that Prism's conversation. */
  selectionNonce: number;
  /** Bumped after every completed list load (old `loadPrisms` tail). */
  loadTick: number;
  prismsRef: RefObject<Prism[]>;
  selectedRef: RefObject<string | null>;
  monitoring: MonitoringApi;
  loadPrisms: () => Promise<void>;
  toggleArchived: () => void;
  openPrismView: (prism: Prism) => void;
  selectPrism: (id: string) => void;
  archivePrism: (prism: Prism, alreadyConfirmed?: boolean) => Promise<void>;
  /** Replace a Prism in the list; `render: false` skips the sidebar/route re-sync (old code assigned state silently). */
  replacePrism: (prism: Prism, options?: { render?: boolean }) => void;
  addAndSelect: (prism: Prism) => void;
  registerCommands: (commands: PageCommands) => () => void;
  commands: RefObject<Partial<PageCommands>>;
}

export const PrismsInternalContext = createContext<PrismsInternal | null>(null);

export function usePrismsInternal(): PrismsInternal {
  const value = useContext(PrismsInternalContext);
  if (!value) throw new Error("Prism directory components must be rendered inside <PrismsProvider>");
  return value;
}
