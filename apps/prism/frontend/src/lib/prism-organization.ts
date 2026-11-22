// Persisted Prism metadata defines the team; the connected user is its only human node.
export interface OrgPrism {
  id?: string | null;
  name?: string | null;
  description?: string | null;
  state?: string | null;
  created_at?: string | null;
  is_chief_of_staff?: boolean | null;
  reports_to_prism_id?: string | null;
  department?: string | null;
  job_role?: string | null;
}

export interface OrgNode {
  id: string;
  prism_id: string | null;
  kind: "owner" | "prism";
  title: string;
  description: string | null | undefined;
  state: string;
  parent_id: string | null;
  department: string;
  level: string;
  holder_type: "human" | "agent";
  holder_name: string;
  is_chief_of_staff?: boolean;
}

export const OWNER_NODE_ID = "prism-owner";

type IdentifiedPrism = OrgPrism & { id: string };

export function prismOrganization(
  prisms: readonly OrgPrism[],
  _agents: readonly unknown[] = [],
  _positions: readonly unknown[] = [],
  ownerName = "You",
): OrgNode[] {
  const ownerId = OWNER_NODE_ID;
  const owned = [
    ...new Map(
      prisms
        .filter((prism): prism is IdentifiedPrism => Boolean(prism.id) && String(prism.state).toLowerCase() !== "archived")
        .map((prism) => [prism.id, prism] as const),
    ).values(),
  ].sort(
    (a, b) =>
      Number(Boolean(b.is_chief_of_staff)) - Number(Boolean(a.is_chief_of_staff)) ||
      String(a.created_at || "").localeCompare(String(b.created_at || "")) ||
      String(a.id).localeCompare(String(b.id)),
  );
  const chief = owned.find((prism) => prism.is_chief_of_staff);
  const ids = new Set(owned.map((prism) => prism.id));
  const nodes: OrgNode[] = owned.map((prism) => {
    const manager = prism.reports_to_prism_id;
    const fallback = chief && chief.id !== prism.id ? chief.id : ownerId;
    return {
      id: prism.id,
      prism_id: prism.id,
      kind: "prism",
      title: prism.name as string,
      description: prism.description,
      state: String(prism.state || "draft").toLowerCase(),
      parent_id: prism.is_chief_of_staff ? ownerId : manager && ids.has(manager) && manager !== prism.id ? manager : fallback,
      department: prism.department || "Operations",
      level: prism.job_role || "Prism Specialist",
      holder_type: "agent",
      holder_name: "",
      is_chief_of_staff: Boolean(prism.is_chief_of_staff),
    };
  });
  const byId = new Map(nodes.map((node) => [node.id, node]));
  for (const node of nodes) {
    const seen = new Set([node.id]);
    let parent = node.parent_id;
    while (parent && parent !== ownerId) {
      if (seen.has(parent)) {
        node.parent_id = chief && chief.id !== node.id ? chief.id : ownerId;
        break;
      }
      seen.add(parent);
      parent = byId.get(parent)?.parent_id ?? null;
    }
  }
  return [
    {
      id: ownerId,
      prism_id: null,
      kind: "owner",
      title: ownerName || "You",
      description: "Your AI employee team",
      state: "owner",
      parent_id: null,
      department: "Leadership",
      level: "Team Owner",
      holder_type: "human",
      holder_name: ownerName || "You",
    },
    ...nodes,
  ];
}
