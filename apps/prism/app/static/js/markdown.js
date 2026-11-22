// Tiny, safe Markdown view for job descriptions and instructions: headings, bullets, numbered
// lists, bold, italics and `code`. Everything is built with DOM nodes and textContent, never HTML.

function inline(parent, text) {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) parent.append(document.createTextNode(text.slice(last, match.index)));
    const token = match[0];
    const node = document.createElement(token.startsWith("**") ? "strong" : token.startsWith("`") ? "code" : "em");
    node.textContent = token.replace(/^(\*\*|`|\*)|(\*\*|`|\*)$/g, "");
    parent.append(node);
    last = match.index + token.length;
  }
  if (last < text.length) parent.append(document.createTextNode(text.slice(last)));
}

export function renderMarkdown(root, source) {
  root.classList.add("markdown");
  root.replaceChildren();
  const text = String(source || "").trim();
  if (!text) {
    const empty = document.createElement("p");
    empty.className = "panel-note";
    empty.textContent = "Nothing written yet.";
    root.append(empty);
    return;
  }
  let list = null;
  let paragraph = null;
  const flush = () => { list = null; paragraph = null; };
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (!line.trim()) { flush(); continue; }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      flush();
      const node = document.createElement(`h${Math.min(heading[1].length + 1, 5)}`);
      inline(node, heading[2]);
      root.append(node);
      continue;
    }
    const item = /^\s*([-*•]|\d+[.)])\s+(.*)$/.exec(line);
    if (item) {
      const ordered = /\d/.test(item[1]);
      if (!list || list.dataset.ordered !== String(ordered)) {
        list = document.createElement(ordered ? "ol" : "ul");
        list.dataset.ordered = String(ordered);
        root.append(list);
      }
      const node = document.createElement("li");
      inline(node, item[2]);
      list.append(node);
      paragraph = null;
      continue;
    }
    list = null;
    if (!paragraph) { paragraph = document.createElement("p"); root.append(paragraph); } else paragraph.append(document.createElement("br"));
    inline(paragraph, line.trim());
  }
}
