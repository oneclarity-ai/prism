import { zodResolver } from '@hookform/resolvers/zod'
import { Eye, EyeOff, KeyRound, Lock, Plus, ShieldCheck, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { useCreateSecret, useDeleteSecret, useSecrets } from '@/api/hooks'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/common/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
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
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { timeAgo } from '@/lib/format'

const schema = z.object({
  name: z.string().trim().min(1, 'Enter a name').max(200),
  value: z.string().min(1, 'Enter the secret value'),
  scope: z.string().trim().min(1),
})
type Values = z.infer<typeof schema>

function NewSecretDialog() {
  const [open, setOpen] = useState(false)
  const [show, setShow] = useState(false)
  const create = useCreateSecret()
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: '', value: '', scope: 'general' } })
  const { errors } = form.formState

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus /> New secret
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Store a secret</DialogTitle>
          <DialogDescription>Encrypted at rest. You will not be able to see the value again.</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={form.handleSubmit((v) =>
            create.mutate(v, {
              onSuccess: () => {
                setOpen(false)
                form.reset()
              },
            }),
          )}
        >
          <FieldGroup>
            <Field data-invalid={!!errors.name}>
              <FieldLabel htmlFor="s-name">Name</FieldLabel>
              <Input id="s-name" className="font-mono" placeholder="github-token" {...form.register('name')} />
              <FieldError errors={[errors.name]} />
            </Field>
            <Field data-invalid={!!errors.value}>
              <FieldLabel htmlFor="s-value">Value</FieldLabel>
              <InputGroup>
                <InputGroupInput
                  id="s-value"
                  type={show ? 'text' : 'password'}
                  autoComplete="off"
                  className="font-mono"
                  {...form.register('value')}
                />
                <InputGroupAddon align="inline-end">
                  <InputGroupButton size="icon-xs" onClick={() => setShow((s) => !s)} aria-label="Toggle visibility">
                    {show ? <EyeOff /> : <Eye />}
                  </InputGroupButton>
                </InputGroupAddon>
              </InputGroup>
              <FieldError errors={[errors.value]} />
            </Field>
            <Field>
              <FieldLabel htmlFor="s-scope">Scope</FieldLabel>
              <Input id="s-scope" placeholder="general" {...form.register('scope')} />
              <FieldDescription>Free label, e.g. github, jira, general.</FieldDescription>
            </Field>
          </FieldGroup>
          <DialogFooter className="mt-6">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? <Spinner /> : <Lock />} Encrypt & save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function SecretsPage() {
  const secrets = useSecrets()
  const remove = useDeleteSecret()

  return (
    <>
      <PageHeader
        icon={KeyRound}
        title="Secrets"
        info={
          <>
            <p>Encrypted values agents may need (API tokens, test logins). The value is never shown again after saving.</p>
            <p>Add a secret named <code>github-token</code> to let approved bugs become GitHub issues.</p>
          </>
        }
        description="API tokens and passwords your agents need. Only names are ever shown."
        actions={<NewSecretDialog />}
      />

      <Alert>
        <ShieldCheck />
        <AlertTitle>Write-only vault</AlertTitle>
        <AlertDescription>
          Values are encrypted with the server key and never returned by the API. Test logins added on Target apps
          appear here with the <code className="font-mono">target_login</code> scope.
        </AlertDescription>
      </Alert>

      {secrets.isPending ? (
        <Skeleton className="h-48" />
      ) : !secrets.data?.length ? (
        <EmptyState
          icon={KeyRound}
          title="No secrets stored"
          description="Add tokens such as a GitHub token so approved bugs become GitHub issues."
          action={<NewSecretDialog />}
        />
      ) : (
        <Card className="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Name</TableHead>
                <TableHead>Scope</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="w-12 pr-4" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {secrets.data.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="pl-4">
                    <span className="inline-flex items-center gap-2 font-mono text-sm">
                      <KeyRound className="text-muted-foreground size-3.5" /> {s.name}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{s.scope}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground font-mono tracking-widest">••••••••</TableCell>
                  <TableCell className="text-muted-foreground text-sm">{timeAgo(s.created_at)}</TableCell>
                  <TableCell className="pr-4">
                    <ConfirmDialog
                      title={`Delete secret "${s.name}"?`}
                      description="Agents that rely on it will fail until you add it again. This cannot be undone."
                      onConfirm={() => remove.mutate(s.id)}
                      trigger={
                        <Button variant="ghost" size="icon-sm" aria-label="Delete">
                          <Trash2 className="text-destructive" />
                        </Button>
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </>
  )
}
