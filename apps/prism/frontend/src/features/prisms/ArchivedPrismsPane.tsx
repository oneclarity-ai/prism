import { useCallback, useEffect, useRef, useState } from "react";
import { agentApi, errorMessage } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { emit } from "@/lib/events";
import { isArchived } from "./helpers";
import type { Prism } from "./types";

/**
 * Settings > Archived Prisms body: the explanatory note and `#archived-prisms`. The section's `<h2 class="settings-title">`
 * stays with the settings dialog.
 */
export function ArchivedPrismsPane() {
  const { setStatus, askDialog, settings } = useApp();
  const [prisms, setPrisms] = useState<Prism[] | null>(null);
  const alive = useRef(true);

  const load = useCallback(async () => {
    try {
      const rows = (await agentApi<Prism[]>("/api/v2/prisms?include_archived=true")).filter(isArchived);
      if (alive.current) setPrisms(rows);
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  }, [setStatus]);

  useEffect(() => {
    alive.current = true;
    void load();
    return () => {
      alive.current = false;
    };
  }, [load]);

  // The old pane reloaded whenever Settings or its Archived section was opened.
  const visible = settings.isOpen && settings.section === "archived";
  const wasVisible = useRef(visible);
  useEffect(() => {
    if (visible && !wasVisible.current) void load();
    wasVisible.current = visible;
  }, [visible, load]);

  const remove = async (prism: Prism) => {
    const confirmed = await askDialog({
      title: `Delete ${prism.name}?`,
      message: "This removes the Prism, its chats and its saved logins for good. It cannot be undone.",
      confirmLabel: "Delete Prism",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await agentApi(`/api/v2/prisms/${prism.id}`, { method: "DELETE" });
      setStatus(`${prism.name} deleted.`);
      emit("prisms-changed");
      await load();
    } catch (error) {
      setStatus(errorMessage(error), true);
    }
  };

  const empty = !prisms?.length;
  return (
    <>
      <p className="panel-note">Archived Prisms are hidden from your list. Deleting one removes it, its chats and its saved logins for good.</p>
      <div id="archived-prisms" className={`brain-list${empty ? " empty-state" : ""}`}>
        {prisms === null || !prisms.length
          ? "No archived Prisms."
          : prisms.map((prism) => (
              <article className="brain-entry" key={prism.id}>
                <div className="brain-entry-text">
                  <strong>{prism.name}</strong>
                  <p>{prism.description}</p>
                  <span className="brain-entry-meta">{`Archived ${new Date(prism.updated_at).toLocaleDateString()}`}</span>
                </div>
                <div className="brain-entry-actions">
                  <button className="mini-button" type="button" onClick={() => void remove(prism)}>
                    Delete
                  </button>
                </div>
              </article>
            ))}
      </div>
    </>
  );
}
