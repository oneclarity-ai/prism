import { Bot, CircleDashed, Network, Plus, User, Users } from 'lucide-react'
import { motion } from 'motion/react'
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import type { Position } from '@/api/client'
import { useAgentRoles, useAgents, usePositions } from '@/api/hooks'
import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/common/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { buildTree, deptTone } from '@/lib/org'
import { cn } from '@/lib/utils'
import { OrgFlow } from './org-flow'
import { PositionSheet } from './position-sheet'

type Mode = { kind: 'edit'; position: Position } | { kind: 'new'; parent: Position | null }

export function OrgChartPage() {
  const positions = usePositions()
  const agents = useAgents()
  const roles = useAgentRoles()
  const [params, setParams] = useSearchParams()
  const focusDept = params.get('dept')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [mode, setMode] = useState<Mode | null>(null)

  const list = useMemo(() => positions.data ?? [], [positions.data])
  const tree = useMemo(() => buildTree(list), [list])
  const departments = useMemo(() => {
    const counts = new Map<string, number>()
    list.forEach((p) => counts.set(p.department, (counts.get(p.department) ?? 0) + 1))
    return [...counts.entries()].sort(([a], [b]) => (a === 'Leadership' ? -1 : b === 'Leadership' ? 1 : a.localeCompare(b)))
  }, [list])
  const stats = {
    total: list.length,
    humans: list.filter((p) => p.holder_type === 'human').length,
    agents: list.filter((p) => p.holder_type === 'agent').length,
    vacant: list.filter((p) => p.holder_type === 'vacant').length,
  }
  const agentName = (id?: string | null) => agents.data?.find((a) => a.id === id)?.name
  const roleName = (key?: string | null) => roles.data?.find((r) => r.key === key)?.name

  const toggle = (id: string) =>
    setCollapsed((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })

  return (
    <>
      <PageHeader
        icon={Network}
        title="Organization"
        info={
          <>
            <p>Your company as an org chart. Each seat (CEO, managers, members) is held by a person, an AI agent, or is vacant.</p>
            <p>Later, manager agents will hand work down this chart. Click a card to edit; hover a card and press + to add a report.</p>
          </>
        }
        description="Your company as an org chart. Each seat is held by a person, an AI agent, or is still vacant."
        actions={
          <Button onClick={() => setMode({ kind: 'new', parent: null })}>
            <Plus /> Add position
          </Button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-4">
        {(
          [
            ['Positions', stats.total, Network, 'text-primary'],
            ['People', stats.humans, User, 'text-sky-500'],
            ['AI agents', stats.agents, Bot, 'text-violet-500'],
            ['Vacant', stats.vacant, CircleDashed, 'text-muted-foreground'],
          ] as const
        ).map(([label, n, Icon, tone], i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06, type: 'spring', stiffness: 260, damping: 24 }}
          >
          <Card className="py-3">
            <CardContent className="flex items-center gap-3">
              <Icon className={cn('size-5', tone)} />
              <div>
                <div className="text-xl font-semibold tabular-nums">{n}</div>
                <div className="text-muted-foreground text-xs">{label}</div>
              </div>
            </CardContent>
          </Card>
          </motion.div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={focusDept ? 'outline' : 'secondary'}
          onClick={() => setParams({})}
          className="rounded-full"
        >
          <Users /> All departments
        </Button>
        {departments.map(([dept, n]) => (
          <Button
            key={dept}
            size="sm"
            variant={focusDept === dept ? 'secondary' : 'outline'}
            className="rounded-full"
            onClick={() => setParams(focusDept === dept ? {} : { dept })}
          >
            <span className={cn('size-2 rounded-full', deptTone(dept).dot)} /> {dept}
            <span className="text-muted-foreground">{n}</span>
          </Button>
        ))}
        <div className="ml-auto flex items-center gap-1">
          <Button size="sm" variant="ghost" onClick={() => setCollapsed(new Set())}>
            Expand all
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setCollapsed(new Set(list.filter((p) => list.some((c) => c.parent_id === p.id) && p.parent_id).map((p) => p.id)))}
          >
            Collapse
          </Button>
        </div>
      </div>

      {positions.isPending ? (
        <Skeleton className="h-[60svh]" />
      ) : tree.length === 0 ? (
        <EmptyState
          icon={Network}
          title="No org chart yet"
          description="Start with the CEO, then add executives, managers and the people or agents who report to them."
          action={
            <Button onClick={() => setMode({ kind: 'new', parent: null })}>
              <Plus /> Add the first position
            </Button>
          }
        />
      ) : (
        <Card className="relative overflow-hidden py-0">
          <div className="h-[72svh] min-h-[480px] bg-gradient-to-b from-violet-500/[0.03] to-transparent">
            <OrgFlow
              positions={list}
              collapsed={collapsed}
              focusDept={focusDept}
              actions={{
                onEdit: (position) => setMode({ kind: 'edit', position }),
                onAddChild: (parent) => setMode({ kind: 'new', parent }),
                onToggle: toggle,
                agentName,
                roleName,
              }}
            />
          </div>
          <div className="text-muted-foreground bg-background/80 absolute bottom-0 left-0 flex w-full flex-wrap gap-4 border-t px-4 py-2 text-xs backdrop-blur">
            <span className="flex items-center gap-1.5">
              <User className="size-3.5" /> Person
            </span>
            <span className="flex items-center gap-1.5">
              <Bot className="size-3.5" /> AI agent
            </span>
            <span className="flex items-center gap-1.5">
              <CircleDashed className="size-3.5" /> Vacant
            </span>
            <span className="ml-auto">
              Drag to pan · scroll to zoom · click a card to edit · hover for <Plus className="inline size-3" /> to add a report ·{' '}
              <Link to="/agents" className="text-primary hover:underline">
                manage agents
              </Link>
            </span>
          </div>
        </Card>
      )}

      <PositionSheet
        mode={mode}
        positions={list}
        onClose={() => setMode(null)}
        onAddChild={(parent) => setMode({ kind: 'new', parent })}
      />
    </>
  )
}
