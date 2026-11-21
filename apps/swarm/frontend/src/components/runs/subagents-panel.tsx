import { ArrowUpRight, Bug as BugIcon, Coins, Network, Repeat, Timer } from 'lucide-react'
import { Link } from 'react-router'

import type { SubAgent } from '@/api/client'
import { RunStatusBadge } from '@/components/common/badges'
import { InfoTip } from '@/components/common/info-tip'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { duration, timeAgo, usd } from '@/lib/format'
import { cn } from '@/lib/utils'

const ACTIVE = new Set(['queued', 'running', 'waiting_approval'])

function Lane({ lane }: { lane: SubAgent }) {
  const running = lane.status === 'running'
  const turnPct = lane.turn && lane.max_turns ? Math.min(100, (lane.turn / lane.max_turns) * 100) : 0
  return (
    <Link
      to={`/runs/${lane.run_id}`}
      className={cn(
        'group hover:border-primary/50 flex flex-col gap-2.5 rounded-xl border p-3 transition-colors',
        running && 'border-sky-500/40 bg-sky-500/5',
      )}
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            'flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold',
            running ? 'bg-sky-500 text-white' : 'bg-muted text-muted-foreground',
          )}
        >
          {lane.index}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs" title={lane.label}>
          {lane.label}
        </span>
        <RunStatusBadge status={lane.status} />
        <ArrowUpRight className="text-muted-foreground size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
      </div>

      <div className="text-muted-foreground min-h-8 text-xs leading-snug">
        {lane.status === 'queued' ? (
          'Waiting for a free slot…'
        ) : lane.activity && !lane.activity.startsWith('status:') ? (
          <>
            <span className={cn('text-foreground', running && 'font-medium')}>{lane.activity}</span>
            {lane.activity_at && running && <> · {timeAgo(lane.activity_at)}</>}
          </>
        ) : lane.status === 'succeeded' ? (
          <span className="line-clamp-2">{lane.summary || 'Finished.'}</span>
        ) : lane.status === 'waiting_approval' ? (
          <span className="text-amber-600">Waiting for your approval (open the lane)</span>
        ) : lane.error ? null : (
          '—'
        )}
        {lane.error && <div className="mt-1 text-rose-600">{lane.error}</div>}
      </div>

      {running && <Progress value={turnPct} className="h-1.5" />}

      <div className="text-muted-foreground grid grid-cols-4 gap-1 text-[11px] tabular-nums">
        <span className="flex items-center gap-1" title="Turns used">
          <Repeat className="size-3" /> {lane.turn ?? '—'}
          {lane.max_turns ? `/${lane.max_turns}` : ''}
        </span>
        <span className="flex items-center gap-1" title="Cost / budget">
          <Coins className="size-3" /> {usd(lane.cost_usd)}
        </span>
        <span className="flex items-center gap-1" title="Test cases: pass / fail">
          <span className="text-emerald-600">{lane.cases_pass}✓</span>
          <span className="text-rose-600">{lane.cases_fail}✗</span>
          <span>/{lane.cases_total}</span>
        </span>
        <span className="flex items-center justify-end gap-1" title="Bugs · duration">
          <BugIcon className="size-3" /> {lane.bugs} <Timer className="ml-1 size-3" />
          {duration(lane.started_at, lane.ended_at)}
        </span>
      </div>
    </Link>
  )
}

/** One lane per sub-agent of a parallel run: what it tests, what it is doing now, its progress. */
export function SubAgentsPanel({ lanes, maxParallel }: { lanes: SubAgent[]; maxParallel?: number }) {
  const done = lanes.filter((l) => !ACTIVE.has(l.status)).length
  const running = lanes.filter((l) => l.status === 'running').length
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Network className="size-4 text-violet-500" /> Sub-agents
          <InfoTip title="Parallel run">
            <p>The orchestrator split the pages into groups. Each sub-agent is a normal QA run with its own browser, its own small context and its own budget.</p>
            <p>At most <b>{maxParallel ?? '?'}</b> work at once; the others wait. When all have finished, the orchestrator merges their results, removes duplicate bugs and writes the final report here.</p>
            <p>Click a lane to watch that sub-agent's live log.</p>
          </InfoTip>
        </CardTitle>
        <CardDescription>
          {done} of {lanes.length} finished · {running} working now
          {maxParallel ? ` (max ${maxParallel} at once)` : ''}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Progress value={lanes.length ? (done / lanes.length) * 100 : 0} className="h-2" />
        {lanes.length === 0 ? (
          <div className="text-muted-foreground py-6 text-center text-sm">The orchestrator is planning the split…</div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {lanes.map((lane) => (
              <Lane key={lane.task_id} lane={lane} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
