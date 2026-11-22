import { departmentColor } from "./constants";

export const NODE_WIDTH = 250;
export const NODE_HEIGHT = 112;
const HORIZONTAL_GAP = 36;
const VERTICAL_GAP = 78;

export const MIN_SCALE = 0.2;
export const MAX_SCALE = 1.8;
export const FIT_MAX_SCALE = 1.1;

export interface OrgLayoutItem {
  id: string;
  parent_id: string | null;
  department?: string | null;
  sort_order?: number | string | null;
}

export interface PlacedItem<T extends OrgLayoutItem> {
  item: T;
  x: number;
  y: number;
}

export interface OrgEdge {
  d: string;
  stroke: string;
}

export interface OrgLayout<T extends OrgLayoutItem> {
  positions: Map<string, PlacedItem<T>>;
  edges: OrgEdge[];
  graphWidth: number;
  graphHeight: number;
}

/** Ids of every item below a collapsed item. */
export function hiddenByCollapse(items: readonly OrgLayoutItem[], collapsed: ReadonlySet<string>): Set<string> {
  const hidden = new Set<string>();
  const queue = items.filter((item) => item.parent_id !== null && collapsed.has(item.parent_id)).map((item) => item.id);
  for (let i = 0; i < queue.length; i++) {
    if (hidden.has(queue[i])) continue;
    hidden.add(queue[i]);
    for (const child of items) if (child.parent_id === queue[i]) queue.push(child.id);
  }
  return hidden;
}

/**
 * Tidy-tree layout: leaves take the next free column, parents centre over their children.
 * Returns null for an empty list. Cyclic data stays visible (every unvisited item becomes a root).
 */
export function layoutOrganization<T extends OrgLayoutItem>(all: readonly T[], collapsed: ReadonlySet<string>): OrgLayout<T> | null {
  if (!all.length) return null;
  const hidden = hiddenByCollapse(all, collapsed);
  const visibleItems = all.filter((item) => !hidden.has(item.id));
  // Invalid cyclic data must remain inspectable, even if every node was collapsed.
  const items = visibleItems.length ? visibleItems : all;
  const ids = new Set(items.map((item) => item.id));
  const children = new Map<string | null, T[]>();
  for (const item of items) {
    const parent = item.parent_id !== null && ids.has(item.parent_id) ? item.parent_id : null;
    const list = children.get(parent) ?? [];
    list.push(item);
    children.set(parent, list);
  }
  for (const list of children.values()) list.sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0));

  const visited = new Set<string>();
  const positions = new Map<string, PlacedItem<T>>();
  let cursor = 40;
  const place = (item: T, depth: number): number | null => {
    if (visited.has(item.id)) return null;
    visited.add(item.id);
    const childCenters = (children.get(item.id) ?? []).map((child) => place(child, depth + 1)).filter((center): center is number => center !== null);
    let x: number;
    if (childCenters.length) {
      x = (childCenters[0] + childCenters[childCenters.length - 1]) / 2 - NODE_WIDTH / 2;
    } else {
      x = cursor;
      cursor += NODE_WIDTH + HORIZONTAL_GAP;
    }
    positions.set(item.id, { item, x, y: 40 + depth * (NODE_HEIGHT + VERTICAL_GAP) });
    return x + NODE_WIDTH / 2;
  };
  for (const item of [...(children.get(null) ?? [])]) {
    place(item, 0);
    cursor += HORIZONTAL_GAP;
  }
  // A cycle can leave every position without a root. Keep those records visible.
  for (const item of items) {
    if (!visited.has(item.id)) {
      const center = place(item, 0);
      if (center !== null) cursor += HORIZONTAL_GAP;
    }
  }

  const maxDepth = Math.max(...[...positions.values()].map(({ y }) => (y - 40) / (NODE_HEIGHT + VERTICAL_GAP)));
  const graphWidth = Math.max(cursor, NODE_WIDTH + 80);
  const graphHeight = 80 + maxDepth * (NODE_HEIGHT + VERTICAL_GAP) + NODE_HEIGHT;

  const edges: OrgEdge[] = [];
  for (const { item, x, y } of positions.values()) {
    const parent = item.parent_id === null ? undefined : positions.get(item.parent_id);
    if (!parent) continue;
    const startX = parent.x + NODE_WIDTH / 2;
    const startY = parent.y + NODE_HEIGHT;
    const endX = x + NODE_WIDTH / 2;
    const midY = (startY + y) / 2;
    edges.push({ d: `M ${startX} ${startY} V ${midY} H ${endX} V ${y}`, stroke: departmentColor(item.department) });
  }
  return { positions, edges, graphWidth, graphHeight };
}

export interface ChartTransform {
  scale: number;
  x: number;
  y: number;
}

export function fitTransform(viewportWidth: number, viewportHeight: number, graphWidth: number, graphHeight: number): ChartTransform {
  const scale = Math.max(MIN_SCALE, Math.min(FIT_MAX_SCALE, (viewportWidth - 64) / graphWidth, (viewportHeight - 64) / graphHeight));
  return { scale, x: (viewportWidth - graphWidth * scale) / 2, y: (viewportHeight - graphHeight * scale) / 2 };
}

/** Zoom by `factor` keeping the viewport point (px, py), in layout pixels, fixed. */
export function zoomTransform(current: ChartTransform, factor: number, px: number, py: number): ChartTransform {
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, current.scale * factor));
  return { scale, x: px - ((px - current.x) * scale) / current.scale, y: py - ((py - current.y) * scale) / current.scale };
}

/**
 * Pointer position inside the viewport in layout pixels. Visual coordinates are divided by the UI zoom
 * (`uiZoom()`), because the page is scaled with CSS zoom while pointer events stay visual.
 */
export function viewportPoint(client: { x: number; y: number }, rect: { left: number; top: number }, zoom: number): { x: number; y: number } {
  return { x: (client.x - rect.left) / zoom, y: (client.y - rect.top) / zoom };
}

/** Pan: start position plus the visual pointer travel in layout pixels. */
export function dragTransform(start: ChartTransform, origin: { x: number; y: number }, client: { x: number; y: number }, zoom: number): ChartTransform {
  return { scale: start.scale, x: start.x + (client.x - origin.x) / zoom, y: start.y + (client.y - origin.y) / zoom };
}

export const transformCss = ({ scale, x, y }: ChartTransform): string => `translate(${x}px, ${y}px) scale(${scale})`;
