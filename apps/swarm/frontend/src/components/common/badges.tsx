import type { Environment, RunStatus, TaskStatus, ToolGrant } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { ENVIRONMENTS, RUN_STATUSES, TASK_STATUSES } from '@/lib/constants'
import { cn } from '@/lib/utils'

export function TaskStatusBadge({ status, className }: { status: TaskStatus; className?: string }) {
  const s = TASK_STATUSES.find((x) => x.value === status) ?? TASK_STATUSES[0]
  const Icon = s.icon
  return (
    <Badge variant="outline" className={cn('gap-1 font-medium', className)}>
      <Icon className={cn('size-3.5', s.tone)} />
      {s.label}
    </Badge>
  )
}

export function AgentStatusBadge({ status }: { status: string }) {
  const active = status === 'active'
  return (
    <Badge
      variant="outline"
      className={cn(
        'gap-1.5 font-medium',
        active ? 'border-emerald-500/30 text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300',
      )}
    >
      <span className={cn('size-1.5 rounded-full', active ? 'animate-pulse bg-emerald-500' : 'bg-amber-500')} />
      {active ? 'Active' : 'Paused'}
    </Badge>
  )
}

export function EnvironmentBadge({ env }: { env: Environment }) {
  const e = ENVIRONMENTS.find((x) => x.value === env) ?? ENVIRONMENTS[0]
  return <Badge className={cn('border-0 font-medium', e.tone)}>{e.label}</Badge>
}

export function GrantBadge({ grant }: { grant: ToolGrant }) {
  const tone = {
    allowed: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    ask_first: 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
    off: 'bg-muted text-muted-foreground',
  }[grant]
  const label = { allowed: 'Allowed', ask_first: 'Ask first', off: 'Off' }[grant]
  return <Badge className={cn('border-0 font-medium', tone)}>{label}</Badge>
}

export function RunStatusBadge({ status, className }: { status: RunStatus; className?: string }) {
  const s = RUN_STATUSES.find((x) => x.value === status) ?? RUN_STATUSES[0]
  const Icon = s.icon
  return (
    <Badge variant="outline" className={cn('gap-1 font-medium', className)}>
      <Icon className={cn('size-3.5', s.tone, status === 'running' && 'animate-spin')} />
      {s.label}
    </Badge>
  )
}

export function TestStatusBadge({ status }: { status: string }) {
  const tone: Record<string, string> = {
    pass: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    fail: 'bg-rose-500/10 text-rose-700 dark:text-rose-300',
    blocked: 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
    skipped: 'bg-muted text-muted-foreground',
    pending: 'bg-muted text-muted-foreground',
  }
  const label: Record<string, string> = { pass: 'Pass', fail: 'Fail', blocked: 'Blocked', skipped: 'Skipped', pending: 'Pending' }
  return <Badge className={cn('border-0 font-medium', tone[status])}>{label[status] ?? status}</Badge>
}

export function SeverityBadge({ severity }: { severity: string }) {
  const tone: Record<string, string> = {
    critical: 'bg-rose-600 text-white',
    high: 'bg-rose-500/15 text-rose-700 dark:text-rose-300',
    medium: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
    low: 'bg-muted text-muted-foreground',
  }
  return <Badge className={cn('border-0 font-medium capitalize', tone[severity])}>{severity}</Badge>
}
