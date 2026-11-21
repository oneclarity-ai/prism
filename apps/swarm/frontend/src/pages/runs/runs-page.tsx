import { PlayCircle } from 'lucide-react'
import { Fragment, useState } from 'react'
import { useNavigate } from 'react-router'

import type { RunStatus } from '@/api/client'
import { useRuns } from '@/api/hooks'
import { RunStatusBadge } from '@/components/common/badges'
import { DateRangeFilter } from '@/components/common/date-range-filter'
import { EmptyState } from '@/components/common/empty-state'
import { WorkerWarning } from '@/components/runs/worker-warning'
import { PageHeader } from '@/components/common/page-header'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { RUN_STATUSES } from '@/lib/constants'
import { defaultRange, groupByDay, rangeQuery, type DateRange } from '@/lib/date-range'
import { duration, tokens, usd } from '@/lib/format'

export function RunsPage() {
  const navigate = useNavigate()
  const [range, setRange] = useState<DateRange>(defaultRange('30d'))
  const runs = useRuns({ top_level: true, ...rangeQuery(range) }, true)
  const [status, setStatus] = useState('all')
  const list = runs.data ?? []
  const shown = status === 'all' ? list : list.filter((r) => r.status === status)

  return (
    <>
      <PageHeader
        icon={PlayCircle}
        title="Runs"
        description="Every work session of every agent. Click one to watch it live."
        info={
          <>
            <p>A run is one bounded work session: the agent starts, works through the task, and ends with a summary.</p>
            <p>
              <b>Needs approval</b>: paused for your decision. <b>resumed</b>: a follow-up run that continued after approval.
              Runs stay <b>Queued</b> until a worker picks them up.
            </p>
          </>
        }
      />
      <WorkerWarning hasQueued={list.some((r) => r.status === 'queued')} />
      <DateRangeFilter value={range} onChange={setRange} />
      <Tabs value={status} onValueChange={setStatus}>
        <TabsList className="h-auto flex-wrap">
          <TabsTrigger value="all">
            All <Badge variant="secondary">{list.length}</Badge>
          </TabsTrigger>
          {RUN_STATUSES.map((s) => (
            <TabsTrigger key={s.value} value={s.value}>
              <s.icon className={s.tone} /> {s.label}
              <Badge variant="secondary">{list.filter((r) => r.status === (s.value as RunStatus)).length}</Badge>
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {runs.isPending ? (
        <Skeleton className="h-64" />
      ) : list.length === 0 ? (
        <EmptyState icon={PlayCircle} title="No runs yet" description='Open a task and press "Run now" to start the QA agent.' />
      ) : (
        <Card className="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Task</TableHead>
                <TableHead>Agent</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Tokens</TableHead>
                <TableHead>Cost</TableHead>
                <TableHead className="pr-4 text-right">Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {groupByDay(shown, (r) => r.created_at).map((day) => (
                <Fragment key={day.key}>
                  <TableRow className="bg-muted/40 hover:bg-muted/40">
                    <TableCell colSpan={7} className="pl-4 text-xs font-semibold">
                      {day.label} <span className="text-muted-foreground font-normal">· {day.items.length} run{day.items.length === 1 ? '' : 's'}</span>
                    </TableCell>
                  </TableRow>
              {day.items.map((r) => (
                <TableRow key={r.id} className="cursor-pointer" onClick={() => navigate(`/runs/${r.id}`)}>
                  <TableCell className="pl-4">
                    <div className="font-medium">{r.task_title}</div>
                    <div className="text-muted-foreground font-mono text-xs">
                      {r.id.slice(0, 8)}
                      {r.trigger === 'approval' && ' · resumed'}
                      {r.kind === 'orchestrator' && ' · parallel'}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{r.agent_name}</TableCell>
                  <TableCell>
                    <RunStatusBadge status={r.status} />
                  </TableCell>
                  <TableCell className="text-sm tabular-nums">{duration(r.started_at, r.ended_at)}</TableCell>
                  <TableCell className="text-sm tabular-nums">{tokens(r.total_tokens ?? r.input_tokens + r.output_tokens)}</TableCell>
                  <TableCell className="text-sm tabular-nums">{usd(r.total_cost_usd ?? r.cost_usd)}</TableCell>
                  <TableCell className="text-muted-foreground pr-4 text-right text-sm">
                    {new Date(r.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </TableCell>
                </TableRow>
              ))}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </>
  )
}
