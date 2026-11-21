import { zodResolver } from '@hookform/resolvers/zod'
import {
  ArrowLeft,
  Bot,
  FileText,
  ListChecks,
  Pause,
  Play,
  Plus,
  Save,
  Settings2,
  ShieldCheck,
  Wrench,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Link, useParams } from 'react-router'
import { z } from 'zod'

import type { Agent, ToolGrant } from '@/api/client'
import { useAgent, useSetAgentStatus, useTasks, useUpdateAgent } from '@/api/hooks'
import { JobDescriptionField } from '@/components/agents/job-description-field'
import { AgentStatusBadge, GrantBadge, TaskStatusBadge } from '@/components/common/badges'
import { IdChip } from '@/components/common/copy-button'
import { EmptyState } from '@/components/common/empty-state'
import { InfoTip } from '@/components/common/info-tip'
import { Markdown } from '@/components/common/markdown'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel, FieldSeparator } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupText } from '@/components/ui/input-group'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { GRANTS, KNOWN_TOOLS } from '@/lib/constants'
import { timeAgo } from '@/lib/format'
import { TaskDialog } from '../tasks/task-dialog'

export function AgentDetailPage() {
  const { agentId = '' } = useParams()
  const agent = useAgent(agentId)
  const setStatus = useSetAgentStatus(agentId)

  if (agent.isPending) return <Skeleton className="h-96 w-full" />
  if (agent.isError)
    return (
      <EmptyState
        icon={Bot}
        title="Agent not found"
        description={agent.error.message}
        action={
          <Button variant="outline" asChild>
            <Link to="/agents">
              <ArrowLeft /> Back to agents
            </Link>
          </Button>
        }
      />
    )

  const a = agent.data
  const paused = a.status === 'paused'

  return (
    <>
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-3">
          <Button variant="ghost" size="sm" className="-ml-2" asChild>
            <Link to="/agents">
              <ArrowLeft /> Agents
            </Link>
          </Button>
          <div className="flex items-center gap-4">
            <div className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-md">
              <Bot className="size-7" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-semibold tracking-tight">{a.name}</h1>
                <AgentStatusBadge status={a.status} />
              </div>
              <div className="text-muted-foreground flex items-center gap-2 text-sm">
                <span className="font-mono">{a.key}</span> · <span>{a.role}</span> ·
                <IdChip id={a.id} />
              </div>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <TaskDialog
            defaultAgentId={a.id}
            trigger={
              <Button variant="outline">
                <Plus /> Assign task
              </Button>
            }
          />
          <Button
            variant={paused ? 'default' : 'outline'}
            onClick={() => setStatus.mutate(paused ? 'resume' : 'pause')}
            disabled={setStatus.isPending}
          >
            {setStatus.isPending ? <Spinner /> : paused ? <Play /> : <Pause />}
            {paused ? 'Resume agent' : 'Pause agent'}
          </Button>
        </div>
      </div>

      {paused && (
        <Alert>
          <Pause />
          <AlertTitle>This agent is paused</AlertTitle>
          <AlertDescription>It keeps its tasks but will not start new runs until you resume it.</AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="overview" className="gap-4">
        <TabsList>
          <TabsTrigger value="overview">
            <Settings2 /> Overview
          </TabsTrigger>
          <TabsTrigger value="instructions">
            <FileText /> Instructions
          </TabsTrigger>
          <TabsTrigger value="tools">
            <Wrench /> Tools & permissions
          </TabsTrigger>
          <TabsTrigger value="tasks">
            <ListChecks /> Tasks
          </TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <OverviewTab agent={a} />
        </TabsContent>
        <TabsContent value="instructions">
          <InstructionsTab key={a.updated_at} agent={a} />
        </TabsContent>
        <TabsContent value="tools">
          <ToolsTab key={a.updated_at} agent={a} />
        </TabsContent>
        <TabsContent value="tasks">
          <AgentTasks agent={a} />
        </TabsContent>
      </Tabs>
    </>
  )
}

/* ---------------- Overview ---------------- */

const overviewSchema = z.object({
  name: z.string().trim().min(1, 'Enter a name'),
  role: z.string().trim().min(1, 'Enter a role'),
  description: z.string(),
  runtime: z.string(),
  model: z.string(),
  max_turns: z.coerce.number().int().min(1).max(500),
  run_budget_usd: z.coerce.number().min(0),
  monthly_budget_usd: z.coerce.number().min(0),
})
type OverviewValues = z.input<typeof overviewSchema>

function OverviewTab({ agent }: { agent: Agent }) {
  const update = useUpdateAgent(agent.id)
  const form = useForm<OverviewValues, unknown, z.output<typeof overviewSchema>>({
    resolver: zodResolver(overviewSchema),
    values: {
      name: agent.name,
      role: agent.role,
      description: agent.description,
      runtime: agent.runtime,
      model: agent.model,
      max_turns: agent.max_turns ?? 80,
      run_budget_usd: Number(agent.run_budget_usd),
      monthly_budget_usd: Number(agent.monthly_budget_usd),
    },
  })
  const { errors, isDirty } = form.formState

  return (
    <form onSubmit={form.handleSubmit((v) => update.mutate(v))}>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Profile</CardTitle>
            <CardDescription>Who this agent is and what it is for</CardDescription>
          </CardHeader>
          <CardContent>
            <FieldGroup>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field data-invalid={!!errors.name}>
                  <FieldLabel htmlFor="name">Name</FieldLabel>
                  <Input id="name" {...form.register('name')} />
                  <FieldError errors={[errors.name]} />
                </Field>
                <Field data-invalid={!!errors.role}>
                  <FieldLabel htmlFor="role">Role</FieldLabel>
                  <Input id="role" {...form.register('role')} />
                  <FieldError errors={[errors.role]} />
                </Field>
              </div>
              <Field>
                <FieldLabel htmlFor="description">Job description</FieldLabel>
                <JobDescriptionField
                  id="description"
                  value={form.watch('description')}
                  onChange={(v) => form.setValue('description', v, { shouldDirty: true })}
                  name={form.watch('name')}
                  role={form.watch('role')}
                  rows={14}
                />
              </Field>
              <FieldSeparator>Runtime</FieldSeparator>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field>
                  <FieldLabel>Agent runtime</FieldLabel>
                  <Controller
                    control={form.control}
                    name="runtime"
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="openai_agents">OpenAI Agents SDK · Azure</SelectItem>
                          <SelectItem value="claude_sdk" disabled>
                            Claude Agent SDK (later)
                          </SelectItem>
                          <SelectItem value="fake">Fake: scripted demo, no AI</SelectItem>
                        </SelectContent>
                      </Select>
                    )}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="model">Azure deployment</FieldLabel>
                  <Input id="model" className="font-mono" placeholder="Uses AZURE_OPENAI_DEPLOYMENT" {...form.register('model')} />
                  <FieldDescription>Leave empty to use the default from backend/.env.</FieldDescription>
                </Field>
              </div>
            </FieldGroup>
          </CardContent>
        </Card>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              Limits
              <InfoTip title="Limits">
                <p><b>Max turns</b>: how many model calls one run may make. Each browser click or tool use is a turn; a full regression needs 100+.</p>
                <p><b>Budget per run</b>: the run stops when its estimated cost passes this.</p>
                <p><b>Monthly budget</b>: new runs are refused once this month's spend reaches it.</p>
              </InfoTip>
            </CardTitle>
            <CardDescription>Guardrails enforced on every run</CardDescription>
          </CardHeader>
          <CardContent>
            <FieldGroup>
              <Field data-invalid={!!errors.max_turns}>
                <FieldLabel htmlFor="max_turns">Max turns per run</FieldLabel>
                <Input id="max_turns" type="number" min={1} max={500} {...form.register('max_turns')} />
              </Field>
              <Field data-invalid={!!errors.run_budget_usd}>
                <FieldLabel htmlFor="run_budget">Budget per run</FieldLabel>
                <InputGroup>
                  <InputGroupAddon>
                    <InputGroupText>$</InputGroupText>
                  </InputGroupAddon>
                  <InputGroupInput id="run_budget" type="number" step="0.01" min={0} {...form.register('run_budget_usd')} />
                  <InputGroupAddon align="inline-end">
                    <InputGroupText>USD</InputGroupText>
                  </InputGroupAddon>
                </InputGroup>
              </Field>
              <Field data-invalid={!!errors.monthly_budget_usd}>
                <FieldLabel htmlFor="monthly_budget">Monthly budget</FieldLabel>
                <InputGroup>
                  <InputGroupAddon>
                    <InputGroupText>$</InputGroupText>
                  </InputGroupAddon>
                  <InputGroupInput
                    id="monthly_budget"
                    type="number"
                    step="1"
                    min={0}
                    {...form.register('monthly_budget_usd')}
                  />
                  <InputGroupAddon align="inline-end">
                    <InputGroupText>USD</InputGroupText>
                  </InputGroupAddon>
                </InputGroup>
                <FieldDescription>The agent pauses when this is used up.</FieldDescription>
              </Field>
            </FieldGroup>
          </CardContent>
          <CardFooter className="justify-end gap-2 border-t">
            <Button type="button" variant="ghost" disabled={!isDirty} onClick={() => form.reset()}>
              Reset
            </Button>
            <Button type="submit" disabled={!isDirty || update.isPending}>
              {update.isPending ? <Spinner /> : <Save />} Save
            </Button>
          </CardFooter>
        </Card>
      </div>
    </form>
  )
}

/* ---------------- Instructions ---------------- */

function InstructionsTab({ agent }: { agent: Agent }) {
  const update = useUpdateAgent(agent.id)
  const [text, setText] = useState(agent.instructions)
  const dirty = text !== agent.instructions

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          Instructions
          <InfoTip title="Instructions">
            <p>The agent's playbook (Markdown). It is sent to the model at the start of every run, followed by platform rules for the browser.</p>
            <p>The default comes from <code>backend/app/agents/qa/SKILL.md</code>; edits here change this agent only.</p>
          </InfoTip>
        </CardTitle>
        <CardDescription>
          The agent&apos;s playbook, written in Markdown. It is sent to the model at the start of every run.
        </CardDescription>
        <CardAction className="flex gap-2">
          <Button variant="ghost" disabled={!dirty} onClick={() => setText(agent.instructions)}>
            Discard
          </Button>
          <Button disabled={!dirty || update.isPending} onClick={() => update.mutate({ instructions: text })}>
            {update.isPending ? <Spinner /> : <Save />} Save
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Editor</div>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="h-[560px] resize-none font-mono text-xs leading-relaxed md:text-xs"
            spellCheck={false}
          />
          <div className="text-muted-foreground text-xs">
            {text.length.toLocaleString()} characters · {text.split('\n').length} lines
          </div>
        </div>
        <div className="space-y-2">
          <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Preview</div>
          <ScrollArea className="bg-muted/30 h-[560px] rounded-lg border px-5 py-3">
            {text.trim() ? <Markdown source={text} /> : <p className="text-muted-foreground text-sm">Nothing to preview.</p>}
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  )
}

/* ---------------- Tools ---------------- */

function ToolsTab({ agent }: { agent: Agent }) {
  const update = useUpdateAgent(agent.id)
  const initial = useMemo(() => agent.tool_grants ?? {}, [agent.tool_grants])
  const [grants, setGrants] = useState<Record<string, ToolGrant>>(initial)

  const tools = useMemo(() => {
    const known = KNOWN_TOOLS.map((t) => t.name)
    const extra = Object.keys(initial)
      .filter((n) => !known.includes(n))
      .map((name) => ({ name, label: name, description: 'Custom tool' }))
    return [...KNOWN_TOOLS, ...extra]
  }, [initial])

  const dirty = JSON.stringify(grants) !== JSON.stringify(initial)
  const counts = GRANTS.map((g) => ({ ...g, n: tools.filter((t) => (grants[t.name] ?? 'off') === g.value).length }))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="text-primary size-4" /> Tools & permissions
          <InfoTip title="Tool permissions">
            <p><b>Allowed</b>: the agent uses it freely. <b>Ask first</b>: the run pauses and waits in Approvals. <b>Off</b>: the agent never gets the tool.</p>
            <p>Browser covers navigating, clicking, typing and screenshots on the target app.</p>
          </InfoTip>
        </CardTitle>
        <CardDescription>
          Decide what the agent may do on its own, what needs your approval first, and what it never gets.
        </CardDescription>
        <CardAction className="flex gap-2">
          <Button variant="ghost" disabled={!dirty} onClick={() => setGrants(initial)}>
            Discard
          </Button>
          <Button disabled={!dirty || update.isPending} onClick={() => update.mutate({ tool_grants: grants })}>
            {update.isPending ? <Spinner /> : <Save />} Save
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2 text-sm">
          {counts.map((c) => (
            <div key={c.value} className="flex items-center gap-2 rounded-lg border px-3 py-1.5">
              <GrantBadge grant={c.value} />
              <span className="font-semibold tabular-nums">{c.n}</span>
              <span className="text-muted-foreground text-xs">{c.hint}</span>
            </div>
          ))}
        </div>
        <div className="divide-y rounded-xl border">
          {tools.map((t) => {
            const value = grants[t.name] ?? 'off'
            return (
              <div key={t.name} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 font-medium">
                    {t.label}
                    <code className="text-muted-foreground font-mono text-xs font-normal">{t.name}</code>
                  </div>
                  <div className="text-muted-foreground text-sm">{t.description}</div>
                </div>
                <ToggleGroup
                  type="single"
                  variant="outline"
                  size="sm"
                  value={value}
                  onValueChange={(v) => v && setGrants((g) => ({ ...g, [t.name]: v as ToolGrant }))}
                >
                  {GRANTS.map((g) => (
                    <ToggleGroupItem
                      key={g.value}
                      value={g.value}
                      className="data-[state=on]:bg-primary data-[state=on]:text-primary-foreground px-3"
                    >
                      {g.label}
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

/* ---------------- Tasks ---------------- */

function AgentTasks({ agent }: { agent: Agent }) {
  const tasks = useTasks({ agent_id: agent.id })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Assigned tasks</CardTitle>
        <CardDescription>Everything {agent.name} is responsible for</CardDescription>
        <CardAction>
          <TaskDialog
            defaultAgentId={agent.id}
            trigger={
              <Button size="sm">
                <Plus /> Assign task
              </Button>
            }
          />
        </CardAction>
      </CardHeader>
      <CardContent>
        {tasks.isPending ? (
          <Skeleton className="h-24" />
        ) : !tasks.data?.length ? (
          <div className="text-muted-foreground py-8 text-center text-sm">No tasks assigned yet.</div>
        ) : (
          <ul className="divide-y">
            {tasks.data.map((t) => (
              <li key={t.id}>
                <Link
                  to={`/tasks/${t.id}`}
                  className="hover:bg-muted/60 -mx-2 flex items-center gap-3 rounded-lg px-2 py-3 transition-colors"
                >
                  <ListChecks className="text-muted-foreground size-4" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{t.title}</div>
                    <div className="text-muted-foreground text-xs">{timeAgo(t.created_at)}</div>
                  </div>
                  <TaskStatusBadge status={t.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
