import { useEffect, useRef, useState } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { Avatar } from "./PeoplePane";
import { loadPeople, subtitle, usePeople } from "./people-store";

type Scope = "all" | "selected";

export interface PrismPeopleScopeProps {
  prismId: string;
  prismName: string;
}

/**
 * Per-Prism visibility, for the chat's settings drawer: the inner content of `#prism-people-root`
 * (old `people-open` handling in people-directory.js). Mount it when the drawer's People panel opens.
 */
export function PrismPeopleScope({ prismId, prismName }: PrismPeopleScopeProps) {
  const { setStatus } = useApp();
  const people = usePeople();
  const [scope, setScope] = useState<Scope>("all");
  const [ids, setIds] = useState<ReadonlySet<string>>(new Set());
  const [query, setQuery] = useState("");
  const [ready, setReady] = useState(false);
  const search = useRef<HTMLInputElement>(null);
  const loaded = useRef(people.loaded);
  loaded.current = people.loaded;

  useEffect(() => {
    let cancelled = false;
    setQuery("");
    setReady(false);
    (async () => {
      try {
        const [answer] = await Promise.all([
          agentApi<{ scope: Scope; employee_ids: string[] }>(`/api/v2/prisms/${prismId}/people`),
          loaded.current ? null : loadPeople(),
        ]);
        if (cancelled) return;
        setScope(answer.scope);
        setIds(new Set(answer.employee_ids));
        setReady(true);
      } catch (error) {
        if (!cancelled) setStatus(errorMessage(error), true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [prismId, setStatus]);

  const save = async (nextScope: Scope, nextIds: ReadonlySet<string>) => {
    try {
      await agentApi(`/api/v2/prisms/${prismId}/people`, { method: "PUT", ...jsonBody({ scope: nextScope, employee_ids: [...nextIds] }) });
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };
  const needle = query.trim().toLowerCase();
  const shown = people.list.filter((person) => !needle || `${person.name} ${person.title || ""} ${person.department || ""}`.toLowerCase().includes(needle));
  if (!ready) return null;
  return (
    <>
      <p className="panel-note">{`Choose who ${prismName} knows about. It uses their role and reporting line to write to the right person in the right tone.`}</p>
      <div className="people-scope">
        {(
          [
            ["all", "Everyone Prism knows"],
            ["selected", "Only people I pick"],
          ] as const
        ).map(([value, label]) => (
          <label className="people-scope-option" key={value}>
            <input
              type="radio"
              name="prism-people-scope"
              value={value}
              checked={scope === value}
              onChange={() => {
                setScope(value);
                void save(value, ids);
              }}
            />
            <span>{label}</span>
          </label>
        ))}
      </div>
      {scope === "selected" ? (
        <>
          <input ref={search} type="search" placeholder="Search people" aria-label="Search people" value={query} onChange={(event) => setQuery(event.currentTarget.value)} />
          <div className="people-pick-list">
            {!people.list.length
              ? "No people yet. Refresh from the Teams page first."
              : shown.map((person) => (
                  <label className="people-pick" key={person.id}>
                    <Avatar name={person.name} />
                    <span className="person-copy">
                      <strong>{person.name}</strong>
                      <span className="person-sub">{subtitle(person) || person.relationship}</span>
                    </span>
                    <input
                      type="checkbox"
                      className="toggle"
                      role="switch"
                      checked={ids.has(person.id)}
                      onChange={(event) => {
                        const next = new Set(ids);
                        if (event.currentTarget.checked) next.add(person.id);
                        else next.delete(person.id);
                        setIds(next);
                        void save(scope, next);
                      }}
                    />
                  </label>
                ))}
          </div>
        </>
      ) : null}
    </>
  );
}
