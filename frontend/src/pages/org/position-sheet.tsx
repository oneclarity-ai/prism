import { Bot, CircleDashed, Plus, Trash2, User } from 'lucide-react'
import { useState } from 'react'

import type { Position, PositionUpdate } from '@/api/client'
import { useAgentRoles, useAgents, useCreatePosition, useDeletePosition, useUpdatePosition } from '@/api/hooks'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSeparator } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { DEPARTMENTS, LEVELS, descendantIds } from '@/lib/org'

const NONE = '__none__'

type Mode = { kind: 'edit'; position: Position } | { kind: 'new'; parent: Position | null }

type Draft = {
  title: string
  level: Position['level']
  department: string
  holder_type: Position['holder_type']
  holder_name: string
  agent_id: string
  planned_agent_key: string
  description: string
  parent_id: string
}

function initial(mode: Mode): Draft {
  if (mode.kind === 'edit') {
    const p = mode.position
    return {
      title: p.title,
      level: p.level,
      department: p.department,
      holder_type: p.holder_type,
      holder_name: p.holder_name,
      agent_id: p.agent_id ?? NONE,
      planned_agent_key: p.planned_agent_key ?? NONE,
      description: p.description,
      parent_id: p.parent_id ?? NONE,
    }
  }
  const parent = mode.parent
  const nextLevel: Record<string, Position['level']> = {
    ceo: 'executive',
    executive: 'senior_manager',
    senior_manager: 'manager',
    manager: 'member',
    member: 'member',
  }
  return {
    title: '',
    level: parent ? nextLevel[parent.level] : 'ceo',
    department: parent?.department ?? 'Leadership',
    holder_type: 'vacant',
    holder_name: '',
    agent_id: NONE,
    planned_agent_key: NONE,
    description: '',
    parent_id: parent?.id ?? NONE,
  }
}

export function PositionSheet({
  mode,
  positions,
  onClose,
  onAddChild,
}: {
  mode: Mode | null
  positions: Position[]
  onClose: () => void
  onAddChild: (parent: Position) => void
}) {
  return (
    <Sheet open={!!mode} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        {mode && (
          <PositionForm
            key={mode.kind === 'edit' ? mode.position.id : `new-${mode.parent?.id ?? 'root'}`}
            mode={mode}
            positions={positions}
            onClose={onClose}
            onAddChild={onAddChild}
          />
        )}
      </SheetContent>
    </Sheet>
  )
}

function PositionForm({
  mode,
  positions,
  onClose,
  onAddChild,
}: {
  mode: Mode
  positions: Position[]
  onClose: () => void
  onAddChild: (parent: Position) => void
}) {
  const [d, setD] = useState<Draft>(() => initial(mode))
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }))
  const agents = useAgents()
  const roles = useAgentRoles()
  const create = useCreatePosition()
  const update = useUpdatePosition()
  const remove = useDeletePosition()
  const pending = create.isPending || update.isPending
  const editing = mode.kind === 'edit' ? mode.position : null
  const blocked = editing ? new Set([editing.id, ...descendantIds(positions, editing.id)]) : new Set<string>()

  const submit = () => {
    const body = {
      title: d.title.trim(),
      level: d.level,
      department: d.department.trim() || 'Leadership',
      holder_type: d.holder_type,
      holder_name: d.holder_type === 'human' ? d.holder_name.trim() : '',
      agent_id: d.holder_type === 'agent' && d.agent_id !== NONE ? d.agent_id : null,
      planned_agent_key: d.planned_agent_key === NONE ? null : d.planned_agent_key,
      description: d.description,
      parent_id: d.parent_id === NONE ? null : d.parent_id,
      sort_order: editing?.sort_order ?? positions.filter((p) => p.parent_id === (d.parent_id === NONE ? null : d.parent_id)).length,
    } satisfies PositionUpdate
    if (editing) update.mutate({ id: editing.id, body }, { onSuccess: onClose })
    else create.mutate(body, { onSuccess: onClose })
  }

  return (
    <form
      className="flex h-full flex-col"
      onSubmit={(e) => {
        e.preventDefault()
        if (d.title.trim()) submit()
      }}
    >
      <SheetHeader className="border-b">
        <SheetTitle>{editing ? 'Edit position' : 'Add position'}</SheetTitle>
        <SheetDescription>
          A seat in the organization. A person, an AI agent, or nobody yet (vacant) can hold it.
        </SheetDescription>
      </SheetHeader>

      <FieldGroup className="flex-1 p-4">
        <Field>
          <FieldLabel htmlFor="pos-title">Title</FieldLabel>
          <Input id="pos-title" value={d.title} onChange={(e) => set('title', e.target.value)} placeholder="QA Manager" autoFocus />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field>
            <FieldLabel>Level</FieldLabel>
            <Select value={d.level} onValueChange={(v) => set('level', v as Draft['level'])}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LEVELS.map((l) => (
                  <SelectItem key={l.value} value={l.value}>
                    {l.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="pos-dept">Department</FieldLabel>
            <Input id="pos-dept" list="departments" value={d.department} onChange={(e) => set('department', e.target.value)} />
            <datalist id="departments">
              {DEPARTMENTS.map((x) => (
                <option key={x} value={x} />
              ))}
            </datalist>
          </Field>
        </div>
        <Field>
          <FieldLabel>Reports to</FieldLabel>
          <Select value={d.parent_id} onValueChange={(v) => set('parent_id', v)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Nobody (top of the chart)</SelectItem>
              {positions
                .filter((p) => !blocked.has(p.id))
                .map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.title}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </Field>

        <FieldSeparator>Who holds it</FieldSeparator>

        <ToggleGroup
          type="single"
          variant="outline"
          value={d.holder_type}
          onValueChange={(v) => v && set('holder_type', v as Draft['holder_type'])}
          className="w-full"
        >
          <ToggleGroupItem value="vacant" className="flex-1">
            <CircleDashed /> Vacant
          </ToggleGroupItem>
          <ToggleGroupItem value="human" className="flex-1">
            <User /> Person
          </ToggleGroupItem>
          <ToggleGroupItem value="agent" className="flex-1">
            <Bot /> AI agent
          </ToggleGroupItem>
        </ToggleGroup>

        {d.holder_type === 'human' && (
          <Field>
            <FieldLabel htmlFor="pos-name">Name</FieldLabel>
            <Input id="pos-name" value={d.holder_name} onChange={(e) => set('holder_name', e.target.value)} placeholder="Full name" />
          </Field>
        )}
        {d.holder_type === 'agent' && (
          <Field>
            <FieldLabel>Agent</FieldLabel>
            <Select value={d.agent_id} onValueChange={(v) => set('agent_id', v)}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Pick an agent" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>Not assigned yet</SelectItem>
                {(agents.data ?? []).map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    <Bot /> {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        )}
        {d.holder_type !== 'human' && (
          <Field>
            <FieldLabel>Planned agent role</FieldLabel>
            <Select value={d.planned_agent_key} onValueChange={(v) => set('planned_agent_key', v)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>None</SelectItem>
                {(roles.data ?? []).map((r) => (
                  <SelectItem key={r.key} value={r.key}>
                    {r.name} · {r.status}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldDescription>Roles come from backend/app/agents/&lt;role&gt;/. Planned ones are not built yet.</FieldDescription>
          </Field>
        )}
        <Field>
          <FieldLabel htmlFor="pos-desc">Responsibilities</FieldLabel>
          <Textarea
            id="pos-desc"
            rows={3}
            value={d.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="Owns release quality for the web app."
          />
        </Field>
      </FieldGroup>

      <SheetFooter className="flex-row flex-wrap justify-between gap-2 border-t">
        {editing ? (
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => onAddChild(editing)}>
              <Plus /> Add report
            </Button>
            <ConfirmDialog
              title={`Remove "${editing.title}"?`}
              description="People and agents reporting to this position move up to its manager."
              confirmLabel="Remove"
              onConfirm={() => remove.mutate(editing.id, { onSuccess: onClose })}
              trigger={
                <Button type="button" variant="ghost" size="icon" aria-label="Remove position">
                  <Trash2 className="text-destructive" />
                </Button>
              }
            />
          </div>
        ) : (
          <span />
        )}
        <Button type="submit" disabled={pending || !d.title.trim()}>
          {pending && <Spinner />} {editing ? 'Save' : 'Add position'}
        </Button>
      </SheetFooter>
    </form>
  )
}
