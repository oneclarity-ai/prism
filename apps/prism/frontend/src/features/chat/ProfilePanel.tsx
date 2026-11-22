import { useEffect, useState, type FormEvent } from "react";
import { ColorPicker, PrismLogo } from "@/components/ui";
import { useComputersEnabled } from "@/features/computers";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { emit } from "@/lib/events";
import { prismColorKey } from "@/lib/prism-logo";
import { useChatController, useChatState } from "./ChatContext";
import type { ChatPrism, NotificationSetting } from "./types";

// Edit profile happens right here in the drawer: name, description, and notifications.
function ProfileForm({ prism }: { prism: ChatPrism | null }) {
  const controller = useChatController();
  const { setStatus } = useApp();
  const computers = useComputersEnabled();
  const [name, setName] = useState(prism?.name ?? "");
  const [description, setDescription] = useState(prism?.description || "");
  const [color, setColor] = useState(prismColorKey(prism));
  const [logins, setLogins] = useState(prism?.logins_policy || "never");
  const [notify, setNotify] = useState(false);
  const [setting, setSetting] = useState<NotificationSetting | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const prismId = prism?.id;
  const archived = String(prism?.state).toLowerCase() === "archived";

  useEffect(() => {
    if (!prismId) return;
    let current = true;
    agentApi<NotificationSetting>(`/api/v2/prisms/${prismId}/notification-settings`)
      .then((loaded) => {
        if (!current) return;
        setSetting(loaded);
        setNotify(loaded.enabled);
      })
      .catch(() => setSetting(null));
    return () => {
      current = false;
    };
  }, [prismId]);

  const dirty =
    Boolean(prism) &&
    (color !== prismColorKey(prism) ||
      name.trim() !== prism?.name ||
      description.trim() !== (prism?.description || "") ||
      (computers && logins !== (prism?.logins_policy || "never")) ||
      Boolean(setting && notify !== setting.enabled));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!prism) return;
    setError(null);
    setSaving(true);
    try {
      const trimmedName = name.trim();
      const trimmedDescription = description.trim();
      if (trimmedName !== prism.name || trimmedDescription !== (prism.description || "") || color !== prismColorKey(prism)) {
        const updated = await agentApi<ChatPrism>(`/api/v2/prisms/${prism.id}`, {
          method: "PATCH",
          ...jsonBody({ name: trimmedName, description: trimmedDescription, color, expected_lifecycle_version: prism.lifecycle_version }),
        });
        controller.applyPrismUpdate(updated);
        emit("prism-updated", { prism: updated });
      }
      if (computers && logins !== (prism.logins_policy || "never")) {
        const updated = await agentApi<ChatPrism>(`/api/v2/prisms/${prism.id}/profile`, {
          method: "PATCH",
          ...jsonBody({ logins_policy: logins }),
        });
        controller.applyPrismUpdate(updated);
        emit("prism-updated", { prism: updated });
      }
      if (setting && notify !== setting.enabled) {
        if (notify && "Notification" in window && Notification.permission === "default") await Notification.requestPermission();
        setSetting(
          await agentApi<NotificationSetting>(`/api/v2/prisms/${prism.id}/notification-settings`, {
            method: "PUT",
            ...jsonBody({ enabled: notify, min_urgency: setting.min_urgency }),
          }),
        );
      }
      controller.refreshHeader();
      setStatus("Profile saved.");
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form id="agent-profile-form" className="profile-form" onSubmit={(event) => void submit(event)}>
      <span id="agent-drawer-avatar" className="profile-avatar" aria-hidden="true">
        <PrismLogo colorKey={color} className="prism-logo" />
      </span>
      <div id="agent-profile-colors" className="profile-colors">
        <ColorPicker selected={color} onPick={setColor} name="agent-profile-color" />
      </div>
      <label htmlFor="agent-profile-name">
        Name
        <input
          id="agent-profile-name"
          maxLength={120}
          required
          autoComplete="off"
          disabled={archived}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label htmlFor="agent-profile-description">
        Description
        <textarea
          id="agent-profile-description"
          rows={4}
          maxLength={2000}
          required
          disabled={archived}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <p id="agent-profile-organization" className="panel-note">
        {`${prism?.job_role || "Prism Specialist"} · ${prism?.department || "Operations"}`}
      </p>
      <button id="agent-profile-organization-edit" className="mini-button" type="button" disabled={archived} onClick={() => controller.editOrganization()}>
        Edit role, department & reporting
      </button>
      <label className="switch-row" htmlFor="agent-profile-notify">
        <span>
          <strong>Notifications</strong>
          <small>Get notified when this Prism has something for you</small>
        </span>
        <input
          id="agent-profile-notify"
          className="toggle"
          type="checkbox"
          role="switch"
          disabled={archived}
          checked={notify}
          onChange={(event) => setNotify(event.target.checked)}
        />
      </label>
      <fieldset id="agent-profile-logins" className="prism-fieldset" hidden={!computers}>
        <legend>Signing in to websites</legend>
        <label className="check-row">
          <input type="radio" name="agent-profile-logins" value="never" checked={logins === "never"} onChange={() => setLogins("never")} />
          <span>
            Never sign in <em>public pages only</em>
          </span>
        </label>
        <label className="check-row">
          <input type="radio" name="agent-profile-logins" value="ask" checked={logins === "ask"} onChange={() => setLogins("ask")} />
          <span>
            Sign in when needed <em>with logins I give in the chat, kept encrypted</em>
          </span>
        </label>
      </fieldset>
      <p id="agent-profile-error" className="inline-error" role="alert" hidden={!error}>
        {error}
      </p>
      <button id="agent-profile-save" className="button" type="submit" disabled={!dirty || saving}>
        Save changes
      </button>
    </form>
  );
}

/** Re-created every time the Profile tab is selected, so it always starts from the saved Prism. */
export function ProfilePanel() {
  const { prism, drawer } = useChatState();
  return <ProfileForm key={`${prism?.id ?? "none"}:${drawer.profileNonce}`} prism={prism} />;
}
