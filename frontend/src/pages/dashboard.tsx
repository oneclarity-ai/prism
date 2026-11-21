import {
  ArrowRight,
  Bot,
  Bug,
  CloudOff,
  Coins,
  LayoutDashboard,
  ListChecks,
  PlayCircle,
  Plus,
  type LucideIcon,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'

import { useAgents, useAnalytics, useBugs, useMe, useRuns, useRuntimeStatus, useTasks } from '@/api/hooks'
import { AgentStatusBadge, RunStatusBadge, SeverityBadge } from '@/components/common/badges'
import { DateRangeFilter } from '@/components/common/date-range-filter'
import { PageHeader } from '@/components/common/page-header'
import { WorkerWarning } from '@/components/runs/worker-warning'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { defaultRange, rangeLabel, rangeQuery, type DateRange } from '@/lib/date-range'
import { dateTime, usd } from '@/lib/format'
import { cn } from '@/lib/utils'
import { TaskDialog } from './tasks/task-dialog'

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  to,
  tone,
  loading,
}: {
  icon: LucideIcon
  label: string
  value: ReactNode
  hint: string
  to: string
  tone: string
  loading: boolean
}) {
  return (
    <Link to={to} className="group">
      <Card className="hover:border-primary/40 h-full transition-all group-hover:shadow-md">
        <CardHeader>
          <CardDescription>{label}</CardDescription>
          <CardAction>
            <div className={cn('flex size-9 items-center justify-center rounded-lg', tone)}>
              <Icon className="size-4.5" />
            </div>
          </CardAction>
          <CardTitle className="text-3xl font-semibold tabular-nums">
            {loading ? <Skeleton className="h-9 w-12" /> : value}
          </CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground flex items-center justify-between text-xs">
          {hint}
          <ArrowRight className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
        </CardContent>
      </Card>
    </Link>
  )
}

export function DashboardPage() {
  const { data: me } = useMe()
  const [range, setRange] = useState<DateRange>(defaultRange('7d'))
  const period = rangeQuery(range)
  const agents = useAgents()
  const tasks = useTasks()
  const runs = useRuns({ top_level: true, ...period })
  const bugs = useBugs(period)
  const stats = useAnalytics(period)
  const runtime = useRuntimeStatus()
  const t = stats.data?.totals as Record<string, number> | undefined
  const tested = t ? t.tests_pass + t.tests_fail + t.tests_blocked : 0

  const taskList = (tasks.data ?? []).filter((x) => !x.parent_id)
  const open = taskList.filter((t) => t.status === 'todo' || t.status === 'in_progress').length
  const activeAgents = (agents.data ?? []).filter((a) => a.status === 'active').length

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  return (
    <>
      <PageHeader
        icon={LayoutDashboard}
        title={`${greeting}, ${me?.name || 'there'}`}
        info={
          <>
            <p>Your control room for the chosen period: runs, bugs found, cost, the latest runs and bugs, and your agent team.</p>
            <p>Red or amber banners at the top tell you when something blocks runs (no worker, Azure not configured).</p>
          </>
        }
        description="Here is what your agent team is working on."
        actions={
          <>
          <DateRangeFilter value={range} onChange={setRange} />
          <TaskDialog
            trigger={
              <Button>
                <Plus /> New task
              </Button>
            }
          />
          </>
        }
      />

      <WorkerWarning hasQueued={!!runs.data?.some((r) => r.status === 'queued')} />

      {runtime.data && !runtime.data.azure_configured && (
        <Alert className="border-amber-500/40">
          <CloudOff className="text-amber-500" />
          <AlertTitle>Azure OpenAI is not connected yet</AlertTitle>
          <AlertDescription>
            The real QA agent needs the AZURE_OPENAI_* values in backend/.env (then restart the worker). Until then, set the
            agent's runtime to "Fake" to try the full flow with a scripted agent.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={Bot}
          label="Active agents"
          value={activeAgents}
          hint={`${open} open task${open === 1 ? '' : 's'}`}
          to="/agents"
          tone="bg-indigo-500/10 text-indigo-600 dark:text-indigo-300"
          loading={agents.isPending}
        />
        <StatCard
          icon={PlayCircle}
          label={`Runs · ${rangeLabel(range)}`}
          value={t?.runs ?? 0}
          hint={t ? `${t.succeeded} succeeded · ${t.failed} failed` : '—'}
          to="/runs"
          tone="bg-sky-500/10 text-sky-600 dark:text-sky-300"
          loading={stats.isPending}
        />
        <StatCard
          icon={Bug}
          label={`Bugs found · ${rangeLabel(range)}`}
          value={t?.bugs ?? 0}
          hint={tested ? `${Math.round((t!.tests_pass / tested) * 100)}% of ${tested} test cases passed` : 'No test cases yet'}
          to="/bugs"
          tone="bg-rose-500/10 text-rose-600 dark:text-rose-300"
          loading={stats.isPending}
        />
        <StatCard
          icon={Coins}
          label={`Cost · ${rangeLabel(range)}`}
          value={usd(t?.cost_usd ?? 0)}
          hint={t?.runs ? `${usd(t.avg_cost_per_run)} per run` : 'Estimated from tokens'}
          to="/usage"
          tone="bg-amber-500/10 text-amber-600 dark:text-amber-300"
          loading={stats.isPending}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent runs</CardTitle>
            <CardDescription>{rangeLabel(range)} · newest first</CardDescription>
            <CardAction>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/runs">
                  View all <ArrowRight />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            {runs.isPending ? (
              <div className="space-y-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : !runs.data?.length ? (
              <div className="text-muted-foreground flex flex-col items-center gap-3 py-10 text-sm">
                <ListChecks className="size-8 opacity-40" />
                No runs in this period. Open a task and press Run now.
              </div>
            ) : (
              <ul className="divide-y">
                {runs.data.slice(0, 7).map((r) => (
                  <li key={r.id}>
                    <Link
                      to={`/runs/${r.id}`}
                      className="hover:bg-muted/60 -mx-2 flex items-center gap-3 rounded-lg px-2 py-3 transition-colors"
                    >
                      <Avatar className="size-8 rounded-lg">
                        <AvatarFallback className="bg-primary/10 text-primary rounded-lg">
                          <Bot className="size-4" />
                        </AvatarFallback>
                      </Avatar>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">
                          {r.task_title}
                          {r.kind === 'orchestrator' && <span className="text-muted-foreground font-normal"> · parallel</span>}
                        </div>
                        <div className="text-muted-foreground truncate text-xs">
                          {r.agent_name} · {dateTime(r.created_at)} · {usd(r.total_cost_usd ?? r.cost_usd)}
                        </div>
                      </div>
                      <RunStatusBadge status={r.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Latest bugs</CardTitle>
            <CardDescription>{rangeLabel(range)}</CardDescription>
            <CardAction>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/bugs">
                  View all <ArrowRight />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            {bugs.isPending ? (
              <Skeleton className="h-40" />
            ) : !bugs.data?.length ? (
              <div className="text-muted-foreground flex flex-col items-center gap-2 py-10 text-sm">
                <Bug className="size-8 opacity-40" />
                No bugs in this period.
              </div>
            ) : (
              <ul className="divide-y">
                {bugs.data.slice(0, 6).map((b) => (
                  <li key={b.id}>
                    <Link to={`/runs/${b.run_id}`} className="hover:bg-muted/60 -mx-2 block rounded-lg px-2 py-2.5 transition-colors">
                      <div className="flex items-center gap-2">
                        <SeverityBadge severity={b.severity} />
                        <span className="truncate text-sm font-medium">{b.title}</span>
                      </div>
                      <div className="text-muted-foreground mt-0.5 truncate text-xs">
                        {b.target_name ?? 'No target'} · {dateTime(b.created_at)}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Agent roster</CardTitle>
          <CardDescription>Your AI team and what each one does</CardDescription>
          <CardAction>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/agents">
                Manage <ArrowRight />
              </Link>
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(agents.data ?? []).map((a) => {
            const count = taskList.filter((t) => t.agent_id === a.id).length
            return (
              <Link
                key={a.id}
                to={`/agents/${a.id}`}
                className="hover:border-primary/40 flex items-center gap-3 rounded-xl border p-3 transition-colors"
              >
                <div className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
                  <Bot className="size-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{a.name}</div>
                  <div className="text-muted-foreground truncate text-xs capitalize">
                    {a.role} · {count} task{count === 1 ? '' : 's'}
                  </div>
                </div>
                <AgentStatusBadge status={a.status} />
              </Link>
            )
          })}
        </CardContent>
      </Card>
    </>
  )
}
