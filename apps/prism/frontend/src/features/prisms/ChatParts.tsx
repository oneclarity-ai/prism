import { clock, formatTime, initial } from "./helpers";

export interface BubbleProps {
  speaker: string;
  message: string;
  kind?: "assistant" | "user";
  time?: string | null;
  meta?: string | null;
}

/** One chat turn: the manager's bubble or the Prism's avatar + text. */
export function Bubble({ speaker, message, kind = "assistant", time = null, meta = null }: BubbleProps) {
  if (kind === "user") {
    return (
      <div className="turn user">
        <div className="bubble">
          <p>{message}</p>
        </div>
      </div>
    );
  }
  return (
    <div className="turn assistant">
      <span className="avatar prism">{initial(speaker)}</span>
      <div className="turn-body say">
        {meta || time ? (
          <div className="turn-head">
            {meta ? <span className="turn-meta">{meta}</span> : null}
            {time ? (
              <time dateTime={time} title={formatTime(time)}>
                {clock(time)}
              </time>
            ) : null}
          </div>
        ) : null}
        <p className="turn-text">{message}</p>
      </div>
    </div>
  );
}

/** Just the animation; the words are only for screen readers. */
export function TypingIndicator({ name, stage = "" }: { name: string; stage?: string }) {
  return (
    <div className="turn assistant turn-typing" role="status">
      <span className="avatar prism">{initial(name)}</span>
      <div className="turn-body say">
        <span className="typing-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="sr-only">{stage || `${name} is typing`}</span>
      </div>
    </div>
  );
}
