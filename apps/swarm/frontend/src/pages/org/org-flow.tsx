import dagre from '@dagrejs/dagre'
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position as Side,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Bot, ChevronDown, ChevronUp, CircleDashed, Crown, Plus, User } from 'lucide-react'
import { motion } from 'motion/react'
import { useTheme } from 'next-themes'
import { createContext, memo, useContext, useEffect, useMemo } from 'react'

import type { Position } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { LEVELS, deptTone } from '@/lib/org'
import { cn } from '@/lib/utils'

const NODE_W = 260
const NODE_H = 128

// Hex colours per department, for edges and the minimap (the cards use Tailwind classes).
const DEPT_HEX: Record<string, string> = {
  Leadership: '#8b5cf6',
  Technology: '#0ea5e9',
  Sales: '#10b981',
  Marketing: '#ec4899',
  'Customer Success': '#f59e0b',
  Operations: '#64748b',
  Finance: '#14b8a6',
  People: '#f97316',
}
const hex = (dept: string) => DEPT_HEX[dept] ?? '#6366f1'

type Actions = {
  onEdit: (p: Position) => void
  onAddChild: (p: Position) => void
  onToggle: (id: string) => void
  agentName: (id?: string | null) => string | undefined
  roleName: (key?: string | null) => string | undefined
}
const ActionsContext = createContext<Actions | null>(null)

type CardData = {
  position: Position
  depth: number
  childCount: number
  collapsed: boolean
  dimmed: boolean
}
type CardNode = Node<CardData, 'position'>

/** One seat in the chart. Fades and rises in level by level; AI agents get a soft pulsing ring. */
const PositionCard = memo(function PositionCard({ data }: NodeProps<CardNode>) {
  const actions = useContext(ActionsContext)!
  const p = data.position
  const tone = deptTone(p.department)
  const level = LEVELS.find((l) => l.value === p.level)?.label
  const Icon = p.level === 'ceo' ? Crown : p.holder_type === 'agent' ? Bot : p.holder_type === 'human' ? User : CircleDashed
  const holder =
    p.holder_type === 'agent'
      ? (actions.agentName(p.agent_id) ?? 'Agent not assigned')
      : p.holder_type === 'human'
        ? p.holder_name || 'Unnamed person'
        : 'Vacant'

  return (
    <motion.div
      initial={{ opacity: 0, y: 18, scale: 0.94 }}
      animate={{ opacity: data.dimmed ? 0.3 : 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 260, damping: 24, delay: data.depth * 0.09 }}
      whileHover={{ y: -4 }}
      className="group relative"
      style={{ width: NODE_W }}
    >
      <Handle type="target" position={Side.Top} className="!size-1.5 !border-0 !bg-transparent" />
      <button
        type="button"
        onClick={() => actions.onEdit(p)}
        className={cn(
          'bg-card relative w-full overflow-hidden rounded-2xl border text-left shadow-sm transition-shadow duration-300 group-hover:shadow-xl',
          p.holder_type === 'vacant' && 'border-dashed',
        )}
        style={{ boxShadow: p.level === 'ceo' ? `0 10px 30px -12px ${hex(p.department)}66` : undefined }}
      >
        <div className={cn('h-1.5 w-full', tone.bar)} />
        <div className="flex gap-3 p-3.5">
          <div className="relative shrink-0">
            {p.holder_type === 'agent' && (
              <motion.span
                className="absolute inset-0 rounded-full bg-violet-500"
                animate={{ scale: [1, 1.45], opacity: [0.45, 0] }}
                transition={{ duration: 2.2, repeat: Infinity, ease: 'easeOut' }}
              />
            )}
            <div
              className={cn(
                'relative flex size-11 items-center justify-center rounded-full',
                p.holder_type === 'agent'
                  ? 'bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-md shadow-violet-500/30'
                  : p.holder_type === 'human'
                    ? 'bg-primary/10 text-primary'
                    : 'bg-muted text-muted-foreground border border-dashed',
                p.level === 'ceo' && p.holder_type !== 'agent' && 'bg-gradient-to-br from-violet-500/20 to-fuchsia-500/20 text-violet-600',
              )}
            >
              <Icon className="size-5" />
            </div>
          </div>
          <div className="min-w-0 flex-1">
            <div className="line-clamp-2 text-sm leading-snug font-semibold">{p.title}</div>
            <div className={cn('truncate text-xs', p.holder_type === 'vacant' && 'text-muted-foreground italic')}>
              {holder}
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1">
              <Badge className={cn('h-4 border-0 px-1.5 text-[10px]', tone.chip)}>{p.department}</Badge>
              <Badge variant="outline" className="h-4 px-1.5 text-[10px]">
                {level}
              </Badge>
            </div>
            {p.holder_type === 'vacant' && p.planned_agent_key && (
              <div className="text-muted-foreground mt-1 flex items-center gap-1 truncate text-[10px]">
                <Bot className="size-3" /> planned: {actions.roleName(p.planned_agent_key) ?? p.planned_agent_key}
              </div>
            )}
          </div>
        </div>
      </button>

      <div className="nodrag absolute -bottom-3.5 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1">
        <motion.button
          type="button"
          title="Add someone reporting here"
          onClick={() => actions.onAddChild(p)}
          className="bg-primary text-primary-foreground flex size-6 items-center justify-center rounded-full opacity-0 shadow transition-opacity group-hover:opacity-100"
          whileTap={{ scale: 0.85 }}
        >
          <Plus className="size-3.5" />
        </motion.button>
        {data.childCount > 0 && (
          <motion.button
            type="button"
            title={data.collapsed ? 'Show reports' : 'Hide reports'}
            onClick={() => actions.onToggle(p.id)}
            className="bg-background text-muted-foreground hover:text-foreground flex h-6 items-center gap-0.5 rounded-full border px-2 text-[10px] shadow-sm"
            whileTap={{ scale: 0.9 }}
          >
            {data.collapsed ? <ChevronDown className="size-3" /> : <ChevronUp className="size-3" />}
            {data.childCount}
          </motion.button>
        )}
      </div>
      <Handle type="source" position={Side.Bottom} className="!size-1.5 !border-0 !bg-transparent" />
    </motion.div>
  )
})

const nodeTypes = { position: PositionCard }

function layout(positions: Position[], collapsed: Set<string>, focusDept: string | null) {
  const byParent = new Map<string | null, Position[]>()
  positions.forEach((p) => {
    const key = p.parent_id && positions.some((x) => x.id === p.parent_id) ? p.parent_id : null
    byParent.set(key, [...(byParent.get(key) ?? []), p])
  })
  for (const list of byParent.values())
    list.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.created_at.localeCompare(b.created_at))

  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'TB', nodesep: 36, ranksep: 70, marginx: 20, marginy: 20 })
  g.setDefaultEdgeLabel(() => ({}))

  const visible: { p: Position; depth: number }[] = []
  const edges: Edge[] = []
  const walk = (p: Position, depth: number) => {
    visible.push({ p, depth })
    g.setNode(p.id, { width: NODE_W, height: NODE_H })
    if (collapsed.has(p.id)) return
    for (const c of byParent.get(p.id) ?? []) {
      g.setEdge(p.id, c.id)
      const color = hex(c.department)
      edges.push({
        id: `${p.id}-${c.id}`,
        source: p.id,
        target: c.id,
        type: 'smoothstep',
        animated: c.holder_type === 'agent',
        style: {
          stroke: color,
          strokeWidth: 2,
          opacity: focusDept && c.department !== focusDept ? 0.15 : 0.7,
        },
      })
      walk(c, depth + 1)
    }
  }
  ;(byParent.get(null) ?? []).forEach((r) => walk(r, 0))
  dagre.layout(g)

  const nodes: CardNode[] = visible.map(({ p, depth }) => {
    const n = g.node(p.id)
    return {
      id: p.id,
      type: 'position',
      position: { x: n.x - NODE_W / 2, y: n.y - NODE_H / 2 },
      draggable: false,
      data: {
        position: p,
        depth,
        childCount: byParent.get(p.id)?.length ?? 0,
        collapsed: collapsed.has(p.id),
        dimmed: !!focusDept && p.department !== focusDept,
      },
    }
  })
  return { nodes, edges }
}

function Flow({
  positions,
  collapsed,
  focusDept,
}: {
  positions: Position[]
  collapsed: Set<string>
  focusDept: string | null
}) {
  const { resolvedTheme } = useTheme()
  const { fitView } = useReactFlow()
  const { nodes, edges } = useMemo(() => layout(positions, collapsed, focusDept), [positions, collapsed, focusDept])

  // Smoothly re-frame when the chart changes shape or a department is selected.
  useEffect(() => {
    const ids = focusDept ? nodes.filter((n) => n.data.position.department === focusDept).map((n) => ({ id: n.id })) : undefined
    const t = setTimeout(() => fitView({ nodes: ids?.length ? ids : undefined, padding: 0.15, duration: 700, maxZoom: 1.1 }), 60)
    return () => clearTimeout(t)
  }, [nodes, focusDept, fitView])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      colorMode={resolvedTheme === 'dark' ? 'dark' : 'light'}
      fitView
      fitViewOptions={{ padding: 0.15, maxZoom: 1.1 }}
      minZoom={0.2}
      maxZoom={1.8}
      nodesConnectable={false}
      proOptions={{ hideAttribution: true }}
      className="!bg-transparent"
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.4} />
      <Controls showInteractive={false} position="top-right" />
    </ReactFlow>
  )
}

/** Interactive, animated org chart: pan and zoom, auto layout, department focus, minimap. */
export function OrgFlow({
  positions,
  collapsed,
  focusDept,
  actions,
}: {
  positions: Position[]
  collapsed: Set<string>
  focusDept: string | null
  actions: Actions
}) {
  return (
    <ActionsContext.Provider value={actions}>
      <ReactFlowProvider>
        <Flow positions={positions} collapsed={collapsed} focusDept={focusDept} />
      </ReactFlowProvider>
    </ActionsContext.Provider>
  )
}
