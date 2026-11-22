import { createContext, useContext } from "react";
import type { PrismLike } from "@/lib/events";

/** Old `data-prism-action` ids: rows of the chat's settings drawer trigger the Prism directory's own actions. */
export type PrismAction =
  | "prism-policy-button"
  | "prism-trigger-button"
  | "prism-sync-button"
  | "prism-notify-button"
  | "prism-health-button";

/** Unread Teams updates of one Prism (`/api/v2/prisms/updates/summary` row). */
export interface PrismUpdateSummary {
  prism_id: string;
  unread: number;
  urgent_unread: number;
  latest_unread_at?: string | null;
}

/**
 * Shared Prism list (replaces the old `prism:list` event). Provider implemented by the Prism directory
 * feature (features/prisms); everything else only reads it.
 */
export interface PrismsApi {
  prisms: PrismLike[];
  loading: boolean;
  selectedId: string | null;
  reload: () => Promise<void>;
  /** Unread-update summaries by Prism id (same data as the bus event `updates`). */
  summaries?: ReadonlyMap<string, PrismUpdateSummary>;
  /** Run a Prism directory action (what clicking the old hidden `#prism-*-button` did). No-op before PrismsPage mounts. */
  runAction?: (action: PrismAction) => void;
}

export const PrismsContext = createContext<PrismsApi>({ prisms: [], loading: false, selectedId: null, reload: async () => {} });
export const usePrisms = (): PrismsApi => useContext(PrismsContext);
