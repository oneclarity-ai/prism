import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { HealthDialog } from "./HealthDialog";
import { usePrismsInternal } from "./internal";
import { NotifyDialog } from "./NotifyDialog";
import { OnboardingChat } from "./OnboardingChat";
import { PrismEditorDialog, type PrismEditorHandle } from "./PrismEditorDialog";
import { TriggerDialog, type DialogHandle } from "./TriggerDialog";

/**
 * Inside `data-tab="prisms"`: `#prism-workspace` (onboarding chat) plus the `prism-*` dialogs. The dialogs are
 * portalled to `document.body` so they can open while this (hidden) tab panel is not the visible one.
 */
export function PrismsPage() {
  const { registerCommands } = usePrismsInternal();
  const editor = useRef<PrismEditorHandle>(null);
  const trigger = useRef<DialogHandle>(null);
  const notify = useRef<DialogHandle>(null);
  const health = useRef<DialogHandle>(null);

  useEffect(
    () =>
      registerCommands({
        openCreate: () => editor.current?.openCreate(),
        openEditor: (prism) => editor.current?.openEditor(prism),
        openTrigger: () => void trigger.current?.open(),
        openNotify: () => void notify.current?.open(),
        openHealth: () => void health.current?.open(),
      }),
    [registerCommands],
  );

  return (
    <>
      <OnboardingChat />
      {createPortal(
        <>
          <TriggerDialog ref={trigger} />
          <NotifyDialog ref={notify} />
          <HealthDialog ref={health} />
          <PrismEditorDialog ref={editor} />
        </>,
        document.body,
      )}
    </>
  );
}
