import { useEffect, useRef, type CSSProperties, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import { Button } from "@/components/ui";
import { words } from "@/lib/format";
import type { OrgNode } from "@/lib/prism-organization";
import { uiZoom } from "@/lib/prefs";
import { departmentColor } from "./constants";
import {
  dragTransform,
  fitTransform,
  transformCss,
  viewportPoint,
  zoomTransform,
  type ChartTransform,
  type OrgLayout,
} from "./org-layout";

export interface OrgChartProps {
  layout: OrgLayout<OrgNode>;
  /** Every node, including hidden ones: the report counts ignore collapsing. */
  items: readonly OrgNode[];
  collapsed: ReadonlySet<string>;
  department: string;
  openPrism: (prismId: string) => void;
  toggle: (id: string) => void;
}

interface Drag {
  x: number;
  y: number;
  start: ChartTransform;
  pointerId: number;
}

const capitalize = (value: string) => value.replace(/^./, (letter) => letter.toUpperCase());

/** Pan, zoom and fit are done on the DOM nodes through refs: they run on every pointer move. */
export function OrgChart({ layout, items, collapsed, department, openPrism, toggle }: OrgChartProps) {
  const { graphWidth, graphHeight } = layout;
  const viewportRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const transform = useRef<ChartTransform>({ scale: 1, x: 0, y: 0 });
  const drag = useRef<Drag | null>(null);

  const apply = (next: ChartTransform) => {
    const stage = stageRef.current;
    if (!stage) return;
    transform.current = next;
    stage.dataset.scale = String(next.scale);
    stage.dataset.x = String(next.x);
    stage.dataset.y = String(next.y);
    stage.style.transform = transformCss(next);
  };
  const fit = () => {
    const viewport = viewportRef.current;
    if (viewport) apply(fitTransform(viewport.clientWidth, viewport.clientHeight, graphWidth, graphHeight));
  };
  const zoomAt = (factor: number, clientX: number | null = null, clientY: number | null = null) => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const rect = viewport.getBoundingClientRect();
    const point = viewportPoint({ x: clientX ?? rect.left + rect.width / 2, y: clientY ?? rect.top + rect.height / 2 }, rect, uiZoom());
    apply(zoomTransform(transform.current, factor, point.x, point.y));
  };
  const latest = useRef({ fit, zoomAt });
  latest.current = { fit, zoomAt };

  // Refit whenever the graph is rebuilt (the old code redrew the whole chart) and when the viewport resizes.
  useEffect(() => {
    const viewport = viewportRef.current;
    const frame = requestAnimationFrame(() => latest.current.fit());
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            if (viewport?.isConnected && viewport.clientWidth) latest.current.fit();
          });
    if (viewport) observer?.observe(viewport);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
    };
  }, [layout, department]);

  // React registers wheel listeners as passive, which would not let us stop the page from scrolling.
  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.deltaY) return;
      event.preventDefault();
      latest.current.zoomAt(event.deltaY < 0 ? 1.08 : 1 / 1.08, event.clientX, event.clientY);
    };
    viewport.addEventListener("wheel", onWheel, { passive: false });
    return () => viewport.removeEventListener("wheel", onWheel);
  }, []);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomAt(1.15);
    }
    if (event.key === "-") {
      event.preventDefault();
      zoomAt(1 / 1.15);
    }
    if (event.key === "0") {
      event.preventDefault();
      fit();
    }
    const delta = ({ ArrowLeft: [35, 0], ArrowRight: [-35, 0], ArrowUp: [0, 35], ArrowDown: [0, -35] } as Record<string, [number, number]>)[event.key];
    if (delta) {
      event.preventDefault();
      const current = transform.current;
      apply({ ...current, x: current.x + delta[0], y: current.y + delta[1] });
    }
  };

  const endDrag = (event?: { pointerId: number }) => {
    if (!drag.current || (event && drag.current.pointerId !== event.pointerId)) return;
    drag.current = null;
    viewportRef.current?.classList.remove("dragging");
  };
  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    const viewport = event.currentTarget;
    if (drag.current || event.button !== 0 || (event.target as Element).closest(".org-chart-controls, .org-node-actions")) return;
    viewport.dataset.dragged = "false";
    drag.current = { x: event.clientX, y: event.clientY, start: transform.current, pointerId: event.pointerId };
    viewport.classList.add("dragging");
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    const viewport = event.currentTarget;
    if (!current || current.pointerId !== event.pointerId) return;
    if (event.pointerType === "mouse" && !event.buttons) {
      endDrag();
      return;
    }
    if (Math.hypot(event.clientX - current.x, event.clientY - current.y) > 4) {
      viewport.dataset.dragged = "true";
      if (!viewport.hasPointerCapture(event.pointerId)) viewport.setPointerCapture(event.pointerId);
    }
    apply(dragTransform(current.start, current, { x: event.clientX, y: event.clientY }, uiZoom()));
  };

  const positions = [...layout.positions.values()];
  return (
    <div
      className="org-chart-viewport"
      role="region"
      aria-label="Organization chart. Drag to pan and scroll to zoom."
      tabIndex={0}
      ref={viewportRef}
      onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onLostPointerCapture={endDrag}
    >
      <div className="org-chart-stage" ref={stageRef} style={{ width: `${graphWidth}px`, height: `${graphHeight}px` }}>
        <svg className="org-chart-edges" width={graphWidth} height={graphHeight} viewBox={`0 0 ${graphWidth} ${graphHeight}`}>
          {layout.edges.map((edge, index) => (
            <path key={index} d={edge.d} stroke={edge.stroke} fill="none" strokeWidth="2" opacity="0.7" />
          ))}
        </svg>
        {positions.map(({ item, x, y }) => {
          const reports = items.filter((child) => child.parent_id === item.id).length;
          const isCollapsed = collapsed.has(item.id);
          const open = () => {
            if (item.prism_id) openPrism(item.prism_id);
          };
          const classes = [
            "org-position-card",
            item.prism_id ? "" : "org-owner-card",
            item.prism_id && department && item.department !== department ? "dimmed" : "",
          ]
            .filter(Boolean)
            .join(" ");
          const interactive = item.prism_id
            ? {
                tabIndex: 0,
                role: "button",
                "aria-label": `Open ${item.title}`,
                onClick: () => {
                  if (viewportRef.current?.dataset.dragged !== "true") open();
                },
                onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
                  if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) {
                    event.preventDefault();
                    open();
                  }
                },
              }
            : {};
          return (
            <article
              key={item.id}
              className={classes}
              style={{ left: `${x}px`, top: `${y}px`, ["--org-dept" as string]: departmentColor(item.department) } as CSSProperties}
              title={item.description || item.title || ""}
              {...interactive}
            >
              <strong className="org-position-title">{item.title || "Untitled position"}</strong>
              <span className="org-position-holder">{capitalize(words(item.state))}</span>
              <span className="org-position-tags">
                <span className="org-position-department">{item.department || "Organization"}</span>
                <span className="org-position-level">{words(item.level)}</span>
              </span>
              <div className="org-node-actions">
                {reports ? (
                  <Button
                    text={String(reports)}
                    glyph={isCollapsed ? "chevron-down" : "chevron-up"}
                    className="org-node-action"
                    title={isCollapsed ? "Show reports" : "Hide reports"}
                    aria-expanded={!isCollapsed}
                    onClick={(event) => {
                      event.stopPropagation();
                      toggle(item.id);
                    }}
                  />
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
      <div className="org-chart-controls">
        <Button glyph="zoom-in" className="org-chart-control" aria-label="Zoom in" onClick={() => zoomAt(1.15)} />
        <Button glyph="zoom-out" className="org-chart-control" aria-label="Zoom out" onClick={() => zoomAt(1 / 1.15)} />
        <Button glyph="maximize" className="org-chart-control" aria-label="Fit chart to view" onClick={fit} />
      </div>
      <div className="org-chart-hint">Drag to pan · scroll to zoom</div>
    </div>
  );
}
