import { useEffect, useState } from "react";
import { PrismLogo } from "@/components/ui";
import { isQaPrism, useComputersEnabled } from "@/features/computers";
import { agentApi } from "@/lib/api";
import { readStorage, writeStorage } from "@/lib/storage";
import { useChatController, useChatState } from "./ChatContext";
import { briefDescription, SUGGESTIONS } from "./format";
import type { Suggestions } from "./types";

const QA_STEPS = [
  "Tell me a site to test, for example “test example.com and check the contact form”",
  "I'll show you a plan; you decide when I start",
  "Watch my screen on the right, then read my report here",
];
const COMPUTER_STEPS = [
  "Give me a task, for example “find 5 fintech companies in Bangalore and list their websites”",
  "I'll show you a plan; you decide when I start",
  "Watch my computer on the right, then read my report here",
];
const PLAIN_STEPS = [
  "Ask naturally and Prism will choose the relevant chats",
  "Select a chat only when you want a hard one-chat limit",
  "Check the evidence and approve only actions you requested",
];

/** Shown only while the conversation is empty, so they appear once after onboarding. */
function useFirstSuggestions(prismId: string | null, enabled: boolean): Suggestions {
  const [data, setData] = useState<Suggestions>({});
  useEffect(() => {
    setData({});
    if (!prismId || !enabled) return;
    let current = true;
    const key = `prism-first-suggestions-v2:${prismId}`;
    void (async () => {
      let stored: Suggestions;
      try {
        stored = JSON.parse(readStorage(key) || "{}") as Suggestions;
      } catch {
        stored = {};
      }
      if (!stored.steps?.length && !stored.suggestions?.length) {
        try {
          stored = await agentApi<Suggestions>(`/api/v2/prisms/${prismId}/suggestions`);
          if (stored.steps?.length || stored.suggestions?.length) writeStorage(key, JSON.stringify(stored));
        } catch {
          return;
        }
      }
      if (current) setData(stored);
    })();
    return () => {
      current = false;
    };
  }, [prismId, enabled]);
  return data;
}

export function Welcome() {
  const controller = useChatController();
  const { activeThread, prism } = useChatState();
  const computers = useComputersEnabled();
  const label = activeThread?.source_label;
  const extra = useFirstSuggestions(prism?.id ?? null, Boolean(prism) && computers);
  const fill = (text: string) => {
    controller.setComposerText(text);
    controller.focus("composer");
  };
  const chips = (items: string[]) => (
    <div className="suggestions">
      {items.map((suggestion) => (
        <button type="button" className="mini-button" key={suggestion} onClick={() => fill(suggestion)}>
          {suggestion}
        </button>
      ))}
    </div>
  );
  const steps = extra.steps?.length ? extra.steps : isQaPrism(prism) ? QA_STEPS : prism && computers ? COMPUTER_STEPS : PLAIN_STEPS;
  return (
    <div className="agent-welcome">
      {prism ? <PrismLogo prism={prism} className="prism-logo welcome-logo" /> : <span className="welcome-mark">P</span>}
      {!label ? (
        <>
          <h2>{prism ? `Talk to your ${prism.name} Prism` : "Talk to your manager Prism"}</h2>
          <p className="welcome-about">
            {prism
              ? briefDescription(prism.description)
              : "Ask naturally and Prism will disclose which Teams chats it reads. Use the chat selector in the message box to limit a request to one chat."}
          </p>
          <ol className="welcome-steps">
            {steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
          {prism && computers && extra.suggestions?.length ? chips(extra.suggestions) : null}
        </>
      ) : (
        <>
          <h2>{`Ask Prism about ${label}`}</h2>
          <p>Prism reads this conversation and shows the evidence behind everything it flags.</p>
          {chips(SUGGESTIONS)}
        </>
      )}
    </div>
  );
}
