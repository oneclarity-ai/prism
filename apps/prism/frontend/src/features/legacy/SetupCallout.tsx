import { useApp } from "@/lib/app-context";
import { useConnectMicrosoft } from "./microsoft";

interface Step {
  text: string;
  action?: "connect" | "provider";
  label?: string;
}

/** The short "Finish setting up Prism" checklist (old `renderSetup`, `[data-setup]`). */
export function SetupCallout() {
  const app = useApp();
  const connect = useConnectMicrosoft();
  const steps: Step[] = [];
  const { microsoft, providerStatus: provider } = app;
  if (microsoft && !microsoft.is_connected) {
    steps.push(
      microsoft.is_auth_configured
        ? {
            text: "Connect your Microsoft account so Prism can read your Teams chats and send replies you approve.",
            action: "connect",
            label: "Connect Microsoft account",
          }
        : { text: "Add the Microsoft settings to .env and restart the API to connect Teams." },
    );
  }
  if (app.modes.v21 === true && provider && !provider.ready && provider.state !== "unavailable") {
    steps.push({ text: `AI provider: ${provider.detail}`, action: "provider", label: "Open settings" });
  }
  return (
    <div className="callout setup-callout" data-setup hidden={steps.length === 0}>
      {steps.length ? (
        <>
          <span className="callout-icon" aria-hidden="true">
            👋
          </span>
          <div className="callout-body">
            <strong>Finish setting up Prism</strong>
            <ul className="setup-steps">
              {steps.map((step) => (
                <li key={step.text}>
                  <span>{step.text}</span>
                  {step.action ? (
                    <button
                      className="mini-button"
                      type="button"
                      data-setup-action={step.action}
                      onClick={() => {
                        if (step.action === "connect") void connect();
                        else app.settings.open("provider");
                      }}
                    >
                      {step.label}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : null}
    </div>
  );
}
