import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataTable, TitleCell } from "./index";

describe("DataTable", () => {
  it("renders headers with scope=col and numeric classes", () => {
    const { container } = render(<DataTable headers={["Name", "Runs", "Success rate", "Cost"]} rows={[]} className="extra" />);
    expect(container.firstElementChild).toHaveClass("workspace-table-wrap", "extra");
    const heads = screen.getAllByRole("columnheader");
    expect(heads.map((h) => h.textContent)).toEqual(["Name", "Runs", "Success rate", "Cost"]);
    expect(heads.map((h) => h.classList.contains("numeric"))).toEqual([false, true, true, true]);
    expect(heads.every((h) => h.getAttribute("scope") === "col")).toBe(true);
    expect(container.querySelector("table")).toHaveClass("workspace-table");
  });

  it("renders cells, em dash for empty, and numeric alignment", () => {
    render(<DataTable headers={["Task", "Tokens"]} rows={[["A", 12], ["B", null], [<TitleCell key="t" title="T" subtitle="s" />, undefined]]} />);
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(4);
    const cells = within(rows[2]).getAllByRole("cell");
    expect(cells.map((c) => c.textContent)).toEqual(["B", "—"]);
    expect(cells[1]).toHaveClass("numeric");
    expect(cells[0]).not.toHaveClass("numeric");
    expect(within(rows[3]).getAllByRole("cell")[0].querySelector(".workspace-title-cell")).not.toBeNull();
  });

  it("renders group separator rows spanning all columns", () => {
    const { container } = render(<DataTable headers={["a", "b", "c"]} rows={[{ group: "Today · 2 runs" }, ["1", "2", "3"]]} />);
    const group = container.querySelector("tr.workspace-date-group > th");
    expect(group).toHaveTextContent("Today · 2 runs");
    expect(group).toHaveAttribute("colspan", "3");
    expect(group).toHaveAttribute("scope", "rowgroup");
  });

  it("supports cells rows with a class", () => {
    const { container } = render(<DataTable headers={["a"]} rows={[{ cells: ["x"], className: "hot", key: "k" }]} />);
    expect(container.querySelector("tbody tr")).toHaveClass("hot");
  });

  it("renders untrusted text as text", () => {
    const { container } = render(<DataTable headers={["a"]} rows={[["<img src=x onerror=alert(1)>"]]} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("td")?.textContent).toBe("<img src=x onerror=alert(1)>");
  });
});

describe("TitleCell", () => {
  it("renders strong without an action and a text-link button with one", async () => {
    const calls: string[] = [];
    const { container, rerender } = render(<TitleCell title="Plain" subtitle="sub" />);
    expect(container.querySelector(".workspace-title-cell > strong")).toHaveTextContent("Plain");
    expect(container.querySelector(".workspace-title-cell > span")).toHaveTextContent("sub");
    rerender(<TitleCell title="Link" onClick={() => calls.push("x")} />);
    const button = screen.getByRole("button", { name: "Link" });
    expect(button).toHaveClass("workspace-text-link");
    button.click();
    expect(calls).toEqual(["x"]);
    expect(container.querySelector(".workspace-title-cell > span")).toBeNull();
  });
});
