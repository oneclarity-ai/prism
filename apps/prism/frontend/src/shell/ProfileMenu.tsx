import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useApp } from "@/lib/app-context";
import { setTheme, uiZoom, useThemeChoice } from "@/lib/prefs";
import { readStorage, STORAGE_KEYS, writeStorage } from "@/lib/storage";
import { useShell } from "./shell-context";

const THEMES = [
  { value: "system", label: "System", path: <><rect width="20" height="14" x="2" y="3" rx="2" /><path d="M8 21h8M12 17v4" /></> },
  { value: "dark", label: "Dark", path: <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" /> },
  {
    value: "light",
    label: "Light",
    path: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2m-7.07-17.07 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41m11.32-11.32 1.41-1.41" />
      </>
    ),
  },
] as const;

const GEAR =
  "M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z";

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

export function ProfileMenu() {
  const app = useApp();
  const { profileMenuResetKey } = useShell();
  const theme = useThemeChoice();
  const [open, setOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const [style, setStyle] = useState<CSSProperties>({});
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const row = useRef<HTMLDivElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    setStatusOpen(false);
  }, []);

  useEffect(() => {
    close();
  }, [profileMenuResetKey, close]);

  const position = useCallback(() => {
    const node = menu.current;
    const anchor = row.current ?? trigger.current;
    if (!node || !anchor) return;
    // Layout pixels: getBoundingClientRect and innerWidth are visual, style values are zoomed.
    const z = uiZoom();
    const box = anchor.getBoundingClientRect();
    const rect = { left: box.left / z, bottom: box.bottom / z, top: box.top / z, width: box.width / z };
    const viewW = innerWidth / z;
    const viewH = innerHeight / z;
    const gap = 8;
    const edge = 12;
    const width = Math.min(rect.width, viewW - edge * 2);
    node.style.width = `${width}px`;
    const above = rect.top - node.offsetHeight - gap;
    setStyle({
      width: `${width}px`,
      left: `${Math.max(edge, Math.min(rect.left, viewW - node.offsetWidth - edge))}px`,
      top: `${above >= edge ? above : Math.max(edge, Math.min(rect.bottom + gap, viewH - node.offsetHeight - edge))}px`,
    });
  }, []);

  useLayoutEffect(() => {
    if (open) position();
  }, [open, statusOpen, position]);

  useEffect(() => {
    if (!open) return;
    const workspace = document.querySelector(".workspace");
    window.addEventListener("resize", position);
    workspace?.addEventListener("scroll", position, { passive: true });
    return () => {
      window.removeEventListener("resize", position);
      workspace?.removeEventListener("scroll", position);
    };
  }, [open, position]);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      const target = event.target as Element | null;
      if (target?.closest("#profile-menu [data-connect-microsoft]") || !target?.closest("#profile-menu, #profile-menu-trigger")) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Tab") {
        close();
        trigger.current?.focus();
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        close();
        trigger.current?.focus();
        return;
      }
      const target = event.target as Element;
      const inTheme = target.closest(".profile-theme-options");
      if (inTheme && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
        event.preventDefault();
        const radios = [...inTheme.querySelectorAll<HTMLElement>("[role='radio']")];
        radios[(radios.indexOf(target as HTMLElement) + (event.key === "ArrowLeft" ? -1 : 1) + radios.length) % radios.length]?.focus();
        return;
      }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) || !target.closest("#profile-menu")) return;
      event.preventDefault();
      const items = [...menu.current!.querySelectorAll<HTMLElement>(".profile-menu-group > [role='menuitem'], .profile-theme-options [aria-checked='true']")];
      const index = items.indexOf(document.activeElement as HTMLElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length;
      items[next]?.focus();
    };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open, close]);

  const openMenu = (last = false) => {
    setOpen(true);
    requestAnimationFrame(() => {
      const items = menu.current?.querySelectorAll<HTMLElement>(".profile-menu-group > [role='menuitem']");
      if (items?.length) items[last ? items.length - 1 : 0]?.focus();
    });
  };

  const onTriggerKey = (event: ReactKeyboardEvent) => {
    if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
    event.preventDefault();
    openMenu(event.key === "ArrowUp");
  };

  const act = (action: string) => {
    if (action === "settings" || action === "account" || action === "workspace") {
      app.settings.open(action === "account" ? "account" : action === "workspace" ? "general" : undefined);
    } else if (action === "status") {
      setStatusOpen((value) => !value);
    } else if (action === "signout") {
      close();
      if (!readStorage(STORAGE_KEYS.operatorToken)) {
        app.setStatus("Local mode has no sign-in session to end.");
        return;
      }
      void app
        .askDialog({
          title: "Sign out of this browser?",
          message: "This removes the operator access key stored in this browser. It will not disconnect Microsoft Teams.",
          confirmLabel: "Sign out",
        })
        .then((confirmed) => {
          if (!confirmed) return;
          writeStorage(STORAGE_KEYS.operatorToken, null);
          window.location.reload();
        });
    }
  };

  const connected = Boolean(app.microsoft?.is_connected && app.microsoft.connection);
  const name = connected ? String(app.microsoft?.connection?.display_name ?? "Microsoft account") : "Microsoft account";
  const letters = connected ? initials(name) : "M";
  const providerText = app.providerStatus?.ready ? "AI provider ready" : "AI provider needs attention";
  const microsoftText = app.microsoft?.is_connected ? "Microsoft Teams connected" : "Microsoft Teams not connected";
  const computerText = app.modes.v24 === true ? "Computer features available" : "Computer features unavailable";
  const warn = !app.providerStatus?.ready || !app.microsoft?.is_connected;

  return (
    <div className="sidebar-footer">
      <div className="profile-row" ref={row}>
        <button
          id="profile-menu-trigger"
          ref={trigger}
          className="account-chip"
          type="button"
          aria-label="Open profile menu"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls="profile-menu"
          onClick={() => (open ? close() : openMenu())}
          onKeyDown={onTriggerKey}
        >
          <span id="account-avatar" className="account-avatar">{letters}</span>
          <span id="account-menu-name" className="account-menu-name">{name}</span>
          <svg className="chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m7 15 5 5 5-5M7 9l5-5 5 5" /></svg>
        </button>
        <button id="nav-settings" className="icon-button" type="button" data-tab-target="settings" aria-label="Settings" data-tooltip="Settings" onClick={() => {
            app.setActiveTab("settings");
            app.closeSidebarIfNarrow();
          }}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d={GEAR} /></svg>
        </button>
      </div>
      <div id="profile-menu" ref={menu} className="profile-menu" role="menu" aria-label="Profile" hidden={!open} style={style}>
        <div className="profile-menu-group">
          <button type="button" role="menuitem" data-profile-action="settings" onClick={() => act("settings")}>
            <span className="menu-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" /><path d={GEAR} /></svg></span>
            <span>Settings</span>
          </button>
          <div className="profile-theme-row">
            <span className="profile-theme-label">
              <span className="menu-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 3a9 9 0 0 1 0 18Z" /></svg></span>
              <span>Theme</span>
            </span>
            <div className="profile-theme-options" role="radiogroup" aria-label="Color theme">
              {THEMES.map((item) => (
                <button key={item.value} type="button" role="radio" aria-checked={theme === item.value} data-profile-theme={item.value} aria-label={item.label} title={item.label} onClick={() => setTheme(item.value)}>
                  <svg viewBox="0 0 24 24" aria-hidden="true">{item.path}</svg>
                </button>
              ))}
            </div>
          </div>
          <button type="button" role="menuitem" data-profile-action="status" onClick={() => act("status")}>
            <span className="menu-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 12h4l3-8 4 16 3-8h4" /></svg></span>
            <span>System status</span>
            <span id="profile-status-dot" className={`profile-status-dot${warn ? " warn" : ""}`} aria-hidden="true"></span>
          </button>
          <div id="profile-status-details" className="profile-status-details" hidden={!statusOpen}>
            {`${providerText} · ${microsoftText} · ${computerText}`}
          </div>
        </div>
        <div className="profile-menu-group">
          <button type="button" role="menuitem" className="profile-menu-muted" data-profile-action="signout" onClick={() => act("signout")}>
            <span className="menu-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></svg></span>
            <span>Log out</span>
          </button>
        </div>
      </div>
    </div>
  );
}
