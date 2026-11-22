import { useState } from "react";
import { useBusEvent } from "@/lib/events";
import { PrismPeopleScope, type PrismPeopleScopeProps } from "./PrismPeopleScope";

/**
 * Inner content of the drawer's `#prism-people-root`: fills in when bus `people-open` fires
 * (old people-directory.js `openPrismPeople`). No props; the chat keeps the wrapper element.
 */
export function PeoplePanel() {
  const [target, setTarget] = useState<PrismPeopleScopeProps | null>(null);
  useBusEvent("people-open", (detail) => setTarget({ prismId: detail.prismId, prismName: detail.prismName }));
  return target ? <PrismPeopleScope key={target.prismId} prismId={target.prismId} prismName={target.prismName} /> : null;
}
