import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Tabs } from "./index";

const options = [
  ["all", "All", 5],
  ["running", "Running", 2],
  ["custom", "Custom", undefined],
] as const;

describe("Tabs", () => {
  it("renders a labelled group of aria-pressed buttons with counts", () => {
    const { container } = render(<Tabs options={options} value="running" onChange={() => {}} />);
    const group = screen.getByRole("group", { name: "Filter by status" });
    expect(group).toHaveClass("workspace-status-tabs");
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((b) => b.getAttribute("aria-pressed"))).toEqual(["false", "true", "false"]);
    expect(buttons[1]).toHaveClass("workspace-status-tab", "active");
    expect(buttons[0]).not.toHaveClass("active");
    expect(buttons[0].querySelector(".workspace-tab-count")).toHaveTextContent("5");
    expect(buttons[2].querySelector(".workspace-tab-count")).toBeEmptyDOMElement();
    expect(container.querySelector("svg")).toBeNull();
    expect(buttons[0].children[0].tagName).toBe("SPAN");
  });

  it("prefixes status icons only for known statuses when showIcons", () => {
    render(<Tabs options={options} value="all" onChange={() => {}} showIcons />);
    const buttons = screen.getAllByRole("button");
    expect(buttons[0].querySelector("svg")).toBeNull();
    const use = buttons[1].querySelector("svg use");
    expect(use).toHaveAttribute("href", "/dashboard/assets/workspace-icons.svg#loader-circle");
    expect(buttons[1].firstElementChild?.tagName.toLowerCase()).toBe("svg");
  });

  it("calls onChange on click and on keyboard activation", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Tabs options={options} value="all" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /Running/ }));
    expect(onChange).toHaveBeenLastCalledWith("running");
    await user.tab();
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledTimes(2);
  });
});
