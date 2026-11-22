import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { useModalDialog } from "@/features/legacy/useModalDialog";
import { usePrisms } from "@/features/prisms/PrismsContext";
import { agentApi } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { emit, useBusEvent, type PrismLike } from "@/lib/events";
import { setTheme, setUiSize, type UiSize } from "@/lib/prefs";
import { GROUPS, LIMIT, collect, highlightParts, termsOf, type PaletteEnv, type RowKind, type SearchRow } from "./logic";
import type { Schema } from "@/types";

const ICONS: Record<string, ReactNode> = {
  prism: (
    <>
      <path d="M6 3h12l4 6-10 12L2 9l4-6Z" />
      <path d="M2 9h20M9 3l3 6 3-6M12 21 9 9M12 21l3-12" />
    </>
  ),
  chat: <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />,
  page: <path d="M3 11 12 3l9 8M5 10v10h14V10" />,
  setting: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
    </>
  ),
  action: <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" />,
  card: (
    <>
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <path d="M2 10h20" />
    </>
  ),
  list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  play: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="m10 8 6 4-6 4V8Z" />
    </>
  ),
  shield: (
    <>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  bug: <path d="M8 2l1.9 1.9M16 2l-1.9 1.9M9 7.1V6a3 3 0 0 1 6 0v1.1M12 20a6 6 0 0 1-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3a6 6 0 0 1-6 6ZM12 20v-9M6.5 13H2M17.5 13H22" />,
  bot: (
    <>
      <rect x="3" y="11" width="18" height="10" rx="2" />
      <circle cx="12" cy="5" r="2" />
      <path d="M12 7v4M8 16h.01M16 16h.01" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20" />
    </>
  ),
  key: (
    <>
      <circle cx="7.5" cy="15.5" r="4.5" />
      <path d="m10.7 12.3 9.3-9.3M17 6l3 3" />
    </>
  ),
  network: (
    <>
      <rect x="9" y="2" width="6" height="6" rx="1" />
      <rect x="2" y="16" width="6" height="6" rx="1" />
      <rect x="16" y="16" width="6" height="6" rx="1" />
      <path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3M12 12V8" />
    </>
  ),
  chart: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  dash: (
    <>
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </>
  ),
  theme: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3a9 9 0 0 1 0 18Z" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
};

function Highlight({ text, terms }: { text: string; terms: readonly string[] }) {
  const [before, match, after] = highlightParts(text, terms);
  if (match === null) return <>{text}</>;
  return (
    <>
      {before}
      <mark>{match}</mark>
      {after}
    </>
  );
}

type MessageState = "idle" | "loading" | "error" | "done";

export function CommandPalette() {
  const app = useApp();
  const { prisms: sharedPrisms } = usePrisms();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const optionRefs = useRef(new Map<number, HTMLElement>());
  const opener = useRef<Element | null>(null);
  const token = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const scrollToActive = useRef(false);

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<SearchRow[]>([]);
  const [messageState, setMessageState] = useState<MessageState>("idle");
  const [fetchedPrisms, setFetchedPrisms] = useState<PrismLike[]>([]);
  const [active, setActiveState] = useState(0);

  const appRef = useRef(app);
  appRef.current = app;
  const prisms = sharedPrisms.length ? sharedPrisms : fetchedPrisms;

  useModalDialog(dialogRef, open, () => setOpen(false));

  const env: PaletteEnv = useMemo(
    () => ({
      modes: app.modes,
      providerStatus: app.providerStatus,
      microsoft: app.microsoft,
      prisms,
      setActiveTab: (tab) => appRef.current.setActiveTab(tab),
      setSidebarSection: (section) => appRef.current.setSidebarSection(section),
      openSettings: (section) => appRef.current.settings.open(section),
      navigateWorkspace: (page) => emit("workspace-navigate", { page }),
      openPrism: (id) => emit("open-prism", { id }),
      // No bus event exists for this yet; the Prism list owner's button is the only entry point.
      createPrism: () => document.getElementById("prism-create-button")?.click(),
      setTheme,
      setDisplaySize: (value) => setUiSize(value as UiSize),
      refresh: () => appRef.current.refresh(),
    }),
    [app.modes, app.providerStatus, app.microsoft, prisms],
  );

  const terms = termsOf(query.trim());
  const buckets = useMemo(() => collect(query.trim(), env, messages), [query, env, messages]);
  const groups = useMemo(() => {
    let offset = 0;
    return GROUPS.flatMap(([kind, heading]) => {
      const rows = (buckets[kind] || []).slice(0, LIMIT[kind]);
      const pending = kind === "message" && terms.length > 0 && messageState !== "idle" && !rows.length;
      if (!rows.length && !pending) return [];
      const start = offset;
      offset += rows.length;
      return [{ kind, heading, rows, pending, start }];
    });
    // `terms` derives from `query`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buckets, messageState, query]);
  const shown: SearchRow[] = groups.flatMap((group) => group.rows);
  const activeIndex = shown.length ? Math.min(active, shown.length - 1) : -1;

  const setActive = (index: number, scroll: boolean) => {
    scrollToActive.current = scroll;
    setActiveState(index);
  };

  useEffect(() => {
    if (!scrollToActive.current) return;
    scrollToActive.current = false;
    optionRefs.current.get(activeIndex)?.scrollIntoView?.({ block: "nearest" });
  }, [activeIndex]);

  const doOpen = async () => {
    if (open) return;
    opener.current = document.activeElement;
    setQuery("");
    setMessages([]);
    setMessageState("idle");
    setActiveState(0);
    setOpen(true);
    if (!sharedPrisms.length && appRef.current.modes.v22 === true) {
      try {
        setFetchedPrisms(await agentApi<PrismLike[]>("/api/v2/prisms?include_archived=false"));
      } catch {
        /* The list loads with the sidebar. */
      }
    }
  };
  const openRef = useRef(doOpen);
  openRef.current = doOpen;

  useBusEvent("open-search", () => void openRef.current());

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (dialogRef.current?.open) setOpen(false);
        else void openRef.current();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Closing (Escape, backdrop, picking a row): stop pending searches and give focus back to the trigger.
  const wasOpen = useRef(false);
  useEffect(() => {
    if (open) {
      wasOpen.current = true;
      inputRef.current?.focus();
      return;
    }
    if (!wasOpen.current) return;
    wasOpen.current = false;
    clearTimeout(timer.current);
    token.current += 1;
    const handle = setTimeout(() => {
      const trigger = opener.current;
      if ((!document.activeElement || document.activeElement === document.body) && trigger?.isConnected && trigger instanceof HTMLElement) trigger.focus();
    }, 60);
    return () => clearTimeout(handle);
  }, [open]);

  useEffect(() => () => clearTimeout(timer.current), []);

  const searchMessages = async (text: string) => {
    const current = ++token.current;
    if (text.length < 2) {
      setMessages([]);
      setMessageState("idle");
      return;
    }
    setMessageState("loading");
    try {
      const rows = await agentApi<Schema<"PrismSearchResultRead">[]>(`/api/v2/prisms/search?${new URLSearchParams({ q: text })}`);
      if (current !== token.current) return;
      setMessages(
        rows
          .filter((row) => row.kind === "message")
          .map((row) => {
            const by = row.role === "manager" ? "You" : "Prism";
            const when = row.created_at ? new Date(row.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
            return {
              kind: "message" as const,
              label: row.prism_name,
              sub: `${by} · ${when}`,
              snippet: row.snippet,
              run: () => {
                appRef.current.setSidebarSection("chat");
                emit("search-result", {
                  prismId: row.prism_id,
                  message: row.message_id ? { id: row.message_id, created_at: row.created_at } : null,
                });
              },
            };
          }),
      );
      setMessageState("done");
    } catch {
      if (current !== token.current) return;
      setMessages([]);
      setMessageState("error");
    }
    // The old render() after a result also put the selection back on the first row.
    setActiveState(0);
  };

  const onInput = (value: string) => {
    const text = value.trim();
    setQuery(value);
    token.current += 1; // A newer query invalidates an earlier response.
    clearTimeout(timer.current);
    setMessages([]);
    setMessageState(text.length >= 2 ? "loading" : "idle");
    setActiveState(0);
    timer.current = setTimeout(() => void searchMessages(text), 220);
  };

  const activate = (index: number) => {
    const row = shown[index];
    if (!row) return;
    setOpen(false);
    // Let the dialog release focus before the destination moves it.
    setTimeout(() => row.run(), 0);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!shown.length) return;
      setActive((activeIndex + (event.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length, true);
    } else if (event.key === "Home" && event.ctrlKey) {
      event.preventDefault();
      setActive(0, true);
    } else if (event.key === "End" && event.ctrlKey) {
      event.preventDefault();
      setActive(shown.length - 1, true);
    } else if (event.key === "Enter") {
      event.preventDefault();
      activate(activeIndex);
    }
  };

  const onBackdrop = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === event.currentTarget) setOpen(false);
  };

  const heading = (kind: RowKind, text: string) =>
    terms.length || kind === "action" ? text : kind === "prism" ? "Prisms" : kind === "page" ? "Go to" : text;

  return (
    <dialog id="search-dialog" className="search-dialog" aria-label="Search Prism" ref={dialogRef} onClick={onBackdrop}>
      <div className="search-head">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="6" />
          <path d="m20 20-4-4" />
        </svg>
        <label className="sr-only" htmlFor="search-input">
          Search Prisms, chats, pages, settings and actions
        </label>
        <input
          id="search-input"
          type="search"
          role="combobox"
          aria-expanded="true"
          aria-controls="search-list"
          aria-autocomplete="list"
          aria-activedescendant={activeIndex >= 0 ? `search-option-${activeIndex}` : undefined}
          autoComplete="off"
          spellCheck={false}
          placeholder="Search Prisms, chats, pages, settings…"
          ref={inputRef}
          value={query}
          onChange={(event) => onInput(event.currentTarget.value)}
          onKeyDown={onKeyDown}
        />
        <kbd className="search-esc">Esc</kbd>
      </div>
      <div id="search-list" className="search-list" role="listbox" aria-label="Results">
        {groups.map((group) => (
          <div key={group.kind} role="group" aria-label={group.heading}>
            <div className="search-group" aria-hidden="true">
              {heading(group.kind, group.heading)}
            </div>
            {group.pending ? (
              <p className="search-note">
                {messageState === "loading"
                  ? "Searching conversations…"
                  : messageState === "error"
                    ? "Conversations could not be searched."
                    : "No conversation matches."}
              </p>
            ) : null}
            {group.rows.map((row, offset) => {
              const index = group.start + offset;
              return (
                <div
                  key={`${row.kind}-${index}-${row.label}`}
                  id={`search-option-${index}`}
                  className="search-item"
                  role="option"
                  aria-selected={index === activeIndex}
                  ref={(node) => {
                    if (node) optionRefs.current.set(index, node);
                    else optionRefs.current.delete(index);
                  }}
                  onPointerMove={() => {
                    if (activeIndex !== index) setActive(index, false);
                  }}
                  onClick={() => activate(index)}
                >
                  <span className="search-icon">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      {ICONS[row.kind === "message" ? "chat" : row.icon || row.kind] || ICONS.page}
                    </svg>
                  </span>
                  <span className="search-text">
                    <span className="search-label">
                      <Highlight text={row.label} terms={terms} />
                    </span>
                    <span className="search-sub">{row.kind === "message" ? row.sub : <Highlight text={row.sub} terms={terms} />}</span>
                    {row.snippet ? (
                      <span className="search-snippet">
                        <Highlight text={row.snippet} terms={terms} />
                      </span>
                    ) : null}
                  </span>
                  <span className="search-enter" aria-hidden="true">
                    ↵
                  </span>
                </div>
              );
            })}
          </div>
        ))}
        {!shown.length && !groups.length ? (
          <p className="search-note">{query.trim() ? `No results for “${query.trim()}”.` : "Start typing to search."}</p>
        ) : null}
      </div>
      <p id="search-status" className="sr-only" role="status" aria-live="polite">
        {shown.length ? `${shown.length} results` : "No results"}
      </p>
      <div className="search-foot" aria-hidden="true">
        <span>
          <kbd>↑</kbd>
          <kbd>↓</kbd> Navigate
        </span>
        <span>
          <kbd>↵</kbd> Open
        </span>
        <span>
          <kbd>Esc</kbd> Close
        </span>
      </div>
    </dialog>
  );
}
