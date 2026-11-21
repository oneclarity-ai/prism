import { zodResolver } from '@hookform/resolvers/zod'
import { Bot, Globe, ShieldAlert } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { useNavigate } from 'react-router'
import { z } from 'zod'

import type { Task } from '@/api/client'
import { useAgents, useCreateTask, useTargets, useUpdateTask } from '@/api/hooks'
import { ListInput } from '@/components/common/list-input'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel, FieldSeparator } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'

const NONE = '__none__'

const schema = z.object({
  title: z.string().trim().min(1, 'Give the task a title').max(300),
  goal: z.string(),
  agent_id: z.string().min(1, 'Pick an agent'),
  target_app_id: z.string(),
  urls: z.array(z.string()),
  features: z.array(z.string()),
  acceptance_criteria: z.array(z.string()),
  allow_bug_filing: z.boolean(),
  schedule_cron: z.string().max(100),
})
type Values = z.infer<typeof schema>

function defaults(task?: Task, agentId?: string, targetId?: string): Values {
  return {
    title: task?.title ?? '',
    goal: task?.goal ?? '',
    agent_id: task?.agent_id ?? agentId ?? '',
    target_app_id: task?.target_app_id ?? targetId ?? NONE,
    urls: task?.scope.urls ?? [],
    features: task?.scope.features ?? [],
    acceptance_criteria: task?.scope.acceptance_criteria ?? [],
    allow_bug_filing: task?.scope.allow_bug_filing ?? false,
    schedule_cron: task?.schedule_cron ?? '',
  }
}

export function TaskDialog({
  trigger,
  task,
  defaultAgentId,
  defaultTargetId,
}: {
  trigger: ReactNode
  task?: Task
  defaultAgentId?: string
  defaultTargetId?: string
}) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const agents = useAgents()
  const targets = useTargets()
  const create = useCreateTask()
  const update = useUpdateTask(task?.id ?? '')
  const firstAgent = defaultAgentId ?? agents.data?.find((a) => a.role === 'qa')?.id ?? agents.data?.[0]?.id
  const form = useForm<Values>({ resolver: zodResolver(schema), values: defaults(task, firstAgent, defaultTargetId) })
  const pending = create.isPending || update.isPending

  const onSubmit = form.handleSubmit((v) => {
    const body = {
      title: v.title,
      goal: v.goal,
      agent_id: v.agent_id,
      target_app_id: v.target_app_id === NONE ? null : v.target_app_id,
      schedule_cron: v.schedule_cron.trim() || null,
      scope: {
        urls: v.urls,
        features: v.features,
        acceptance_criteria: v.acceptance_criteria,
        allow_bug_filing: v.allow_bug_filing,
        focus: task?.scope.focus ?? '',
      },
    }
    if (task) {
      update.mutate(body, { onSuccess: () => setOpen(false) })
    } else {
      create.mutate(body, {
        onSuccess: (t) => {
          setOpen(false)
          form.reset()
          navigate(`/tasks/${t.id}`)
        },
      })
    }
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[92svh] gap-0 p-0 sm:max-w-2xl">
        <DialogHeader className="border-b p-6">
          <DialogTitle>{task ? 'Edit task' : 'New QA task'}</DialogTitle>
          <DialogDescription>
            Describe what to test. The agent reads this when it runs.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex min-h-0 flex-col">
          <ScrollArea className="max-h-[62svh]">
            <FieldGroup className="p-6">
              <Field data-invalid={!!form.formState.errors.title}>
                <FieldLabel htmlFor="title">Title</FieldLabel>
                <Input id="title" placeholder="Regression test login and password reset" {...form.register('title')} />
                <FieldError errors={[form.formState.errors.title]} />
              </Field>
              <Field>
                <FieldLabel htmlFor="goal">Goal</FieldLabel>
                <Textarea
                  id="goal"
                  rows={3}
                  placeholder="Find bugs in the sign-in flow before the v2.3 release."
                  {...form.register('goal')}
                />
              </Field>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field data-invalid={!!form.formState.errors.agent_id}>
                  <FieldLabel>Agent</FieldLabel>
                  <Controller
                    control={form.control}
                    name="agent_id"
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Pick an agent" />
                        </SelectTrigger>
                        <SelectContent>
                          {(agents.data ?? []).map((a) => (
                            <SelectItem key={a.id} value={a.id}>
                              <Bot /> {a.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                  <FieldError errors={[form.formState.errors.agent_id]} />
                </Field>
                <Field>
                  <FieldLabel>Target app</FieldLabel>
                  <Controller
                    control={form.control}
                    name="target_app_id"
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Pick a target" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={NONE}>No target</SelectItem>
                          {(targets.data ?? []).map((t) => (
                            <SelectItem key={t.id} value={t.id}>
                              <Globe /> {t.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                </Field>
              </div>

              <FieldSeparator>Scope</FieldSeparator>

              <Field>
                <FieldLabel htmlFor="urls">Pages or URLs</FieldLabel>
                <Controller
                  control={form.control}
                  name="urls"
                  render={({ field }) => (
                    <ListInput id="urls" value={field.value} onChange={field.onChange} placeholder="/login, then Enter" />
                  )}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="features">Features</FieldLabel>
                <Controller
                  control={form.control}
                  name="features"
                  render={({ field }) => (
                    <ListInput id="features" value={field.value} onChange={field.onChange} placeholder="Password reset" />
                  )}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="ac">Acceptance criteria</FieldLabel>
                <Controller
                  control={form.control}
                  name="acceptance_criteria"
                  render={({ field }) => (
                    <ListInput
                      id="ac"
                      value={field.value}
                      onChange={field.onChange}
                      placeholder="Given a wrong password, when I sign in, then I see an error"
                    />
                  )}
                />
              </Field>

              <Controller
                control={form.control}
                name="allow_bug_filing"
                render={({ field }) => (
                  <Field orientation="horizontal" className="rounded-xl border p-4">
                    <ShieldAlert className="mt-0.5 size-5 shrink-0 text-amber-500" />
                    <div className="flex-1 space-y-1">
                      <FieldLabel htmlFor="bugfiling">Allow filing bugs to GitHub / Jira</FieldLabel>
                      <FieldDescription>Each bug still needs your approval before it is filed.</FieldDescription>
                    </div>
                    <Switch id="bugfiling" checked={field.value} onCheckedChange={field.onChange} />
                  </Field>
                )}
              />

              <Field>
                <FieldLabel htmlFor="cron">Schedule (optional)</FieldLabel>
                <Input id="cron" placeholder="0 2 * * *  (every night at 02:00)" className="font-mono" {...form.register('schedule_cron')} />
                <FieldDescription>Cron format, e.g. 0 2 * * * for every night at 02:00. Scheduled runs are not active yet.</FieldDescription>
              </Field>
            </FieldGroup>
          </ScrollArea>
          <DialogFooter className="m-0">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending && <Spinner />}
              {task ? 'Save changes' : 'Create task'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
