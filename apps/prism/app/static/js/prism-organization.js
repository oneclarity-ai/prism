// Persisted Prism metadata defines the team; the connected user is its only human node.
export function prismOrganization(prisms, _agents = [], _positions = [], ownerName = "You") {
  const owned = [...new Map(prisms.filter((prism) => prism.id && String(prism.state).toLowerCase() !== "archived").map((prism) => [prism.id, prism])).values()]
    .sort((a, b) => Number(Boolean(b.is_chief_of_staff)) - Number(Boolean(a.is_chief_of_staff)) || String(a.created_at || "").localeCompare(String(b.created_at || "")) || String(a.id).localeCompare(String(b.id)));
  const ownerId = "prism-owner";
  const chief = owned.find((prism) => prism.is_chief_of_staff);
  const ids = new Set(owned.map((prism) => prism.id));
  const nodes = owned.map((prism) => {
    const manager = prism.reports_to_prism_id;
    const fallback = chief && chief.id !== prism.id ? chief.id : ownerId;
    return {
      id: prism.id, prism_id: prism.id, kind: "prism", title: prism.name, description: prism.description,
      state: String(prism.state || "draft").toLowerCase(),
      parent_id: prism.is_chief_of_staff ? ownerId : manager && ids.has(manager) && manager !== prism.id ? manager : fallback,
      department: prism.department || "Operations", level: prism.job_role || "Prism Specialist",
      holder_type: "agent", holder_name: "", is_chief_of_staff: Boolean(prism.is_chief_of_staff),
    };
  });
  const byId = new Map(nodes.map((node) => [node.id, node]));
  for (const node of nodes) {
    const seen = new Set([node.id]);
    let parent = node.parent_id;
    while (parent && parent !== ownerId) {
      if (seen.has(parent)) { node.parent_id = chief && chief.id !== node.id ? chief.id : ownerId; break; }
      seen.add(parent);
      parent = byId.get(parent)?.parent_id;
    }
  }
  return [{ id: ownerId, prism_id: null, kind: "owner", title: ownerName || "You", description: "Your AI employee team",
    state: "owner", parent_id: null, department: "Leadership", level: "Team Owner", holder_type: "human", holder_name: ownerName || "You" }, ...nodes];
}
