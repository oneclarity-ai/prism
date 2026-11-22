import { useState, type ReactNode } from "react";
import { Button, Chip, Empty, Icon, Panel, PrismLogo, SearchField, useFormDialog } from "@/components/ui";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { plainSummary } from "@/lib/format";
import { brainApi, sourceLabel } from "./brain";
import type { BrainEntry } from "./types";

function EntryCard({ entry, actions, byPrism = false }: { entry: BrainEntry; actions: ReactNode; byPrism?: boolean }) {
  return (
    <article className="bn-entry">
      {byPrism ? <PrismLogo colorKey={entry.prism_name || entry.title} className="prism-logo" /> : null}
      <div className="bn-entry-text">
        <strong>{(byPrism && entry.prism_name) || entry.title}</strong>
        <p>{byPrism ? plainSummary(entry.body, 400) : entry.body}</p>
        <div className="bn-entry-meta">
          <Chip tone={entry.source === "chat" ? "blue" : entry.source === "prism" ? "gray" : "green"}>{sourceLabel(entry)}</Chip>
        </div>
      </div>
      <div className="bn-entry-actions">{actions}</div>
    </article>
  );
}

/** Opens the add/edit form. The controller also uses it for the "Add to Brain" page action. */
export function useBrainEditor(reload: () => Promise<void>): (entry: BrainEntry | null) => void {
  const { openFormDialog } = useFormDialog();
  return (entry) =>
    openFormDialog(
      entry ? "Edit knowledge" : "Add to the Brain",
      [
        { name: "title", label: "Title", required: true, maxLength: 200, value: entry?.title, placeholder: "For example: What OneClarity does" },
        { name: "body", label: "What every Prism should know", type: "textarea", required: true, maxLength: 2000, value: entry?.body },
      ],
      async (values) => {
        const saved = await agentApi<BrainEntry>(entry ? `/api/v2/brain/${entry.id}` : "/api/v2/brain", {
          method: entry ? "PATCH" : "POST",
          ...jsonBody(values),
        });
        // Editing a suggestion is approving it.
        if (entry?.status === "proposed") await brainApi.decide(saved, "approve");
        await reload();
      },
      { submit: entry ? "Save" : "Add", description: "Every Prism reads approved entries before it works. Keep it factual and short." },
    );
}

export function BrainPage({ entries, reload, edit }: { entries: readonly BrainEntry[]; reload: () => Promise<void>; edit: (entry: BrainEntry | null) => void }) {
  const { setStatus, askDialog } = useApp();
  const [query, setQuery] = useState("");
  const proposed = entries.filter((entry) => entry.status === "proposed");
  const approved = entries.filter((entry) => entry.status === "approved");
  const facts = approved.filter((entry) => entry.source !== "prism");
  const work = approved.filter((entry) => entry.source === "prism");

  const act = async (task: () => Promise<unknown>) => {
    try {
      await task();
      await reload();
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };
  const remove = async (entry: BrainEntry) => {
    const confirmed = await askDialog({ title: "Remove from the Brain?", message: "Prisms will no longer know this.", confirmLabel: "Remove", danger: true });
    if (confirmed) void act(() => brainApi.remove(entry));
  };

  const needle = query.trim().toLowerCase();
  const shown = facts.filter((entry) => !needle || `${entry.title} ${entry.body}`.toLowerCase().includes(needle));
  const tiles = [
    ["brain", facts.length, "Facts every Prism knows"],
    ["circle-dashed", proposed.length, "Waiting for approval"],
    ["bot", work.length, "Prism work notes"],
  ] as const;

  return (
    <div className="bn-page">
      <div className="bn-stats">
        {tiles.map(([glyph, value, label]) => (
          <div className="bn-stat" key={label}>
            <Icon name={glyph} />
            <div>
              <strong>{value}</strong>
              <span>{label}</span>
            </div>
          </div>
        ))}
      </div>
      {proposed.length ? (
        <Panel title="Waiting for your approval" subtitle="Prisms picked these up from your chats. They are not used until you add them." className="bn-pending">
          <div className="bn-list">
            {proposed.map((entry) => (
              <EntryCard
                key={entry.id}
                entry={entry}
                actions={
                  <>
                    <Button text="Add" glyph="circle-check" className="mini-button primary" onClick={() => void act(() => brainApi.decide(entry, "approve"))} />
                    <Button text="Edit" glyph="pencil" onClick={() => edit(entry)} />
                    <Button text="Dismiss" glyph="x" onClick={() => void act(() => brainApi.decide(entry, "reject"))} />
                  </>
                }
              />
            ))}
          </div>
        </Panel>
      ) : null}
      <Panel
        title="What every Prism knows"
        subtitle="Shared context: your organisation, tone, products, rules."
        action={facts.length > 4 ? <SearchField label="Search the Brain" value={query} onChange={setQuery} /> : null}
      >
        <div className="bn-list">
          {!facts.length ? (
            <Empty title="Nothing yet" description="Add what every Prism should know about your organisation." glyph="brain" />
          ) : !shown.length ? (
            <Empty title="No matches" description="Try a different search." glyph="search" />
          ) : (
            shown.map((entry) => (
              <EntryCard
                key={entry.id}
                entry={entry}
                actions={
                  <>
                    <Button className="icon-button" glyph="pencil" title="Edit" onClick={() => edit(entry)} />
                    <Button className="icon-button" glyph="trash" title="Delete" onClick={() => void remove(entry)} />
                  </>
                }
              />
            ))
          )}
        </div>
      </Panel>
      {work.length ? (
        <Panel title="What Prisms are working on" subtitle="Each Prism leaves a short note so the others stay in step.">
          <div className="bn-list">
            {work.map((entry) => (
              <EntryCard key={entry.id} entry={entry} byPrism actions={<Button className="icon-button" glyph="x" title="Clear note" onClick={() => void remove(entry)} />} />
            ))}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
