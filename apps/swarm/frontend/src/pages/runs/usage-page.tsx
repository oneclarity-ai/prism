import { Bot, Bug, CheckCircle2, Cloud, Coins, Cpu, Gauge, PlayCircle, Timer, TrendingUp, Wallet, XCircle } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from 'recharts'

import { useAgents, useAnalytics, useRuntimeStatus } from '@/api/hooks'
import { DateRangeFilter } from '@/components/common/date-range-filter'
import { InfoTip } from '@/components/common/info-tip'
import { PageHeader } from '@/components/common/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { defaultRange, rangeLabel, rangeQuery, type DateRange } from '@/lib/date-range'
import { tokens, usd } from '@/lib/format'

const ALL = 'all'
const STATUS_COLORS: Record<string, string> = {
  succeeded: 'oklch(0.65 0.17 162)',
  failed: 'oklch(0.63 0.21 25)',
  timed_out: 'oklch(0.55 0.2 25)',
  waiting_approval: 'oklch(0.75 0.16 70)',
  running: 'oklch(0.6 0.15 240)',
  queued: 'oklch(0.7 0.02 270)',
  cancelled: 'oklch(0.6 0.02 270)',
  pass: 'oklch(0.65 0.17 162)',
  fail: 'oklch(0.63 0.21 25)',
  blocked: 'oklch(0.75 0.16 70)',
  pending: 'oklch(0.7 0.02 270)',
  skipped: 'oklch(0.6 0.02 270)',
  critical: 'oklch(0.5 0.22 25)',
  high: 'oklch(0.63 0.21 25)',
  medium: 'oklch(0.75 0.16 70)',
  low: 'oklch(0.7 0.02 270)',
}
const pct = (n: number) => `${Math.round(n * 100)}%`
const shortDate = (d: string) => new Date(d + 'T00:00:00').toLocaleDateString([], { day: 'numeric', month: 'short' })
const secs = (s: number) => (s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${Math.round(s)}s`)

function Kpi({ icon: Icon, label, value, sub, info }: { icon: typeof Coins; label: string; value: ReactNode; sub?: ReactNode; info: ReactNode }) {
  return (
    <Card className="gap-2 py-4">
      <CardHeader className="px-4">
        <CardDescription className="flex items-center gap-1.5">
          <Icon className="size-4" /> {label}
        </CardDescription>
        <CardAction>
          <InfoTip title={label}>{info}</InfoTip>
        </CardAction>
      </CardHeader>
      <CardContent className="px-4">
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        {sub && <div className="text-muted-foreground mt-0.5 text-xs">{sub}</div>}
      </CardContent>
    </Card>
  )
}

function ChartCard({ title, description, info, children, className }: { title: string; description?: string; info: ReactNode; children: ReactNode; className?: string }) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
        <CardAction>
          <InfoTip title={title}>{info}</InfoTip>
        </CardAction>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function Donut({ data, nameKey }: { data: { count: number; [k: string]: string | number }[]; nameKey: string }) {
  const total = data.reduce((s, d) => s + d.count, 0)
  const config = Object.fromEntries(data.map((d) => [String(d[nameKey]), { label: String(d[nameKey]).replace('_', ' '), color: STATUS_COLORS[String(d[nameKey])] }])) as ChartConfig
  if (!total) return <div className="text-muted-foreground flex h-52 items-center justify-center text-sm">No data in this period</div>
  return (
    <ChartContainer config={config} className="mx-auto aspect-square h-56">
      <PieChart>
        <ChartTooltip content={<ChartTooltipContent nameKey={nameKey} hideLabel />} />
        <Pie data={data} dataKey="count" nameKey={nameKey} innerRadius={55} strokeWidth={3}>
          {data.map((d) => (
            <Cell key={String(d[nameKey])} fill={STATUS_COLORS[String(d[nameKey])] ?? 'var(--chart-1)'} />
          ))}
        </Pie>
        <ChartLegend content={<ChartLegendContent nameKey={nameKey} />} className="flex-wrap gap-2" />
      </PieChart>
    </ChartContainer>
  )
}

export function UsagePage() {
  const [range, setRange] = useState<DateRange>(defaultRange('30d'))
  const [agentId, setAgentId] = useState(ALL)
  const agents = useAgents()
  const runtime = useRuntimeStatus()
  const a = useAnalytics(rangeQuery(range), agentId === ALL ? undefined : agentId)
  const d = a.data
  const t = d?.totals as Record<string, number> | undefined
  const tested = t ? t.tests_pass + t.tests_fail + t.tests_blocked : 0

  return (
    <>
      <PageHeader
        icon={Wallet}
        title="Usage & analytics"
        description="Cost, tokens and results of your agents, per agent and per model."
        info={
          <>
            <p>Every run records the model it used, its tokens and its estimated cost.</p>
            <p>
              Cost = tokens × the price per 1M tokens set in <code>backend/.env</code> (AZURE_PRICE_INPUT_PER_1M /
              AZURE_PRICE_OUTPUT_PER_1M). Check your real prices on the Azure pricing page.
            </p>
            <p>The page refreshes every 30 seconds.</p>
          </>
        }
        actions={
          <>
            <Select value={agentId} onValueChange={setAgentId}>
              <SelectTrigger className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All agents</SelectItem>
                {(agents.data ?? []).map((ag) => (
                  <SelectItem key={ag.id} value={ag.id}>
                    {ag.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <DateRangeFilter value={range} onChange={setRange} />
          </>
        }
      />

      {runtime.data && (
        <Alert className={runtime.data.azure_configured ? 'border-emerald-500/30' : 'border-amber-500/40'}>
          {runtime.data.azure_configured ? <CheckCircle2 className="text-emerald-500" /> : <XCircle className="text-amber-500" />}
          <AlertTitle className="flex items-center gap-2">
            <Cloud className="size-4" /> Azure OpenAI {runtime.data.azure_configured ? 'connected' : 'not configured'}
            {runtime.data.azure_configured && <span className="text-muted-foreground font-normal">· default deployment {runtime.data.deployment}</span>}
          </AlertTitle>
          <AlertDescription>
            {runtime.data.workers_online > 0
              ? `${runtime.data.workers_online} worker${runtime.data.workers_online > 1 ? 's' : ''} online.`
              : 'No worker online: queued runs will not start until you run ./scripts/dev.sh.'}
          </AlertDescription>
        </Alert>
      )}

      {a.isPending || !d || !t ? (
        <Skeleton className="h-[60svh]" />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <Kpi icon={Coins} label="Total cost" value={usd(t.cost_usd)} sub={`${usd(t.avg_cost_per_run)} per run`} info="Estimated spend of all runs in the period, from tokens × your price settings." />
            <Kpi icon={PlayCircle} label="Runs" value={t.runs} sub={`${t.succeeded} succeeded · ${t.failed} failed`} info="Work sessions started in the period, including follow-up runs after approvals." />
            <Kpi icon={TrendingUp} label="Success rate" value={pct(t.success_rate)} sub="of finished runs" info="Succeeded ÷ (succeeded + failed + timed out). Runs still queued, running or waiting are left out." />
            <Kpi icon={Gauge} label="Tokens" value={tokens(t.input_tokens + t.output_tokens)} sub={`${tokens(t.input_tokens)} in · ${tokens(t.output_tokens)} out`} info="Input tokens are what the model reads (instructions, page snapshots); output tokens are what it writes. Browser pages make input large." />
            <Kpi icon={Timer} label="Avg duration" value={secs(t.avg_duration_s)} sub="per finished run" info="Average wall-clock time from start to end of a run." />
            <Kpi icon={Bug} label="Bugs found" value={t.bugs} sub={tested ? `${pct(t.tests_pass / tested)} of ${tested} tests passed` : 'no tests yet'} info="Bug drafts created by agents, and the share of executed test cases that passed." />
          </div>

          <ChartCard title="Cost and runs per day" description={rangeLabel(range)} info="Bars: number of runs started each day. Line: estimated cost that day (right axis).">
            <ChartContainer
              config={{ runs: { label: 'Runs', color: 'var(--chart-1)' }, cost_usd: { label: 'Cost ($)', color: 'var(--chart-4)' } }}
              className="h-64 w-full"
            >
              <ComposedChart data={d.by_day}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis yAxisId="runs" allowDecimals={false} tickLine={false} axisLine={false} width={28} />
                <YAxis yAxisId="cost" orientation="right" tickLine={false} axisLine={false} width={48} tickFormatter={(v) => `$${v}`} />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => shortDate(String(v))} />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Bar yAxisId="runs" dataKey="runs" fill="var(--color-runs)" radius={4} />
                <Line yAxisId="cost" dataKey="cost_usd" stroke="var(--color-cost_usd)" strokeWidth={2} dot={false} type="monotone" />
              </ComposedChart>
            </ChartContainer>
          </ChartCard>

          <div className="grid gap-4 lg:grid-cols-3">
            <ChartCard title="Runs by outcome" info="How runs ended. 'Needs approval' runs are paused waiting for a human decision.">
              <Donut data={d.by_status as { status: string; count: number }[]} nameKey="status" />
            </ChartCard>
            <ChartCard title="Test results" info="All test cases executed by agents in the period. Pending means planned but not executed (for example when a run stopped early).">
              <Donut data={d.tests_by_status as { status: string; count: number }[]} nameKey="status" />
            </ChartCard>
            <ChartCard title="Bugs by severity" info="Severity is chosen by the agent: critical (blocks core use), high, medium, low.">
              <ChartContainer config={{ count: { label: 'Bugs', color: 'var(--chart-4)' } }} className="h-56 w-full">
                <BarChart data={d.bugs_by_severity}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="severity" tickLine={false} axisLine={false} className="capitalize" />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={24} />
                  <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                  <Bar dataKey="count" radius={4}>
                    {(d.bugs_by_severity as { severity: string }[]).map((b) => (
                      <Cell key={b.severity} fill={STATUS_COLORS[b.severity]} />
                    ))}
                  </Bar>
                </BarChart>
              </ChartContainer>
            </ChartCard>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Cost by model" info="Which Azure deployment the runs used and what they cost. 'scripted' is the fake demo runtime (free).">
              <ChartContainer config={{ cost_usd: { label: 'Cost ($)', color: 'var(--chart-1)' } }} className="h-56 w-full">
                <BarChart data={d.by_model} layout="vertical" margin={{ left: 8 }}>
                  <CartesianGrid horizontal={false} />
                  <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} />
                  <YAxis type="category" dataKey="model" tickLine={false} axisLine={false} width={96} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="cost_usd" fill="var(--color-cost_usd)" radius={4} />
                </BarChart>
              </ChartContainer>
            </ChartCard>
            <ChartCard title="Tokens by model" info="Input vs output tokens per model. Browsing agents read a lot (page snapshots), so input dominates.">
              <ChartContainer
                config={{ input_tokens: { label: 'Input', color: 'var(--chart-1)' }, output_tokens: { label: 'Output', color: 'var(--chart-2)' } }}
                className="h-56 w-full"
              >
                <BarChart data={d.by_model}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="model" tickLine={false} axisLine={false} />
                  <YAxis tickLine={false} axisLine={false} width={48} tickFormatter={(v) => tokens(Number(v))} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <ChartLegend content={<ChartLegendContent />} />
                  <Bar dataKey="input_tokens" stackId="t" fill="var(--color-input_tokens)" />
                  <Bar dataKey="output_tokens" stackId="t" fill="var(--color-output_tokens)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ChartContainer>
            </ChartCard>
          </div>

          <ChartCard title="Model comparison" info="Use this to pick a model: compare success rate, bugs found per run and cost per run side by side.">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Model</TableHead>
                  <TableHead className="text-right">Runs</TableHead>
                  <TableHead className="text-right">Success rate</TableHead>
                  <TableHead className="text-right">Bugs / run</TableHead>
                  <TableHead className="text-right">Avg cost / run</TableHead>
                  <TableHead className="text-right">Avg duration</TableHead>
                  <TableHead className="text-right">Total cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(d.by_model as Record<string, number & string>[]).map((m) => (
                  <TableRow key={m.model}>
                    <TableCell className="font-medium">
                      <span className="inline-flex items-center gap-1.5">
                        <Cpu className="text-muted-foreground size-3.5" /> {m.model}
                      </span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{m.runs}</TableCell>
                    <TableCell className="text-right tabular-nums">{pct(m.success_rate)}</TableCell>
                    <TableCell className="text-right tabular-nums">{m.runs ? (m.bugs / m.runs).toFixed(1) : '—'}</TableCell>
                    <TableCell className="text-right tabular-nums">{usd(m.avg_cost_per_run)}</TableCell>
                    <TableCell className="text-right tabular-nums">{secs(m.avg_duration_s)}</TableCell>
                    <TableCell className="text-right font-medium tabular-nums">{usd(m.cost_usd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ChartCard>

          <ChartCard title="Per agent" info="Spend this calendar month against each agent's monthly budget. At 100% new runs are refused until next month or until you raise the budget.">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {(d.by_agent as Record<string, number & string>[]).map((ag) => {
                const used = ag.monthly_budget_usd ? (ag.month_spend_usd / ag.monthly_budget_usd) * 100 : 0
                return (
                  <div key={ag.agent_id} className="space-y-3 rounded-xl border p-4">
                    <div className="flex items-center gap-2 font-medium">
                      <Bot className="text-primary size-4" /> {ag.agent_name}
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex justify-between text-sm">
                        <span>This month</span>
                        <span className="font-semibold tabular-nums">
                          {usd(ag.month_spend_usd)} / {usd(ag.monthly_budget_usd)}
                        </span>
                      </div>
                      <Progress value={Math.min(100, used)} />
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center text-xs">
                      <div className="rounded-lg border py-2">
                        <div className="text-base font-semibold tabular-nums">{ag.runs}</div>runs
                      </div>
                      <div className="rounded-lg border py-2">
                        <div className="text-base font-semibold tabular-nums">{pct(ag.success_rate)}</div>success
                      </div>
                      <div className="rounded-lg border py-2">
                        <div className="text-base font-semibold tabular-nums">{ag.bugs}</div>bugs
                      </div>
                    </div>
                    <div className="text-muted-foreground text-xs">
                      {usd(ag.cost_usd)} in period · {tokens(ag.input_tokens + ag.output_tokens)} tokens · avg {secs(ag.avg_duration_s)}
                    </div>
                  </div>
                )
              })}
              {d.by_agent.length === 0 && <div className="text-muted-foreground text-sm">No runs in this period.</div>}
            </div>
          </ChartCard>
        </>
      )}
    </>
  )
}
