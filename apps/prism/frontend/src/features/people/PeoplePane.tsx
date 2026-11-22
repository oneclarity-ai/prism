import { useEffect, useState } from "react";
import { agentApi, errorMessage } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PersonEditDialog } from "./PersonEditDialog";
import { avatarTone, everyone, initials, loadPeople, subtitle, usePeople, type Person } from "./people-store";

const RANK = ["Your manager", "Above you", "Peer", "In your team", "Reports to you", "Colleague"];
type ViewMode = "list" | "tree";

export function Avatar({ name, large = false }: { name: string; large?: boolean }) {
  return <span className={`avatar ${avatarTone(name)}${large ? " large" : ""}`}>{initials(name)}</span>;
}

/** Long role descriptions show three lines and open on demand, so the page stays compact. */
function Clamped({ className, text }: { className: string; text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="people-clamp">
      <p className={`${className}${open ? "" : " clamped"}`}>{text}</p>
      <button type="button" className="people-clamp-toggle" hidden={text.length < 220} aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Show less" : "Show more"}
      </button>
    </div>
  );
}

function MeCard({ me, onEdit }: { me: Person | null; onEdit: (person: Person) => void }) {
  if (!me) {
    return <p className="people-me-empty">Prism doesn't know who you are yet. Refresh from Teams to pull your name, role and manager, then add what you do.</p>;
  }
  const facts = [me.manager_name ? `Reports to ${me.manager_name}` : "No manager set", `${me.direct_report_count} direct ${me.direct_report_count === 1 ? "report" : "reports"}`];
  return (
    <>
      <div className="people-me-head">
        <Avatar name={me.name} large />
        <div className="people-me-copy">
          <span className="people-me-eyebrow">You</span>
          <strong className="people-me-name">{me.name}</strong>
          <span className="people-me-sub">{subtitle(me) || "Add your role"}</span>
          <span className="people-me-facts">{facts.join(" · ")}</span>
        </div>
        <button type="button" className="mini-button" onClick={() => onEdit(me)}>
          Edit about me
        </button>
      </div>
      {me.responsibilities ? <Clamped className="people-me-text" text={me.responsibilities} /> : null}
      {me.notes ? <Clamped className="people-me-text muted" text={me.notes} /> : null}
      {!me.responsibilities ? <p className="people-me-hint">Tell Prism what you're responsible for so every Prism understands your role.</p> : null}
    </>
  );
}

function PersonRow({ person, className = "", onEdit }: { person: Person; className?: string; onEdit: (person: Person) => void }) {
  const line = [person.manager_name ? `Reports to ${person.manager_name}` : "", person.responsibilities || ""].filter(Boolean).join(" · ");
  return (
    <button type="button" className={`person-row${className ? ` ${className}` : ""}`} onClick={() => onEdit(person)}>
      <Avatar name={person.name} />
      <span className="person-copy">
        <strong>{person.name}</strong>
        <span className="person-sub">{subtitle(person) || "No role on record"}</span>
        {line ? <span className="person-line">{line}</span> : null}
      </span>
      <span className="person-tags">
        {person.is_me ? <span className="person-tag">You</span> : !person.in_chats && !person.in_team ? <span className="person-tag faint">Org link</span> : null}
        {person.overrides.length ? <span className="person-tag">Edited</span> : null}
      </span>
    </button>
  );
}

function Branch({ parent, depth, children, onEdit }: { parent: string | null; depth: number; children: Map<string | null, Person[]>; onEdit: (person: Person) => void }) {
  return (
    <ul className="org-tree">
      {(children.get(parent) ?? []).map((person) => (
        <li key={person.id}>
          <PersonRow person={person} className={person.is_me ? "is-me" : ""} onEdit={onEdit} />
          {depth < 12 && children.has(person.id) ? <Branch parent={person.id} depth={depth + 1} children={children} onEdit={onEdit} /> : null}
        </li>
      ))}
    </ul>
  );
}

function matches(person: Person, query: string): boolean {
  const needle = query.trim().toLowerCase();
  return !needle || [person.name, person.title, person.department, person.manager_name, person.responsibilities].some((value) => String(value || "").toLowerCase().includes(needle));
}

/** Settings > People: the `teams` section body plus `#person-edit-dialog`. */
export function PeoplePane() {
  const app = useApp();
  const { setStatus, settings } = app;
  const people = usePeople();
  const [mode, setMode] = useState<ViewMode>("list");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Person | null>(null);
  const [syncing, setSyncing] = useState(false);

  const load = async () => {
    try {
      await loadPeople();
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };
  // Loaded on start, whenever Settings opens and when the People section is picked (old tab/subtab hooks).
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (settings.isOpen) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.isOpen, settings.section === "teams"]);

  const sync = async () => {
    setSyncing(true);
    try {
      const result = await agentApi<{ me_found: boolean; people: number }>("/api/v1/people/sync", { method: "POST" });
      setStatus(
        result.me_found
          ? `Found ${result.people} ${result.people === 1 ? "person" : "people"} in your chats and their managers.`
          : "Synced, but Prism could not find your own profile in the directory.",
      );
      await loadPeople();
      app.refresh();
    } catch (error) {
      setStatus(errorMessage(error), true);
    } finally {
      setSyncing(false);
    }
  };

  const visible = everyone(people).filter((person) => matches(person, query));
  let list;
  if (!people.list.length) {
    list = <div id="people-list" className="people-list empty-state">No people yet. Refresh from Teams to pull your team and the people you chat with.</div>;
  } else if (!visible.length) {
    list = <div id="people-list" className="people-list empty-state">Nobody matches that search.</div>;
  } else {
    let content;
    if (mode === "tree") {
      const ids = new Set(visible.map((person) => person.id));
      const children = new Map<string | null, Person[]>();
      visible.forEach((person) => {
        const parent = person.manager_id && ids.has(person.manager_id) ? person.manager_id : null;
        children.set(parent, [...(children.get(parent) ?? []), person]);
      });
      content = <Branch parent={null} depth={0} children={children} onEdit={setEditing} />;
    } else {
      const groups = new Map<string, Person[]>();
      visible.filter((person) => !person.is_me).forEach((person) => groups.set(person.relationship, [...(groups.get(person.relationship) ?? []), person]));
      content = [...groups.keys()]
        .sort((a, b) => RANK.indexOf(a) - RANK.indexOf(b))
        .map((name) => (
          <section className="people-group" key={name}>
            <h3 className="people-group-title">
              {name}
              <span className="people-group-count">{String(groups.get(name)?.length)}</span>
            </h3>
            {groups.get(name)?.map((person) => (
              <PersonRow key={person.id} person={person} onEdit={setEditing} />
            ))}
          </section>
        ));
    }
    list = (
      <div id="people-list" className="people-list">
        {content}
        {people.syncedAt ? <p className="people-synced">{`Last refreshed ${new Date(people.syncedAt).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}`}</p> : null}
      </div>
    );
  }

  return (
    <>
      <h2 className="settings-title">People</h2>
      <div className="settings-subhead">
        <h3 className="brain-heading">People</h3>
        <button
          id="people-sync-button"
          className="mini-button"
          type="button"
          data-tooltip="Read your Teams chats and each person's manager from Microsoft. Your own edits are kept."
          disabled={syncing}
          onClick={() => void sync()}
        >
          {syncing ? "Reading Teams…" : "Refresh from Teams"}
        </button>
      </div>
      <p className="panel-note">
        Your reporting team and the people in your Teams chats, who they report to, and what they do. Prism uses this to know who is who. Nobody is messaged when you refresh.
      </p>
      <div id="people-me" className="people-me">
        <MeCard me={people.me} onEdit={setEditing} />
      </div>
      <div className="people-toolbar">
        <input id="people-search" type="search" placeholder="Search people" aria-label="Search people" autoComplete="off" value={query} onChange={(event) => setQuery(event.currentTarget.value)} />
        <div className="segmented" role="group" aria-label="View">
          <button type="button" data-people-view="list" aria-pressed={mode === "list"} onClick={() => setMode("list")}>
            List
          </button>
          <button type="button" data-people-view="tree" aria-pressed={mode === "tree"} onClick={() => setMode("tree")}>
            Org chart
          </button>
        </div>
      </div>
      {list}
      <PersonEditDialog person={editing} onClose={() => setEditing(null)} />
    </>
  );
}
