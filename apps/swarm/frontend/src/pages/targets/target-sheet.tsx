import { zodResolver } from '@hookform/resolvers/zod'
import { FolderGit2, Globe, KeyRound, Lock, Trash2, User } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

import type { Environment, Target, TargetUpdate } from '@/api/client'
import { useCreateTarget, useUpdateTarget } from '@/api/hooks'
import { InfoTip } from '@/components/common/info-tip'
import { ListInput } from '@/components/common/list-input'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel, FieldSeparator } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { ENVIRONMENTS } from '@/lib/constants'

const url = z.string().trim().url('Enter a full URL, e.g. https://staging.example.com')

const schema = z
  .object({
    name: z.string().trim().min(1, 'Enter a name'),
    base_url: url,
    environment: z.enum(['local', 'dev', 'staging', 'production']),
    username: z.string(),
    password: z.string(),
    repo_url: z.union([url, z.literal('')]),
    notes: z.string(),
    extra_origins: z.array(z.string()),
  })
  .refine((v) => !v.username || v.password, { path: ['password'], message: 'Enter the password for this user' })
  .refine((v) => !v.password || v.username, { path: ['username'], message: 'Enter the username' })
type Values = z.infer<typeof schema>

export function TargetSheet({ trigger, target }: { trigger: ReactNode; target?: Target }) {
  const [open, setOpen] = useState(false)
  const [clearLogin, setClearLogin] = useState(false)
  const create = useCreateTarget()
  const update = useUpdateTarget(target?.id ?? '')
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    values: {
      name: target?.name ?? '',
      base_url: target?.base_url ?? '',
      environment: (target?.environment ?? 'staging') as Values['environment'],
      username: '',
      password: '',
      repo_url: target?.repo_url ?? '',
      notes: target?.notes ?? '',
      extra_origins: target?.extra_origins ?? [],
    },
  })
  const { errors } = form.formState
  const pending = create.isPending || update.isPending

  const onSubmit = form.handleSubmit((v) => {
    const login = v.username ? { username: v.username, password: v.password } : null
    const done = () => {
      setOpen(false)
      setClearLogin(false)
      form.reset()
    }
    if (target) {
      const body: TargetUpdate = {
        name: v.name,
        base_url: v.base_url,
        environment: v.environment,
        repo_url: v.repo_url || null,
        notes: v.notes,
        extra_origins: v.extra_origins,
        clear_test_login: clearLogin && !login,
      }
      if (login) body.test_login = login
      update.mutate(body, { onSuccess: done })
    } else {
      create.mutate(
        {
          name: v.name,
          base_url: v.base_url,
          environment: v.environment as Environment,
          repo_url: v.repo_url || null,
          notes: v.notes,
          extra_origins: v.extra_origins,
          test_login: login,
        },
        { onSuccess: done },
      )
    }
  })

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>{trigger}</SheetTrigger>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
        <form onSubmit={onSubmit} className="flex h-full flex-col">
          <SheetHeader className="border-b">
            <SheetTitle className="flex items-center gap-2">
              <Globe className="text-primary size-4" />
              {target ? 'Edit target app' : 'Add a target app'}
            </SheetTitle>
            <SheetDescription>The web app the QA agent will open in a real browser.</SheetDescription>
          </SheetHeader>

          <FieldGroup className="flex-1 p-4">
            <Field data-invalid={!!errors.name}>
              <FieldLabel htmlFor="t-name">Name</FieldLabel>
              <Input id="t-name" placeholder="Customer portal (staging)" {...form.register('name')} />
              <FieldError errors={[errors.name]} />
            </Field>
            <Field data-invalid={!!errors.base_url}>
              <FieldLabel htmlFor="t-url">Base URL</FieldLabel>
              <InputGroup>
                <InputGroupInput id="t-url" placeholder="https://staging.example.com" {...form.register('base_url')} />
                <InputGroupAddon>
                  <Globe />
                </InputGroupAddon>
              </InputGroup>
              <FieldError errors={[errors.base_url]} />
            </Field>
            <Field>
              <FieldLabel>Environment</FieldLabel>
              <Controller
                control={form.control}
                name="environment"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ENVIRONMENTS.map((e) => (
                        <SelectItem key={e.value} value={e.value}>
                          {e.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              {form.watch('environment') === 'production' && (
                <FieldDescription className="text-amber-600 dark:text-amber-400">
                  Careful: the agent will act on a live system. Prefer staging.
                </FieldDescription>
              )}
            </Field>

            <FieldSeparator>
              <span className="inline-flex items-center gap-1">
                Test login (optional)
                <InfoTip title="Test login">
                  <p>A dedicated test account the agent uses to sign in. Stored encrypted; the agent reads it only during a run and it is masked in logs.</p>
                  <p>Accounts with MFA, CAPTCHA or email codes will block the agent.</p>
                </InfoTip>
              </span>
            </FieldSeparator>

            {target?.has_test_login && !clearLogin && (
              <Alert>
                <Lock />
                <AlertDescription className="flex items-center justify-between gap-2">
                  <span>A test login is stored (encrypted). Enter new values to replace it.</span>
                  <Button type="button" size="xs" variant="ghost" onClick={() => setClearLogin(true)}>
                    <Trash2 /> Remove
                  </Button>
                </AlertDescription>
              </Alert>
            )}
            {clearLogin && (
              <Alert variant="destructive">
                <AlertDescription className="flex items-center justify-between gap-2">
                  The stored login will be deleted on save.
                  <Button type="button" size="xs" variant="ghost" onClick={() => setClearLogin(false)}>
                    Undo
                  </Button>
                </AlertDescription>
              </Alert>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field data-invalid={!!errors.username}>
                <FieldLabel htmlFor="t-user">Username</FieldLabel>
                <InputGroup>
                  <InputGroupInput id="t-user" autoComplete="off" placeholder="qa@example.com" {...form.register('username')} />
                  <InputGroupAddon>
                    <User />
                  </InputGroupAddon>
                </InputGroup>
                <FieldError errors={[errors.username]} />
              </Field>
              <Field data-invalid={!!errors.password}>
                <FieldLabel htmlFor="t-pass">Password</FieldLabel>
                <InputGroup>
                  <InputGroupInput id="t-pass" type="password" autoComplete="new-password" {...form.register('password')} />
                  <InputGroupAddon>
                    <KeyRound />
                  </InputGroupAddon>
                </InputGroup>
                <FieldError errors={[errors.password]} />
              </Field>
            </div>
            <FieldDescription>
              Use a dedicated test account. It is encrypted and only the agent can read it during a run.
            </FieldDescription>

            <FieldSeparator>More</FieldSeparator>

            <Field data-invalid={!!errors.repo_url}>
              <FieldLabel htmlFor="t-repo">Repository (optional)</FieldLabel>
              <InputGroup>
                <InputGroupInput id="t-repo" placeholder="https://github.com/acme/portal" {...form.register('repo_url')} />
                <InputGroupAddon>
                  <FolderGit2 />
                </InputGroupAddon>
              </InputGroup>
              <FieldError errors={[errors.repo_url]} />
            </Field>
            <Field>
              <FieldLabel htmlFor="t-origins">Extra allowed domains</FieldLabel>
              <Controller
                control={form.control}
                name="extra_origins"
                render={({ field }) => (
                  <ListInput
                    id="t-origins"
                    value={field.value}
                    onChange={field.onChange}
                    placeholder="https://login.microsoftonline.com, then Enter"
                  />
                )}
              />
              <FieldDescription>
                The agent's browser may only load the base URL's domain. Add CDNs, the SSO / login provider and API
                hosts the app needs. Use <code className="font-mono">*</code> to allow everything.
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="t-notes">Notes for the agent</FieldLabel>
              <Textarea
                id="t-notes"
                rows={3}
                placeholder="Use test card 4242 4242 4242 4242. Do not delete existing orders."
                {...form.register('notes')}
              />
            </Field>
          </FieldGroup>

          <SheetFooter className="flex-row justify-end border-t">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending && <Spinner />}
              {target ? 'Save changes' : 'Add target'}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  )
}
