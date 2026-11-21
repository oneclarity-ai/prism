import {
  ArrowLeft,
  Bot,
  CalendarClock,
  CheckCircle2,
  Globe,
  Link2,
  ListTree,
  Pencil,
  Play,
  Radio,
  Network,
  ShieldAlert,
  SlidersHorizontal,
  Target,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import type { TaskStatus } from '@/api/client'
import { ACTIVE_RUN, useAgents, useRuns, useStartRun, useTargets, useTask, useTasks, useUpdateTask } from '@/api/hooks'
import { RunDialog } from '@/components/runs/run-dialog'
import { EnvironmentBadge, RunStatusBadge, TaskStatusBadge } from '@/components/common/badges'
import { IdChip } from '@/components/common/copy-button'
import { EmptyState } from '@/components/common/empty-state'
import { InfoTip } from '@/components/common/info-tip'
import { WorkerWarning } from '@/components/runs/worker-warning'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { TASK_STATUSES } from '@/lib/constants'
import { dateTime, duration, hostOf, timeAgo, usd } from '@/lib/format'
import { TaskDialog } from './task-dialog'

function Row({ icon: Icon, label, children }: { icon: typeof Bot; label: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-2.5">
      <Icon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
      <div className="text-muted-foreground w-24 shrink-0 text-sm">{label}</div>
      <div className="min-w-0 flex-1 text-sm">{children}</div>
    </div>
  )
}

function ScopeList({ title, items, mono }: { title: string; items: string[]; mono?: boolean }) {
  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">{title}</div>
      {items.length === 0 ? (
        <div className="text-muted-foreground text-sm">Not set — the agent decides.</div>
      ) : (
        <ul className="space-y-1.5">
          {items.map((i) => (
            <li key={i} className="flex gap-2 text-sm">
              <CheckCircle2 className="text-primary mt-0.5 size-4 shrink-0" />
              <span className={mono ? 'font-mono text-xs leading-5' : ''}>{i}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function TaskDetailPage() {
  const { taskId = '' } = useParams()
  const task = useTask(taskId)
  const agents = useAgents()
  const targets = useTargets()
  const update = useUpdateTask(taskId)
  const start = useStartRun()
  const runs = useRuns({ task_id: taskId }, true)
  const allTasks = useTasks()
  const navigate = useNavigate()
  const activeRun = runs.data?.find((r) => ACTIVE_RUN.includes(r.status))

  if (task.isPending) return <Skeleton className="h-96 w-full" />
  if (task.isError)
    return (
      <EmptyState
        icon={ListTree}
        title="Task not found"
        description={task.error.message}
        action={
          <Button variant="outline" asChild>
            <Link to="/tasks">
              <ArrowLeft /> Back to tasks
            </Link>
          </Button>
        }
      />
    )

  const t = task.data
  const agent = agents.data?.find((a) => a.id === t.agent_id)
  const target = targets.data?.find((x) => x.id === t.target_app_id)

  return (
    <>
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-2">
          <Button variant="ghost" size="sm" className="-ml-2" asChild>
            <Link to="/tasks">
              <ArrowLeft /> Tasks
            </Link>
          </Button>
          <h1 className="text-2xl font-semibold tracking-tight">{t.title}</h1>
          <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-sm">
            <TaskStatusBadge status={t.status} />
            <span>Created {timeAgo(t.created_at)}</span>
            <span>·</span>
            <IdChip id={t.id} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={t.status} onValueChange={(v) => update.mutate({ status: v as TaskStatus })}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TASK_STATUSES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  <s.icon className={s.tone} /> {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <TaskDialog
            task={t}
            trigger={
              <Button variant="outline">
                <Pencil /> Edit
              </Button>
            }
          />
          {activeRun ? (
            <Button asChild>
              <Link to={`/runs/${activeRun.id}`}>
                <Radio className="animate-pulse" /> Watch live run
              </Link>
            </Button>
          ) : (
            <>
              <RunDialog
                task={t}
                agent={agent}
                trigger={
                  <Button variant="outline">
                    <SlidersHorizontal /> Run with options
                  </Button>
                }
              />
              <Button
                disabled={start.isPending}
                onClick={() => start.mutate(t.id, { onSuccess: (r) => navigate(`/runs/${r.id}`) })}
              >
                {start.isPending ? <Spinner /> : <Play />} Run now
              </Button>
            </>
          )}
        </div>
      </div>

      <WorkerWarning hasQueued={!!runs.data?.some((r) => r.status === 'queued')} />

      {t.parent_id && (
        <Alert className="border-violet-500/30">
          <Network className="text-violet-500" />
          <AlertDescription>
            Sub-task created by a parallel run of{' '}
            <Link to={`/tasks/${t.parent_id}`} className="text-primary hover:underline">
              {allTasks.data?.find((x) => x.id === t.parent_id)?.title ?? 'its parent task'}
            </Link>
            . {t.scope.focus}
          </AlertDescription>
        </Alert>
      )}
      {(() => {
        const subs = (allTasks.data ?? []).filter((x) => x.parent_id === t.id)
        return subs.length > 0 ? (
          <div className="text-muted-foreground flex flex-wrap items-center gap-1.5 text-sm">
            <Network className="size-4 text-violet-500" /> Sub-tasks from parallel runs:
            {subs.map((x) => (
              <Link key={x.id} to={`/tasks/${x.id}`}>
                <Badge variant="outline" className="hover:bg-muted font-mono text-[11px]">
                  {(x.scope.urls ?? []).join(', ') || x.title}
                </Badge>
              </Link>
            ))}
          </div>
        ) : null
      })()}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Target className="text-primary size-4" /> Goal
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">
                {t.goal || <span className="text-muted-foreground">No goal written yet.</span>}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                Scope
                <InfoTip title="Scope">
                  <p><b>You decide the scope</b>: whoever creates the task writes the pages, features and acceptance criteria. Press <b>Edit scope</b> to change them.</p>
                  <p>The agent decides the individual <b>test cases</b> from this scope. Acceptance criteria in Given / When / Then form become test cases almost one to one, so write your company's own rules here.</p>
                  <p>House rules for a whole website (test data, what never to touch) go in the target app's <b>Notes for the agent</b>; how the agent works in general is in Agents → <b>Instructions</b>.</p>
                </InfoTip>
              </CardTitle>
              <CardDescription>What the agent should cover when it runs. Written by you; the agent turns it into test cases.</CardDescription>
              <CardAction>
                <TaskDialog
                  task={t}
                  trigger={
                    <Button variant="outline" size="sm">
                      <Pencil /> Edit scope
                    </Button>
                  }
                />
              </CardAction>
            </CardHeader>
            <CardContent className="grid gap-6 md:grid-cols-2">
              <ScopeList title="Pages or URLs" items={t.scope.urls ?? []} mono />
              <ScopeList title="Features" items={t.scope.features ?? []} />
              <div className="md:col-span-2">
                <ScopeList title="Acceptance criteria" items={t.scope.acceptance_criteria ?? []} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Play className="text-primary size-4" /> Runs
              </CardTitle>
              <CardDescription>Each run is one bounded work session of the agent</CardDescription>
            </CardHeader>
            <CardContent>
              {!runs.data?.length ? (
                <div className="text-muted-foreground flex flex-col items-center gap-2 rounded-xl border border-dashed py-10 text-center text-sm">
                  <Play className="size-8 opacity-40" />
                  No runs yet. Press "Run now" to start the agent and watch it live.
                </div>
              ) : (
                <ul className="divide-y">
                  {runs.data.map((r) => (
                    <li key={r.id}>
                      <Link
                        to={`/runs/${r.id}`}
                        className="hover:bg-muted/60 -mx-2 flex items-center gap-3 rounded-lg px-2 py-3 transition-colors"
                      >
                        <RunStatusBadge status={r.status} />
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm">
                            {r.summary || r.error || (r.trigger === 'approval' ? 'Resumed after approval' : 'Run')}
                          </div>
                          <div className="text-muted-foreground text-xs">
                            {timeAgo(r.created_at)} · {duration(r.started_at, r.ended_at)} · {usd(r.cost_usd)}
                          </div>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent className="divide-y">
            <Row icon={Bot} label="Agent">
              {agent ? (
                <Link to={`/agents/${agent.id}`} className="text-primary font-medium hover:underline">
                  {agent.name}
                </Link>
              ) : (
                '—'
              )}
            </Row>
            <Row icon={Globe} label="Target">
              {target ? (
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{target.name}</span>
                    <EnvironmentBadge env={target.environment} />
                  </div>
                  <a
                    href={target.base_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-muted-foreground inline-flex items-center gap-1 text-xs hover:underline"
                  >
                    <Link2 className="size-3" /> {hostOf(target.base_url)}
                  </a>
                </div>
              ) : (
                <span className="text-muted-foreground">No target</span>
              )}
            </Row>
            <Row icon={ShieldAlert} label="Bug filing">
              {t.scope.allow_bug_filing ? (
                <Badge className="border-0 bg-amber-500/10 text-amber-700 dark:text-amber-300">Allowed, with approval</Badge>
              ) : (
                <Badge variant="secondary">Drafts only</Badge>
              )}
            </Row>
            <Row icon={CalendarClock} label="Schedule">
              {t.schedule_cron ? <code className="font-mono text-xs">{t.schedule_cron}</code> : 'Manual'}
            </Row>
            <Row icon={CalendarClock} label="Updated">
              {dateTime(t.updated_at)}
            </Row>
          </CardContent>
        </Card>
      </div>
    </>
  )
}
