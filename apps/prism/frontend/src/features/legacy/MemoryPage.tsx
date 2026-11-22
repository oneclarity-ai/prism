import { useState, type FormEvent } from "react";
import { agentApi, errorMessage } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import type { Schema } from "@/types";
import { dateTime, factText } from "./format";
import { useLegacyData } from "./LegacyDataProvider";
import { Item, ListBox } from "./parts";
import type { MemoryEpisode } from "./types";

interface ConsolidateResult {
  processed: number;
  facts: number;
  episodes: number;
  relations: number;
}

const PREVIEW_IDLE = "Choose a team member to see their limited working context.";

function SearchResults({ results }: { results: Schema<"MemorySearchRead"> }) {
  const facts = results.facts || [];
  const episodes = (results.episodes || []) as unknown as MemoryEpisode[];
  if (!facts.length && !episodes.length) {
    return <p className="memory-search-empty">Nothing matched that search yet.</p>;
  }
  return (
    <>
      {facts.length ? (
        <div>
          <strong>Facts</strong>
          {facts.map((fact) => (
            <p key={fact.id}>{factText(fact)}</p>
          ))}
        </div>
      ) : null}
      {episodes.length ? (
        <div>
          <strong>Past situations</strong>
          {episodes.map((episode, index) => (
            <p key={episode.id ?? index}>
              {episode.title}
              <span>{episode.summary}</span>
            </p>
          ))}
        </div>
      ) : null}
    </>
  );
}

export function MemoryPage() {
  const { setStatus } = useApp();
  const { data, loaded, reload } = useLegacyData();
  const [consolidating, setConsolidating] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Schema<"MemorySearchRead"> | null>(null);
  const [employeeId, setEmployeeId] = useState("");
  const [preview, setPreview] = useState(PREVIEW_IDLE);

  const consolidate = async () => {
    setConsolidating(true);
    try {
      const backfill = await agentApi<Record<string, number>>("/api/v1/memory/backfill", { method: "POST" });
      const result = await agentApi<ConsolidateResult>("/api/v1/memory/consolidate", { method: "POST" });
      const queued = Object.values(backfill).reduce((total, count) => total + count, 0);
      setStatus(
        `Memory updated: ${queued} existing record(s) queued; ${result.processed} event(s) processed, ${result.facts} fact(s), ${result.episodes} situation(s), and ${result.relations} relationship(s) added.`,
      );
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
    } finally {
      setConsolidating(false);
    }
  };

  const search = async (event: FormEvent) => {
    event.preventDefault();
    const text = query.trim();
    if (!text) return;
    try {
      setResults(await agentApi<Schema<"MemorySearchRead">>(`/api/v1/memory/search?q=${encodeURIComponent(text)}&include_history=true`));
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };

  const loadContext = async () => {
    if (!employeeId) return;
    setPreview("Loading context…");
    try {
      const context = await agentApi<Schema<"CompiledMemoryContext">>(`/api/v1/memory/context/${employeeId}`);
      const sections = (
        [
          ["Current work", context.current_work],
          ["Current blockers", context.current_blockers],
          ["Open commitments", context.open_commitments],
          ["Relevant memory", context.relevant_facts],
          ["Past situations", context.relevant_episodes],
          ["Relationships", context.relevant_relations],
        ] as Array<[string, string[] | undefined]>
      ).filter((section): section is [string, string[]] => Boolean(section[1] && section[1].length));
      setPreview(
        sections.length
          ? sections.map(([title, values]) => `${title}\n${values.map((value) => `- ${value}`).join("\n")}`).join("\n\n")
          : "No relevant context is available yet.",
      );
    } catch (error) {
      setPreview("Could not load context.");
      setStatus(errorMessage(error), true);
    }
  };

  return (
    <section className="panel memory-panel">
      <div className="panel-heading">
        <div>
          <h2>Organisational memory</h2>
          <p className="panel-note">
            Operational records stay authoritative. This view shows evidence-backed facts and history derived from them.
          </p>
        </div>
        <button
          id="consolidate-memory-button"
          className="mini-button"
          type="button"
          data-tooltip="Process saved management events into memory now. It does not send a Teams message."
          disabled={consolidating}
          onClick={consolidate}
        >
          Update memory
        </button>
      </div>
      <form id="memory-search-form" className="memory-search-form" onSubmit={search}>
        <label htmlFor="memory-search-input">Search facts and past situations</label>
        <div className="memory-search-row">
          <input id="memory-search-input" placeholder="For example: connector API" value={query} onChange={(event) => setQuery(event.currentTarget.value)} />
          <button className="button secondary" type="submit">
            Search
          </button>
        </div>
      </form>
      <div id="memory-search-results" className="memory-search-results" hidden={!results}>
        {results ? <SearchResults results={results} /> : null}
      </div>
      <div className="memory-grid">
        <section>
          <h3>What Prism currently believes</h3>
          <ListBox
            id="memory-facts-list"
            items={data.memoryFacts}
            empty={loaded ? "No derived facts yet. Use Update memory after management activity is recorded." : "No derived facts yet."}
            render={(fact) => <Item key={fact.id} title={factText(fact)} meta={`${fact.status} · observed ${dateTime(fact.observed_at)}`} />}
          />
        </section>
        <section>
          <h3>Recent situations</h3>
          <ListBox
            id="memory-episodes-list"
            items={data.memoryEpisodes}
            empty="No memory episodes yet."
            render={(episode, index) => (
              <Item key={episode.id ?? index} title={episode.title} meta={`${episode.summary} · ${dateTime(episode.started_at)}`} />
            )}
          />
        </section>
      </div>
      <details className="memory-context-preview">
        <summary>Preview the context given to Prism</summary>
        <div className="memory-context-controls">
          <label htmlFor="memory-employee-select">Team member</label>
          <select id="memory-employee-select" value={employeeId} onChange={(event) => setEmployeeId(event.currentTarget.value)}>
            <option value="">Choose a team member</option>
            {data.employees.map((employee) => (
              <option key={employee.id} value={employee.id}>
                {employee.name}
              </option>
            ))}
          </select>
          <button id="load-memory-context-button" className="mini-button" type="button" onClick={loadContext}>
            Load preview
          </button>
        </div>
        <pre id="memory-context-output" className="memory-context-output">
          {preview}
        </pre>
      </details>
    </section>
  );
}
