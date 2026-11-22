import { Button, Metric } from "@/components/ui";
import type { OrgNode } from "@/lib/prism-organization";
import { OrgChart } from "../OrgChart";
import { departmentColor } from "../constants";
import { layoutOrganization } from "../org-layout";

export interface OrganizationPageProps {
  items: readonly OrgNode[];
  department: string;
  setDepartment: (department: string) => void;
  collapsed: ReadonlySet<string>;
  setCollapsed: (next: ReadonlySet<string>) => void;
  openPrism: (prismId: string) => void;
}

/** The org chart view of the Prisms page ("positions"): counts, department filters and the chart. */
export function OrganizationPage({ items, department, setDepartment, collapsed, setCollapsed, openPrism }: OrganizationPageProps) {
  const prisms = items.filter((item) => item.kind === "prism");
  const layout = layoutOrganization(items, collapsed);
  const departments = [...new Set(prisms.map((item) => item.department).filter(Boolean))];
  const toggle = (id: string) => {
    const next = new Set(collapsed);
    if (!next.delete(id)) next.add(id);
    setCollapsed(next);
  };
  return (
    <>
      <div className="workspace-metrics four">
        <Metric title="Prisms" value={prisms.length} glyph="network" />
        <Metric title="Active" value={prisms.filter((item) => item.state === "active").length} glyph="bot" />
        <Metric title="Setting up" value={prisms.filter((item) => !["active", "paused"].includes(item.state)).length} glyph="clock" />
        <Metric title="Paused" value={prisms.filter((item) => item.state === "paused").length} glyph="circle-dashed" />
      </div>
      <div className="workspace-toolbar org-department-filters">
        <Button text="All departments" glyph="users" className={`mini-button${department ? "" : " active"}`} onClick={() => setDepartment("")} />
        {departments.map((name) => (
          <button
            key={name}
            type="button"
            className={`mini-button${department === name ? " active" : ""}`}
            aria-pressed={department === name}
            onClick={() => setDepartment(department === name ? "" : name)}
          >
            <span className="workspace-department-dot" style={{ background: departmentColor(name) }} />
            <span>{`${name} ${prisms.filter((item) => item.department === name).length}`}</span>
          </button>
        ))}
        <Button text="Expand all" onClick={() => setCollapsed(new Set())} />
        <Button
          text="Collapse"
          onClick={() => {
            const next = new Set(collapsed);
            items.filter((item) => item.parent_id && items.some((child) => child.parent_id === item.id)).forEach((item) => next.add(item.id));
            setCollapsed(next);
          }}
        />
      </div>
      {layout ? (
        <OrgChart layout={layout} items={items} collapsed={collapsed} department={department} openPrism={openPrism} toggle={toggle} />
      ) : (
        <p className="operations-empty">No Prisms yet. Create a Prism to see it here.</p>
      )}
    </>
  );
}
