import { describe, expect, it } from "vitest";
import { prismOrganization, type OrgNode, type OrgPrism } from "./prism-organization";

const chief = "11111111-0000-0000-0000-000000000001";
const worker = "22222222-0000-0000-0000-000000000002";
const draft = "33333333-0000-0000-0000-000000000003";
const prisms: OrgPrism[] = [
  { id: chief, name: "Chief of Staff", state: "active", is_chief_of_staff: true, job_role: "Chief of Staff", department: "Leadership", reports_to_prism_id: null },
  { id: worker, name: "Research Prism", state: "paused", job_role: "AI Researcher", department: "Research & Development", reports_to_prism_id: chief },
  { id: draft, name: "New Prism", state: "draft", job_role: "Marketing Specialist", department: "Marketing", reports_to_prism_id: chief },
  { id: "44444444-0000-0000-0000-000000000004", name: "Archived", state: "ARCHIVED" },
];
const agents = [{ id: "unrelated", key: "seeded-qa", name: "New Prism" }];
const positions = [{ id: "ceo", title: "CEO", holder_type: "human" }, { id: "vacant", holder_type: "vacant" }];

describe("prismOrganization", () => {
  const chart = prismOrganization(prisms, agents, positions, "Yash");

  it("lists the owner then actual non-archived Prisms with reporting links", () => {
    expect(chart.map((n) => n.title)).toEqual(["Yash", "Chief of Staff", "Research Prism", "New Prism"]);
    expect(chart[0].kind).toBe("owner");
    expect(chart[0].prism_id).toBeNull();
    expect(chart[1].parent_id).toBe(chart[0].id);
    expect(chart[2].parent_id).toBe(chief);
    expect(chart[3].parent_id).toBe(chief);
    expect(chart[2].department).toBe("Research & Development");
    expect(chart[3].department).toBe("Marketing");
  });

  it("ignores input order, engine agents and positions", () => {
    expect(prismOrganization([...prisms].reverse(), agents, positions, "Yash")).toEqual(chart);
    expect(prismOrganization(prisms, [], [], "Yash")).toEqual(chart);
  });

  it("shows only the owner for an empty team and defaults the owner name", () => {
    expect(prismOrganization([], agents, positions, "Yash")).toHaveLength(1);
    expect(prismOrganization([])[0].title).toBe("You");
  });

  it("falls back to the Chief of Staff for missing managers", () => {
    const orphan = prismOrganization([prisms[0], { ...prisms[2], reports_to_prism_id: "missing" }]);
    expect(orphan[2].parent_id).toBe(chief);
  });

  it("falls back to the owner without a Chief of Staff, and fills in defaults", () => {
    const [, only] = prismOrganization([{ id: "x", name: "Solo" }]);
    expect(only.parent_id).toBe("prism-owner");
    expect(only.department).toBe("Operations");
    expect(only.level).toBe("Prism Specialist");
    expect(only.state).toBe("draft");
  });

  it("deduplicates by id and ignores records without one", () => {
    const rows = prismOrganization([prisms[0], prisms[0], { name: "no id" }]);
    expect(rows.map((n) => n.id)).toEqual(["prism-owner", chief]);
  });

  it("breaks reporting cycles", () => {
    const cycle = prismOrganization([
      prisms[0],
      { ...prisms[1], reports_to_prism_id: draft },
      { ...prisms[2], reports_to_prism_id: worker },
    ]);
    const byId = new Map<string, OrgNode>(cycle.map((n) => [n.id, n]));
    for (const node of cycle) {
      const seen = new Set([node.id]);
      let parent = node.parent_id;
      while (parent) {
        expect(seen.has(parent)).toBe(false);
        seen.add(parent);
        parent = byId.get(parent)?.parent_id ?? null;
      }
    }
  });
});
