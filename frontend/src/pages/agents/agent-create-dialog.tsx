import { zodResolver } from '@hookform/resolvers/zod'
import { useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router'
import { z } from 'zod'

import { useCreateAgent } from '@/api/hooks'
import { JobDescriptionField } from '@/components/agents/job-description-field'
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
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

const schema = z.object({
  name: z.string().trim().min(1, 'Enter a name'),
  key: z
    .string()
    .regex(/^[a-z0-9][a-z0-9_-]{1,63}$/, 'Lowercase letters, numbers, - and _ (2–64 characters)'),
  role: z.string().trim().min(1, 'Enter a role'),
  description: z.string(),
})
type Values = z.infer<typeof schema>

const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 64)

export function AgentCreateDialog({ trigger }: { trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const create = useCreateAgent()
  const navigate = useNavigate()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', key: '', role: '', description: '' },
  })
  const { errors } = form.formState

  const onSubmit = form.handleSubmit((v) =>
    create.mutate(
      {
        ...v,
        instructions: '',
        runtime: 'openai_agents',
        model: '',
        max_turns: 80,
        run_budget_usd: 3,
        monthly_budget_usd: 100,
        tool_grants: {},
      },
      {
      onSuccess: (a) => {
        setOpen(false)
        form.reset()
        navigate(`/agents/${a.id}`)
      },
      },
    ),
  )

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[92svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Onboard a new agent</DialogTitle>
          <DialogDescription>
            An agent is data: a role, instructions, tools and a budget. You can fine-tune everything after creating it.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit}>
          <FieldGroup>
            <Field data-invalid={!!errors.name}>
              <FieldLabel htmlFor="a-name">Name</FieldLabel>
              <Input
                id="a-name"
                placeholder="Sales SDR Agent"
                {...form.register('name', {
                  onChange: (e) => {
                    if (!form.getFieldState('key').isDirty) form.setValue('key', slug(e.target.value))
                  },
                })}
              />
              <FieldError errors={[errors.name]} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field data-invalid={!!errors.key}>
                <FieldLabel htmlFor="a-key">Key</FieldLabel>
                <Input id="a-key" className="font-mono" placeholder="sales-sdr" {...form.register('key')} />
                <FieldError errors={[errors.key]} />
              </Field>
              <Field data-invalid={!!errors.role}>
                <FieldLabel htmlFor="a-role">Role</FieldLabel>
                <Input id="a-role" placeholder="e.g. marketing, sales, qa" {...form.register('role')} />
                <FieldError errors={[errors.role]} />
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="a-desc">What does this agent do?</FieldLabel>
              <JobDescriptionField
                id="a-desc"
                value={form.watch('description')}
                onChange={(v) => form.setValue('description', v, { shouldDirty: true })}
                name={form.watch('name')}
                role={form.watch('role')}
              />
              <FieldDescription>
                Its job description: mission, responsibilities, outcomes and boundaries. People and other agents use it to
                know when to involve this agent. Edit freely.
              </FieldDescription>
            </Field>
          </FieldGroup>
          <DialogFooter className="mt-6">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending && <Spinner />} Create agent
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
