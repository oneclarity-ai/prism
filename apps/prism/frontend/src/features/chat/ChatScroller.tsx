import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { SetupCallout } from "@/features/legacy";
import { Composer } from "./Composer";
import { useChatController, useChatState } from "./ChatContext";
import { Timeline } from "./Timeline";

const NEAR_BOTTOM = 120;
const JUMP_DISTANCE = 240;

const distanceFromBottom = (scroller: HTMLElement): number => scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;

/** The scrolling conversation and the composer dock that sits below it (the jump button belongs to the dock). */
export function ChatScroller() {
  const controller = useChatController();
  const { scroll } = useChatState();
  const scroller = useRef<HTMLDivElement | null>(null);
  const nearBottom = useRef(true);
  const handled = useRef(0);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [scrolling, setScrolling] = useState(false);
  const [jumpHidden, setJumpHidden] = useState(true);

  const updateJump = () => {
    if (scroller.current) setJumpHidden(distanceFromBottom(scroller.current) < JUMP_DISTANCE);
  };

  // The stream is rebuilt by React, so "near the bottom" is whatever the last commit left behind.
  useLayoutEffect(() => {
    const element = scroller.current;
    if (!element) return;
    if (handled.current !== scroll.nonce) {
      handled.current = scroll.nonce;
      if (scroll.kind === "bottom" || (scroll.kind === "auto" && nearBottom.current)) element.scrollTop = element.scrollHeight;
      if (scroll.focusMessage) {
        const message = controller.refs.messages.get(scroll.focusMessage);
        message?.scrollIntoView?.({ block: "center" });
        message?.focus();
      }
      if (scroll.kind !== "keep" && scroll.kind !== "none") updateJump();
    }
    nearBottom.current = distanceFromBottom(element) < NEAR_BOTTOM;
  });

  useEffect(() => () => clearTimeout(hideTimer.current), []);

  const onScroll = () => {
    if (scroller.current) nearBottom.current = distanceFromBottom(scroller.current) < NEAR_BOTTOM;
    updateJump();
    // The scrollbar fades in while scrolling and out shortly after.
    setScrolling(true);
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setScrolling(false), 900);
  };

  return (
    <>
      <div
        className={`agent-scroll fade-scrollbar${scrolling ? " scrolling" : ""}`}
        id="agent-scroll"
        ref={(node) => {
          scroller.current = node;
          controller.refs.scroller = node;
        }}
        onScroll={onScroll}
      >
        <div className="agent-stream">
          <SetupCallout />
          <Timeline />
        </div>
      </div>
      <Composer
        jumpHidden={jumpHidden}
        onJump={() => scroller.current?.scrollTo?.({ top: scroller.current.scrollHeight, behavior: "smooth" })}
      />
    </>
  );
}
