import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button, Chip, Empty, Icon, Metric, Panel, SearchField, SelectField, StatusChip } from "./index";

describe("primitives", () => {
  it("Icon renders the sprite use", () => {
    const { container } = render(<Icon name="bot" className="big" />);
    const svg = container.querySelector("svg") as SVGElement;
    expect(svg.getAttribute("class")).toBe("workspace-icon big");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg.querySelector("use")).toHaveAttribute("href", "/dashboard/assets/workspace-icons.svg#bot");
    expect(render(<Icon name="x" />).container.querySelector("svg")?.getAttribute("class")).toBe("workspace-icon");
  });

  it("Button: defaults, glyph, title and click", async () => {
    const onClick = vi.fn();
    const { container } = render(
      <>
        <Button text="Go" onClick={onClick} />
        <Button glyph="x" className="icon-button" title="Close" />
      </>,
    );
    const [go, close] = [...container.querySelectorAll("button")];
    expect(go.className).toBe("mini-button");
    expect(go.type).toBe("button");
    expect(go.innerHTML).toBe("<span>Go</span>");
    expect(close.getAttribute("aria-label")).toBe("Close");
    expect(close.title).toBe("Close");
    expect(close.querySelector("svg")).not.toBeNull();
    expect(close.querySelector("span")).toBeNull();
    await userEvent.setup().click(go);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("Chip and StatusChip", () => {
    const { container } = render(
      <>
        <Chip tone="red">prod</Chip>
        <Chip>plain</Chip>
        <StatusChip value="waiting_approval" />
        <StatusChip value="odd_one" />
      </>,
    );
    const [a, b, c, d] = [...container.children];
    expect(a.className).toBe("workspace-chip tone-red");
    expect(b.className).toBe("workspace-chip tone-gray");
    expect(c.className).toBe("workspace-status tone-orange");
    expect(c.textContent).toBe("Needs approval");
    expect(c.firstElementChild?.tagName.toLowerCase()).toBe("svg");
    expect(d.className).toBe("workspace-status tone-gray");
    expect(d.textContent).toBe("odd one");
  });

  it("Empty", () => {
    const { container } = render(<Empty title="Nothing" description="Try again" glyph="bot" />);
    expect(container.innerHTML).toContain('<strong>Nothing</strong><p>Try again</p>');
    expect(container.querySelector("use")).toHaveAttribute("href", expect.stringContaining("#bot"));
    const bare = render(<Empty title="T" />).container;
    expect(bare.querySelector("p")).toBeNull();
    expect(bare.querySelector("use")).toHaveAttribute("href", expect.stringContaining("#list-checks"));
  });

  it("SelectField is controlled with an aria-label", async () => {
    const onChange = vi.fn();
    render(<SelectField label="Prism" options={[["", "All"], ["a", "Alpha"]]} value="a" onChange={onChange} />);
    const select = screen.getByRole("combobox", { name: "Prism" }) as HTMLSelectElement;
    expect(select).toHaveClass("workspace-select");
    expect(select.value).toBe("a");
    await userEvent.setup().selectOptions(select, "");
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("SearchField", async () => {
    const onChange = vi.fn();
    const { container } = render(<SearchField label="Search tasks…" value="" onChange={onChange} />);
    expect(container.firstElementChild).toHaveClass("workspace-search");
    const input = screen.getByRole("searchbox", { name: "Search tasks…" });
    expect(input).toHaveAttribute("placeholder", "Search tasks…");
    await userEvent.setup().type(input, "a");
    expect(onChange).toHaveBeenCalledWith("a");
  });

  it("Panel and Metric", () => {
    const { container } = render(
      <>
        <Panel title="T" subtitle="S" action={<button>act</button>}>
          <p>body</p>
        </Panel>
        <Metric title="Runs" value={3} detail="d" />
      </>,
    );
    const panel = container.querySelector("section.workspace-panel") as HTMLElement;
    expect(panel.querySelector(".workspace-panel-heading > div > h3")).toHaveTextContent("T");
    expect(panel.querySelector(".workspace-panel-heading > div > p.panel-note")).toHaveTextContent("S");
    expect(panel.querySelector(".workspace-panel-heading > button")).not.toBeNull();
    expect(panel.lastElementChild?.tagName).toBe("P");
    const metric = container.querySelector("article.workspace-metric") as HTMLElement;
    expect([...metric.children].map((c) => c.tagName.toLowerCase())).toEqual(["span", "svg", "strong", "small"]);
    expect(metric.querySelector("use")).toHaveAttribute("href", expect.stringContaining("#hash"));
  });
});
