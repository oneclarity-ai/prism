import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "./index";

const html = (source: string, props: { className?: string } = {}) => render(<Markdown source={source} {...props} />).container.firstElementChild as HTMLElement;

describe("Markdown", () => {
  it("adds the markdown class after the caller's class and forwards attributes", () => {
    const { container } = render(<Markdown source="x" className="pd-rich-view" hidden id="v" />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toBe("pd-rich-view markdown");
    expect(root.hidden).toBe(true);
    expect(root.id).toBe("v");
  });

  it("shows a placeholder for empty input", () => {
    for (const source of ["", "   \n ", null, undefined]) {
      const { container } = render(<Markdown source={source} />);
      expect(container.querySelector("p.panel-note")).toHaveTextContent("Nothing written yet.");
    }
  });

  it("maps heading levels 1-4 to h2-h5", () => {
    const root = html("# a\n## b\n### c\n#### d\n##### not a heading");
    expect([...root.children].map((c) => c.tagName)).toEqual(["H2", "H3", "H4", "H5", "P"]);
    expect(root.querySelector("h2")).toHaveTextContent("a");
  });

  it("builds bullet and numbered lists, switching lists when the kind changes", () => {
    const root = html("- one\n* two\n• three\n1. first\n2) second\n\n- again");
    const kids = [...root.children];
    expect(kids.map((c) => c.tagName)).toEqual(["UL", "OL", "UL"]);
    expect(kids[0].children).toHaveLength(3);
    expect(kids[0]).toHaveAttribute("data-ordered", "false");
    expect(kids[1]).toHaveAttribute("data-ordered", "true");
    expect(kids[1].textContent).toBe("firstsecond");
  });

  it("joins consecutive lines of a paragraph with <br> and splits on blank lines", () => {
    const root = html("line one\nline two\n\nnext");
    const [first, second] = [...root.querySelectorAll("p")];
    expect(first.innerHTML).toBe("line one<br>line two");
    expect(second.textContent).toBe("next");
  });

  it("renders bold, italics and code inline", () => {
    const root = html("a **b** and *c* and `d` end");
    expect(root.querySelector("strong")?.textContent).toBe("b");
    expect(root.querySelector("em")?.textContent).toBe("c");
    expect(root.querySelector("code")?.textContent).toBe("d");
    expect(root.querySelector("p")?.textContent).toBe("a b and c and d end");
  });

  it("does not interpret code contents or links", () => {
    const root = html("`**x**` and [site](https://example.com)");
    expect(root.querySelector("code")?.textContent).toBe("**x**");
    expect(root.querySelector("code strong")).toBeNull();
    expect(root.querySelector("a")).toBeNull();
    expect(root.textContent).toContain("[site](https://example.com)");
  });

  it("renders raw HTML and scripts as text", () => {
    const source = "<script>alert(1)</script>\n- <img src=x onerror=alert(1)>\n# <b>h</b>";
    const root = html(source);
    expect(root.querySelector("script, img, b")).toBeNull();
    expect(root.querySelector("p")?.textContent).toBe("<script>alert(1)</script>");
    expect(root.querySelector("li")?.textContent).toBe("<img src=x onerror=alert(1)>");
    expect(root.querySelector("h2")?.textContent).toBe("<b>h</b>");
  });

  it("handles CRLF line endings", () => {
    const root = html("# t\r\n- a\r\n- b\r\n");
    expect(root.querySelectorAll("li")).toHaveLength(2);
  });
});
