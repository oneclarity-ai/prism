import {
  ArrowLeft,
  ArrowRight,
  Bot,
  Bug as BugIcon,
  ClipboardList,
  Coins,
  Gauge,
  ImageIcon,
  ListChecks,
  Network,
  OctagonX,
  Play,
  Radio,
  Repeat,
  RotateCcw,
  Square,
  Timer,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import type { Run, RunStart } from '@/api/client'
import {
  ACTIVE_RUN,
  useApprovals,
  useCancelRun,
  useRun,
  useRunArtifacts,
  useRunBugs,
  useRunTestCases,
  useStartRun,
  useSubAgents,
} from '@/api/hooks'
import { RunStatusBadge, SeverityBadge, TestStatusBadge } from '@/components/common/badges'
import { IdChip } from '@/components/common/copy-button'
import { EmptyState } from '@/components/common/empty-state'
import { Markdown } from '@/components/common/markdown'
import { SubAgentsPanel } from '@/components/runs/subagents-panel'
import { ApprovalCard } from '@/components/runs/approval-card'
import { BugActions } from '@/components/runs/bug-actions'
import { InfoTip } from '@/components/common/info-tip'
import { WorkerWarning } from '@/components/runs/worker-warning'
import { RunTimeline } from '@/components/runs/run-timeline'
import { EvidenceThumbs, LatestScreenshot, ScreenshotGallery } from '@/components/runs/screenshots'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { RUNTIME_LABELS } from '@/lib/constants'
import { dateTime, duration, tokens, usd } from '@/lib/format'
import { useRunStream } from '@/lib/use-run-stream'
import { cn } from '@/lib/utils'

const LIVE = new Set(ACTIVE_RUN)

/** Options to repeat a run exactly (same pages, mode and limits). */
function againOptions(run: Run): RunStart {
  const o = run.options as Record<string, unknown>
  return {
    mode: run.kind === 'orchestrator' ? 'parallel' : 'single',
    pages: (o.pages as string[] | undefined)?.length ? (o.pages as string[]) : null,
    max_parallel: (o.max_parallel as number | undefined) ?? null,
    pages_per_agent: (o.pages_per_agent as number | undefined) ?? 1,
    max_turns: (o.max_turns as number | undefined) ?? null,
    budget_usd: (o.budget_usd as number | undefined) ?? null,
  }
}

function useTicker(active: boolean) {
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => setTick((n) => n + 1), 1000)
    return () => clearInterval(t)
  }, [active])
}

function Stat({ icon: Icon, label, value }: { icon: typeof Timer; label: string; value: ReactNode }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="bg-muted flex size-8 items-center justify-center rounded-lg">
        <Icon className="text-muted-foreground size-4" />
      </div>
      <div className="leading-tight">
        <div className="text-muted-foreground text-[11px] uppercase">{label}</div>
        <div className="text-sm font-semibold tabular-nums">{value}</div>
      </div>
    </div>
  )
}

export function RunDetailPage() {
  const { runId = '' } = useParams()
  const run = useRun(runId)
  if (run.isPending) return <Skeleton className="h-[70svh] w-full" />
  if (run.isError)
    return (
      <EmptyState
        icon={Play}
        title="Run not found"
        description={run.error.message}
        action={
          <Button variant="outline" asChild>
            <Link to="/runs">
              <ArrowLeft /> All runs
            </Link>
          </Button>
        }
      />
    )
  return <RunView key={runId} run={run.data} />
}

function RunView({ run }: { run: Run }) {
  const navigate = useNavigate()
  // Re-open the stream if the run status moves on while the stream is not connected.
  const [nonce, setNonce] = useState(0)
  const { events, connected } = useRunStream(run.id, nonce)
  const lastStatus = useRef(run.status)
  useEffect(() => {
    if (run.status !== lastStatus.current) {
      lastStatus.current = run.status
      if (!connected) setNonce((n) => n + 1)
    }
  }, [run.status, connected])
  const cases = useRunTestCases(run.id)
  const bugs = useRunBugs(run.id)
  const artifacts = useRunArtifacts(run.id)
  const approvals = useApprovals()
  const cancel = useCancelRun(run.id)
  const again = useStartRun()
  const live = LIVE.has(run.status)
  const parallel = run.kind === 'orchestrator'
  const lanes = useSubAgents(run.id, parallel, live)
  const opts = run.options as { index?: number; label?: string; max_parallel?: number; pages?: string[] }
  useTicker(live)

  // After the last approval is decided here, jump to the follow-up run that continues the work.
  const wasWaiting = useRef(false)
  useEffect(() => {
    if (run.status === 'waiting_approval') wasWaiting.current = true
    else if (wasWaiting.current && run.resumed_by_run_id) navigate(`/runs/${run.resumed_by_run_id}`)
  }, [run.status, run.resumed_by_run_id, navigate])

  const runApprovals = (approvals.data ?? []).filter((a) => a.run_id === run.id)
  const pendingApprovals = runApprovals.filter((a) => a.status === 'pending')
  const caseList = cases.data ?? []
  const counts = {
    pass: caseList.filter((c) => c.status === 'pass').length,
    fail: caseList.filter((c) => c.status === 'fail').length,
    blocked: caseList.filter((c) => c.status === 'blocked').length,
    pending: caseList.filter((c) => c.status === 'pending').length,
  }
  const runtime = (events.find((e) => e.type === 'status')?.payload as { runtime?: string } | undefined)?.runtime
  // Live usage: the run row is only updated at the end, the stream carries running totals.
  const lastUsage = [...events].reverse().find((e) => e.type === 'usage')?.payload as
    | { input_tokens: number; output_tokens: number; cost_usd: number; turn?: number; max_turns?: number; budget_usd?: number }
    | undefined
  let liveTokens = live && lastUsage ? lastUsage.input_tokens + lastUsage.output_tokens : run.input_tokens + run.output_tokens
  let liveCost = live && lastUsage ? lastUsage.cost_usd : Number(run.cost_usd)
  const turns = lastUsage?.turn
  const laneList = lanes.data ?? []
  if (parallel) {
    // A parallel run's own cost is only the merge; show the total of all sub-agents.
    liveTokens = run.input_tokens + run.output_tokens + laneList.reduce((n, l) => n + l.tokens, 0)
    liveCost = Number(run.cost_usd) + laneList.reduce((n, l) => n + l.cost_usd, 0)
  }
  const lanesDone = laneList.filter((l) => !['queued', 'running', 'waiting_approval'].includes(l.status)).length

  return (
    <>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-2">
          <Button variant="ghost" size="sm" className="-ml-2" asChild>
            <Link to={`/tasks/${run.task_id}`}>
              <ArrowLeft /> {run.task_title ?? 'Task'}
            </Link>
          </Button>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              {parallel ? 'Parallel QA run' : run.kind === 'child' ? `Sub-agent #${opts.index ?? '?'}` : 'QA run'}
              <InfoTip title="Run page">
                <p><b>Live log</b>: every step the agent takes, as it happens. Click a step to see its input and output.</p>
                <p><b>Test results / Bugs / Screenshots</b>: fill in while it works.</p>
                <p><b>What the agent sees</b>: the latest browser screenshot.</p>
                <p>Turns = model calls; the run stops at the agent's max turns or per-run budget (Agents → Limits).</p>
              </InfoTip>
            </h1>
            <RunStatusBadge status={run.status} />
            {live && (
              <Badge variant="outline" className={cn('gap-1.5', connected ? 'text-emerald-600' : 'text-muted-foreground')}>
                <Radio className={cn('size-3.5', connected && 'animate-pulse')} /> {connected ? 'Live' : 'Connecting…'}
              </Badge>
            )}
            {runtime && <Badge variant="secondary">{RUNTIME_LABELS[runtime] ?? runtime}</Badge>}
          </div>
          <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-sm">
            <Bot className="size-4" /> {run.agent_name} · {run.trigger === 'approval' ? 'resumed after approval' : run.trigger} ·
            started {run.started_at ? dateTime(run.started_at) : 'not yet'} · <IdChip id={run.id} />
          </div>
        </div>
        <div className="flex gap-2">
          {(live || run.status === 'waiting_approval') && (
            <Button variant="outline" onClick={() => cancel.mutate()} disabled={cancel.isPending || run.cancel_requested}>
              <Square /> {run.cancel_requested ? 'Stopping…' : 'Cancel run'}
            </Button>
          )}
          {!live && run.status !== 'waiting_approval' && run.kind !== 'child' && (
            <Button
              onClick={() =>
                again.mutate(
                  { taskId: run.task_id, options: againOptions(run) },
                  { onSuccess: (r) => navigate(`/runs/${r.id}`) },
                )
              }
              disabled={again.isPending}
            >
              <RotateCcw /> Run again
            </Button>
          )}
        </div>
      </div>

      {run.status === 'queued' && <WorkerWarning />}

      <Card className="py-4">
        <CardContent className="grid grid-cols-2 gap-4 md:grid-cols-6">
          <Stat icon={Timer} label="Duration" value={duration(run.started_at, run.ended_at)} />
          {parallel ? (
            <Stat icon={Network} label="Sub-agents" value={`${lanesDone} / ${laneList.length} done`} />
          ) : (
            <Stat
              icon={Repeat}
              label="Turns"
              value={turns ? `${turns}${lastUsage?.max_turns ? ` / ${lastUsage.max_turns}` : ''}` : '—'}
            />
          )}
          <Stat icon={Gauge} label="Tokens" value={tokens(liveTokens)} />
          <Stat
            icon={Coins}
            label="Cost"
            value={`${usd(liveCost)}${lastUsage?.budget_usd ? ` / ${usd(lastUsage.budget_usd)}` : ''}`}
          />
          <Stat icon={ListChecks} label="Test cases" value={`${counts.pass} ✓ · ${counts.fail} ✗ · ${counts.blocked} ⊘`} />
          <Stat icon={BugIcon} label="Bugs" value={bugs.data?.length ?? 0} />
        </CardContent>
      </Card>

      {run.parent_run_id && (
        <Alert className="border-violet-500/30">
          <Network className="text-violet-500" />
          <AlertTitle>Sub-agent #{opts.index} of a parallel run</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
            <span>
              Tests only <span className="font-mono">{opts.label}</span>. Its results also appear in the final report.
            </span>
            <Button size="sm" variant="outline" asChild>
              <Link to={`/runs/${run.parent_run_id}`}>
                <ArrowLeft /> Back to the parallel run
              </Link>
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {!parallel && !run.parent_run_id && (opts.pages?.length ?? 0) > 0 && (
        <div className="text-muted-foreground flex flex-wrap items-center gap-1.5 text-sm">
          This run tests only:
          {opts.pages!.map((p) => (
            <Badge key={p} variant="outline" className="font-mono text-[11px]">
              {p}
            </Badge>
          ))}
        </div>
      )}
      {parallel && <SubAgentsPanel lanes={laneList} maxParallel={opts.max_parallel} />}

      {run.status === 'waiting_approval' && (
        <div className="space-y-3">
          <Alert className="border-amber-500/40">
            <OctagonX className="text-amber-500" />
            <AlertTitle>The agent is waiting for your decision</AlertTitle>
            <AlertDescription>
              Approve or reject each action below. When all are decided, a follow-up run continues automatically.
            </AlertDescription>
          </Alert>
          {pendingApprovals.map((a) => (
            <ApprovalCard key={a.id} approval={a} />
          ))}
        </div>
      )}
      {run.resumed_by_run_id && (
        <Alert>
          <ArrowRight />
          <AlertTitle>Continued in a follow-up run</AlertTitle>
          <AlertDescription className="flex items-center justify-between gap-2">
            The work after your approval happened in the next run.
            <Button size="sm" asChild>
              <Link to={`/runs/${run.resumed_by_run_id}`}>
                Open it <ArrowRight />
              </Link>
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {run.resumes_run_id && (
        <Alert>
          <RotateCcw />
          <AlertDescription>
            This run continues{' '}
            <Link to={`/runs/${run.resumes_run_id}`} className="text-primary hover:underline">
              the paused run
            </Link>
            . Test cases and bugs from both runs are shown together.
          </AlertDescription>
        </Alert>
      )}
      {run.error && (
        <Alert variant="destructive">
          <OctagonX />
          <AlertTitle>Run ended with a problem</AlertTitle>
          <AlertDescription>{run.error}</AlertDescription>
        </Alert>
      )}
      {run.summary && run.status === 'succeeded' && !parallel && (
        <Card className="border-emerald-500/30 bg-emerald-500/5">
          <CardHeader>
            <CardTitle>Agent's summary</CardTitle>
            <CardDescription className="text-foreground text-sm whitespace-pre-wrap">{run.summary}</CardDescription>
          </CardHeader>
        </Card>
      )}
      {run.summary && parallel && !live && (
        <Card className="border-emerald-500/30 bg-emerald-500/5">
          <CardContent className="prose-sm">
            <Markdown source={run.summary} />
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <Tabs defaultValue="log" className="gap-4">
            <CardHeader>
              <TabsList>
                <TabsTrigger value="log">
                  <Radio /> Live log <Badge variant="secondary">{events.length}</Badge>
                </TabsTrigger>
                <TabsTrigger value="cases">
                  <ClipboardList /> Test results <Badge variant="secondary">{caseList.length}</Badge>
                </TabsTrigger>
                <TabsTrigger value="bugs">
                  <BugIcon /> Bugs <Badge variant="secondary">{bugs.data?.length ?? 0}</Badge>
                </TabsTrigger>
                <TabsTrigger value="shots">
                  <ImageIcon /> Screenshots <Badge variant="secondary">{artifacts.data?.length ?? 0}</Badge>
                </TabsTrigger>
              </TabsList>
            </CardHeader>
            <CardContent>
              <TabsContent value="log" className="max-h-[70svh] overflow-y-auto pr-1">
                <RunTimeline events={events} live={live} />
              </TabsContent>
              <TabsContent value="cases">
                {caseList.length === 0 ? (
                  <div className="text-muted-foreground py-12 text-center text-sm">No test plan saved yet.</div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Test case</TableHead>
                        <TableHead>Result</TableHead>
                        <TableHead>Evidence</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {caseList.map((c) => (
                        <TableRow key={c.id}>
                          <TableCell className="max-w-md whitespace-normal">
                            <div className="font-medium">{c.title}</div>
                            {(c.given || c.when || c.then) && (
                              <div className="text-muted-foreground mt-0.5 text-xs">
                                {c.given && <>Given {c.given}, </>}
                                {c.when && <>when {c.when}, </>}
                                {c.then && <>then {c.then}</>}
                              </div>
                            )}
                            {c.notes && <div className="mt-1 text-xs italic">{c.notes}</div>}
                          </TableCell>
                          <TableCell>
                            <TestStatusBadge status={c.status} />
                          </TableCell>
                          <TableCell>
                            <EvidenceThumbs ids={c.evidence_artifact_ids} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </TabsContent>
              <TabsContent value="bugs" className="space-y-3">
                {(bugs.data ?? []).length === 0 && (
                  <div className="text-muted-foreground py-12 text-center text-sm">No bugs found in this run.</div>
                )}
                {(bugs.data ?? []).map((b) => (
                  <div key={b.id} className="space-y-2 rounded-xl border p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <BugIcon className="size-4 text-rose-500" />
                      <span className="font-medium">{b.title}</span>
                      <SeverityBadge severity={b.severity} />
                      {b.duplicate_of_id && (
                        <Badge variant="secondary" title="Another sub-agent reported the same bug">
                          Duplicate
                        </Badge>
                      )}
                      <Badge variant="outline" className="ml-auto capitalize">
                        {b.status}
                      </Badge>
                    </div>
                    <div className="grid gap-3 text-sm md:grid-cols-3">
                      <div>
                        <div className="text-muted-foreground text-xs font-medium uppercase">Steps</div>
                        <p className="whitespace-pre-wrap">{b.steps}</p>
                      </div>
                      <div>
                        <div className="text-muted-foreground text-xs font-medium uppercase">Expected</div>
                        <p className="whitespace-pre-wrap">{b.expected}</p>
                      </div>
                      <div>
                        <div className="text-muted-foreground text-xs font-medium uppercase">Actual</div>
                        <p className="whitespace-pre-wrap">{b.actual}</p>
                      </div>
                    </div>
                    <div className="border-t pt-3">
                      <BugActions title={b.title} size="xs" />
                    </div>
                    {b.external_url && (
                      <a href={b.external_url} target="_blank" rel="noreferrer" className="text-primary text-sm hover:underline">
                        View in tracker
                      </a>
                    )}
                  </div>
                ))}
              </TabsContent>
              <TabsContent value="shots">
                <ScreenshotGallery artifacts={artifacts.data ?? []} />
              </TabsContent>
            </CardContent>
          </Tabs>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ImageIcon className="text-primary size-4" /> What the agent sees
              </CardTitle>
              <CardDescription>Latest browser screenshot</CardDescription>
            </CardHeader>
            <CardContent>
              <LatestScreenshot artifacts={artifacts.data ?? []} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Results</CardTitle>
              <CardDescription>{caseList.length} test cases</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="bg-muted flex h-2.5 overflow-hidden rounded-full">
                {caseList.length > 0 &&
                  (
                    [
                      ['pass', 'bg-emerald-500'],
                      ['fail', 'bg-rose-500'],
                      ['blocked', 'bg-amber-500'],
                    ] as const
                  ).map(([k, color]) => (
                    <div key={k} className={color} style={{ width: `${(counts[k] / caseList.length) * 100}%` }} />
                  ))}
              </div>
              <div className="grid grid-cols-4 gap-2 text-center text-xs">
                {(
                  [
                    ['Pass', counts.pass, 'text-emerald-600'],
                    ['Fail', counts.fail, 'text-rose-600'],
                    ['Blocked', counts.blocked, 'text-amber-600'],
                    ['Pending', counts.pending, 'text-muted-foreground'],
                  ] as const
                ).map(([label, n, tone]) => (
                  <div key={label} className="rounded-lg border py-2">
                    <div className={cn('text-lg font-semibold tabular-nums', tone)}>{n}</div>
                    {label}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  )
}
