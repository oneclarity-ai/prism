import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ColorPicker, PrismLogo, PrismLogoIcon } from "./index";

describe("PrismLogo", () => {
  it("wraps the svg in a span with the colour key", () => {
    const { container } = render(<PrismLogo prism={{ name: "x", color: "blue" }} className="prism-logo nav-logo" />);
    const span = container.firstElementChild as HTMLElement;
    expect(span.tagName).toBe("SPAN");
    expect(span.className).toBe("prism-logo nav-logo");
    expect(span.dataset.color).toBe("blue");
    expect(span.querySelector("svg")).toHaveAttribute("viewBox", "0 0 200 200");
  });

  it("defaults the class, prefers colorKey, and gives each logo unique gradient ids", () => {
    const { container } = render(
      <>
        <PrismLogo colorKey="pink" prism={{ color: "red" }} />
        <PrismLogo colorKey="pink" />
      </>,
    );
    const spans = [...container.querySelectorAll("span.prism-logo")] as HTMLElement[];
    expect(spans.map((s) => s.dataset.color)).toEqual(["pink", "pink"]);
    const ids = [...container.querySelectorAll("linearGradient, clipPath")].map((n) => n.id);
    expect(ids).toHaveLength(12);
    expect(new Set(ids).size).toBe(12);
    const clip = container.querySelector("svg g")?.getAttribute("clip-path") ?? "";
    expect(container.querySelector(`[id="${clip.slice(5, -1)}"]`)?.tagName.toLowerCase()).toBe("clippath");
  });

  it("renders the bare icon", () => {
    const { container } = render(<PrismLogoIcon colorKey="purple" />);
    expect(container.firstElementChild?.tagName.toLowerCase()).toBe("svg");
    expect(container.querySelectorAll("stop").length).toBeGreaterThan(8);
  });
});

describe("ColorPicker", () => {
  it("renders eight labelled radio swatches with the selected one checked", () => {
    const { container } = render(<ColorPicker selected="green" onPick={() => {}} name="editor-color" />);
    expect(screen.getByRole("radiogroup", { name: "Prism colour" })).toHaveClass("color-picker");
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios).toHaveLength(8);
    expect(radios.every((r) => r.name === "editor-color")).toBe(true);
    expect(radios.filter((r) => r.checked).map((r) => r.value)).toEqual(["green"]);
    expect((screen.getByRole("radio", { name: "Teal" }) as HTMLInputElement).value).toBe("teal");
    const label = container.querySelector("label.color-swatch") as HTMLElement;
    expect(label.title).toBe("Red");
    expect(label.style.getPropertyValue("--swatch")).toBe("#EF4444");
  });

  it("defaults the group name and calls onPick with the key", async () => {
    const onPick = vi.fn();
    render(<ColorPicker selected="red" onPick={onPick} />);
    expect((screen.getAllByRole("radio")[0] as HTMLInputElement).name).toBe("prism-color");
    await userEvent.setup().click(screen.getByRole("radio", { name: "Blue" }));
    expect(onPick).toHaveBeenCalledWith("blue");
  });
});
