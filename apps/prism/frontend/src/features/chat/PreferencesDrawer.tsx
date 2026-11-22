import { useState, type FormEvent, type KeyboardEvent } from "react";
import { PeoplePanel } from "@/features/people/PeoplePanel";
import { ScopePanel } from "@/features/prisms/ScopePanel";
import { usePrisms } from "@/features/prisms/PrismsContext";
import type { PrismAction } from "@/features/prisms/PrismsContext";
import { useApp } from "@/lib/app-context";
import { useChatController, useChatState } from "./ChatContext";
import { autoGrow } from "./DraftCard";
import { ProfilePanel } from "./ProfilePanel";
import type { DrawerTab, Preference } from "./types";

const CHEVRON = (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="m9 6 6 6-6 6" />
  </svg>
);

/** Rows in the Scope/More panels that trigger the Prism menu actions owned by the Prism directory. */
function ActionRow({ target, title, detail }: { target: PrismAction; title: string; detail: string }) {
  const controller = useChatController();
  const { runAction } = usePrisms();
  return (
    <button
      className="settings-row"
      type="button"
      data-prism-action={target}
      onClick={() => {
        controller.setPreferencesOpen(false);
        runAction?.(target);
      }}
    >
      <span>
        <strong>{title}</strong>
        <small>{detail}</small>
      </span>
      {CHEVRON}
    </button>
  );
}

function PreferenceRow({ preference }: { preference: Preference }) {
  const controller = useChatController();
  return (
    <article className={`pref-item${preference.is_active ? "" : " inactive"}`}>
      <button
        type="button"
        className="switch"
        role="switch"
        aria-checked={preference.is_active}
        aria-label={`${preference.is_active ? "Disable" : "Enable"} this preference`}
        onClick={() => void controller.updatePreference(preference, !preference.is_active)}
      />
      <div className="pref-copy">
        <p className="pref-text">{preference.instruction}</p>
        <span className="pref-meta">{`${preference.is_active ? "On" : "Paused"} · added ${new Date(preference.created_at).toLocaleDateString([], { month: "short", day: "numeric" })}`}</span>
      </div>
      <button type="button" className="icon-button small" aria-label="Edit preference" onClick={() => void controller.editPreference(preference)}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 20h4L19 9l-4-4L4 16v4ZM13.5 6.5l4 4" />
        </svg>
      </button>
      <button type="button" className="icon-button small danger-icon" aria-label="Delete preference" onClick={() => void controller.deletePreference(preference)}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12h10l1-12M9 7V4h6v3" />
        </svg>
      </button>
    </article>
  );
}

function PreferencesPanel() {
  const controller = useChatController();
  const { prism, preferences, drawer } = useChatState();
  const [text, setText] = useState("");
  const name = prism?.name;

  const save = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!text.trim()) return;
    if (await controller.savePreference(text)) setText("");
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void save();
    }
  };

  return (
    <section className="drawer-panel" role="tabpanel" data-drawer-panel="preferences" hidden={drawer.tab !== "preferences"}>
      <p id="agent-preferences-intro" className="panel-note">
        {name
          ? `How ${name} should work. These apply to ${name} only, never to your other Prisms.`
          : "Only explicit instructions are remembered. Draft edits stay feedback, not global rules."}
      </p>
      <form id="agent-preference-form" className="agent-preference-form" onSubmit={(event) => void save(event)}>
        <label className="sr-only" htmlFor="agent-preference-input">
          New instruction
        </label>
        <textarea
          id="agent-preference-input"
          ref={(node) => {
            controller.refs.preferenceInput = node;
            if (node) autoGrow(node, 140);
          }}
          rows={2}
          maxLength={4000}
          placeholder={name ? "For example: Keep replies short and friendly" : "For example: Keep replies concise and direct"}
          required
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <button className="button" type="submit">
          Add
        </button>
      </form>
      <p className="section-label pref-heading">Instructions</p>
      <div id="agent-preference-list" className={`agent-preference-list${preferences.length ? "" : " empty-state"}`}>
        {preferences.length
          ? preferences.map((preference) => <PreferenceRow key={preference.id} preference={preference} />)
          : prism
            ? `No instructions yet. Tell ${prism.name} how you want it to work.`
            : "No preferences saved yet. Tell Prism how you like to write replies."}
      </div>
    </section>
  );
}

const TABS: { tab: DrawerTab; label: string; needsPrism: boolean }[] = [
  { tab: "preferences", label: "Preferences", needsPrism: false },
  { tab: "profile", label: "Profile", needsPrism: true },
  { tab: "scope", label: "Scope", needsPrism: true },
  { tab: "people", label: "People", needsPrism: true },
  { tab: "more", label: "More", needsPrism: true },
];

export function PreferencesDrawer() {
  const controller = useChatController();
  const { modes } = useApp();
  const { prism, drawer } = useChatState();
  const hiddenIf = (tab: DrawerTab) => drawer.tab !== tab;

  return (
    <aside id="agent-preferences-panel" className={`agent-drawer${drawer.open ? " open" : ""}`} aria-label="Prism settings">
      <div className="drawer-head">
        <h3 id="agent-drawer-title">Settings</h3>
        {/* Everything about this Prism (profile, instructions, tools, limits, tasks) is on its Workspace page. */}
        <button
          id="agent-more-settings"
          className="button secondary drawer-more"
          type="button"
          hidden={!(prism && modes.v24 === true)}
          onClick={() => controller.openMoreSettings()}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 7h8M16 7h4M4 17h4M12 17h8" />
            <circle cx="14" cy="7" r="2" />
            <circle cx="10" cy="17" r="2" />
          </svg>
          <span>More settings</span>
        </button>
        <button id="agent-preferences-close" className="icon-button" type="button" aria-label="Close settings" onClick={() => controller.setPreferencesOpen(false)}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
      <div className="drawer-tabs" role="tablist" aria-label="Prism settings">
        {TABS.map(({ tab, label, needsPrism }) => (
          <button
            key={tab}
            className={`drawer-tab${drawer.tab === tab ? " active" : ""}`}
            type="button"
            role="tab"
            aria-selected={drawer.tab === tab}
            data-drawer-tab={tab}
            data-needs-prism={needsPrism ? "" : undefined}
            hidden={needsPrism && !prism}
            onClick={() => controller.setDrawerTab(tab)}
          >
            {label}
          </button>
        ))}
      </div>
      <PreferencesPanel />
      <section className="drawer-panel" role="tabpanel" data-drawer-panel="profile" hidden={hiddenIf("profile")}>
        <ProfilePanel />
      </section>
      <section className="drawer-panel" role="tabpanel" data-drawer-panel="people" hidden={hiddenIf("people")}>
        <div id="prism-people-root" className="prism-people">
          <PeoplePanel />
        </div>
      </section>
      <section className="drawer-panel" role="tabpanel" data-drawer-panel="scope" hidden={hiddenIf("scope")}>
        <ScopePanel />
        <ActionRow target="prism-trigger-button" title="Monitoring schedule" detail="When it checks for new activity" />
      </section>
      <section className="drawer-panel" role="tabpanel" data-drawer-panel="more" hidden={hiddenIf("more")}>
        <ActionRow target="prism-notify-button" title="Notifications" detail="Browser alerts for new updates" />
        <ActionRow target="prism-sync-button" title="Refresh Teams activity" detail="Check for new messages now" />
        <ActionRow target="prism-health-button" title="Status & tuning" detail="Health, budgets, and signal settings" />
        <button className="settings-row danger" type="button" id="agent-archive-start" onClick={() => controller.setArchiveConfirm(true)}>
          <span>
            <strong>Archive this Prism</strong>
            <small>Stops monitoring. History is kept.</small>
          </span>
          {CHEVRON}
        </button>
        <div id="agent-archive-confirm" className="archive-confirm" role="alertdialog" aria-labelledby="agent-archive-title" hidden={!drawer.archiveConfirm}>
          <strong id="agent-archive-title">Archive this Prism?</strong>
          <p>It disappears from your list and stops monitoring. Its history and audit trail are kept.</p>
          <div className="archive-actions">
            <button id="agent-archive-cancel" className="button secondary" type="button" onClick={() => controller.setArchiveConfirm(false)}>
              Keep it
            </button>
            <button
              id="agent-archive-yes"
              ref={(node) => {
                controller.refs.archiveYes = node;
              }}
              className="button danger"
              type="button"
              onClick={() => controller.confirmArchive()}
            >
              Archive
            </button>
          </div>
        </div>
      </section>
    </aside>
  );
}
