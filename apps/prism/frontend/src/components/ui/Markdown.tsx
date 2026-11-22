import { Fragment, type HTMLAttributes, type ReactNode } from "react";
import { cx } from "./cx";

// Tiny, safe Markdown view for job descriptions and instructions: headings, bullets, numbered
// lists, bold, italics and `code`. Everything is React text and elements, never HTML.

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const token = match[0];
    const inner = token.replace(/^(\*\*|`|\*)|(\*\*|`|\*)$/g, "");
    const key = out.length;
    out.push(token.startsWith("**") ? <strong key={key}>{inner}</strong> : token.startsWith("`") ? <code key={key}>{inner}</code> : <em key={key}>{inner}</em>);
    last = match.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "paragraph"; lines: string[] };

function parse(text: string): Block[] {
  const blocks: Block[] = [];
  let list: Extract<Block, { type: "list" }> | null = null;
  let paragraph: Extract<Block, { type: "paragraph" }> | null = null;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      list = null;
      paragraph = null;
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      list = null;
      paragraph = null;
      blocks.push({ type: "heading", level: Math.min(heading[1].length + 1, 5), text: heading[2] });
      continue;
    }
    const item = /^\s*([-*•]|\d+[.)])\s+(.*)$/.exec(line);
    if (item) {
      const ordered = /\d/.test(item[1]);
      if (!list || list.ordered !== ordered) {
        list = { type: "list", ordered, items: [] };
        blocks.push(list);
      }
      list.items.push(item[2]);
      paragraph = null;
      continue;
    }
    list = null;
    if (!paragraph) {
      paragraph = { type: "paragraph", lines: [] };
      blocks.push(paragraph);
    }
    paragraph.lines.push(line.trim());
  }
  return blocks;
}

export interface MarkdownProps extends Omit<HTMLAttributes<HTMLDivElement>, "children" | "dangerouslySetInnerHTML"> {
  source: string | null | undefined;
}

/** Renders into `<div class="{className} markdown">`; empty input shows "Nothing written yet.". */
export function Markdown({ source, className, ...rest }: MarkdownProps) {
  const text = String(source || "").trim();
  return (
    <div {...rest} className={cx(className, "markdown")}>
      {!text ? (
        <p className="panel-note">Nothing written yet.</p>
      ) : (
        parse(text).map((block, index) => {
          if (block.type === "heading") {
            const Tag = `h${block.level}` as "h2" | "h3" | "h4" | "h5";
            return <Tag key={index}>{inline(block.text)}</Tag>;
          }
          if (block.type === "list") {
            const Tag = block.ordered ? "ol" : "ul";
            return (
              <Tag key={index} data-ordered={String(block.ordered)}>
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex}>{inline(item)}</li>
                ))}
              </Tag>
            );
          }
          return (
            <p key={index}>
              {block.lines.map((line, lineIndex) => (
                <Fragment key={lineIndex}>
                  {lineIndex > 0 ? <br /> : null}
                  {inline(line)}
                </Fragment>
              ))}
            </p>
          );
        })
      )}
    </div>
  );
}
