import { describe, expect, it } from "vitest";
import { departmentColor } from "./constants";
import { dragTransform, fitTransform, layoutOrganization, NODE_WIDTH, viewportPoint, zoomTransform, type OrgLayoutItem } from "./org-layout";

const node = (id: string, parent: string | null, department = "Sales"): OrgLayoutItem => ({ id, parent_id: parent, department });

describe("layoutOrganization", () => {
  it("returns null for an empty list", () => {
    expect(layoutOrganization([], new Set())).toBeNull();
  });

  it("centres a parent over its children and levels by depth", () => {
    const layout = layoutOrganization([node("root", null), node("a", "root"), node("b", "root")], new Set());
    const p = layout!.positions;
    expect(p.get("a")!.x).toBe(40);
    expect(p.get("b")!.x).toBe(40 + NODE_WIDTH + 36);
    expect(p.get("root")!.x).toBe((p.get("a")!.x + p.get("b")!.x) / 2);
    expect(p.get("root")!.y).toBe(40);
    expect(p.get("a")!.y).toBe(40 + 112 + 78);
    expect(layout!.edges).toHaveLength(2);
    expect(layout!.edges[0].stroke).toBe(departmentColor("Sales"));
  });

  it("hides everything below a collapsed node", () => {
    const layout = layoutOrganization([node("root", null), node("a", "root"), node("b", "a")], new Set(["a"]));
    expect([...layout!.positions.keys()].sort()).toEqual(["a", "root"]);
  });

  it("keeps cyclic data visible", () => {
    const layout = layoutOrganization([node("a", "b"), node("b", "a")], new Set());
    expect(layout!.positions.size).toBe(2);
  });
});

describe("transforms", () => {
  it("fit clamps the scale and centres", () => {
    const fit = fitTransform(1000, 800, 500, 300);
    expect(fit.scale).toBe(1.1);
    expect(fit.x).toBeCloseTo((1000 - 500 * 1.1) / 2);
  });

  it("zoom keeps the anchor point fixed and clamps", () => {
    const z = zoomTransform({ scale: 1, x: 10, y: 20 }, 1.5, 110, 120);
    expect(z).toEqual({ scale: 1.5, x: -40, y: -30 });
    expect(zoomTransform({ scale: 1.7, x: 0, y: 0 }, 2, 0, 0).scale).toBe(1.8);
  });

  it("divides visual pointer coordinates by the ui zoom", () => {
    expect(viewportPoint({ x: 300, y: 200 }, { left: 100, top: 50 }, 2)).toEqual({ x: 100, y: 75 });
    expect(dragTransform({ scale: 1, x: 0, y: 0 }, { x: 10, y: 10 }, { x: 110, y: 30 }, 2)).toEqual({ scale: 1, x: 50, y: 10 });
  });
});
