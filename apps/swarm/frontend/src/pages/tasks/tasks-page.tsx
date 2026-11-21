import { Bot, Columns3, Globe, List, ListChecks, Plus, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import type { Task, TaskStatus } from '@/api/client'
import { useAgents, useTargets, useTasks } from '@/api/hooks'
import { TaskStatusBadge } from '@/components/common/badges'
import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/common/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { TASK_STATUSES } from '@/lib/constants'
import { timeAgo } from '@/lib/format'
import { TaskDialog } from './task-dialog'

const ALL = 'all'

function readView(): 'table' | 'board' {
  try {
    return localStorage.getItem('oc.tasks.view') === 'board' ? 'board' : 'table'
  } catch {
    return 'table'
  }
}

export function TasksPage() {
  const navigate = useNavigate()
  const tasks = useTasks()
  const agents = useAgents()
  const targets = useTargets()
  const [status, setStatus] = useState<string>(ALL)
  const [agentId, setAgentId] = useState<string>(ALL)
  const [targetId, setTargetId] = useState<string>(ALL)
  const [query, setQuery] = useState('')
  const [view, setView] = useState<'table' | 'board'>(readView)

  // Sub-tasks of parallel runs are opened from their parent task, not listed here.
  const all = useMemo(() => (tasks.data ?? []).filter((t) => !t.parent_id), [tasks.data])
  const filtered = useMemo(
    () =>
      all.filter(
        (t) =>
          (agentId === ALL || t.agent_id === agentId) &&
          (targetId === ALL || t.target_app_id === targetId) &&
          (!query || `${t.title} ${t.goal}`.toLowerCase().includes(query.toLowerCase())),
      ),
    [all, agentId, targetId, query],
  )
  const shown = status === ALL ? filtered : filtered.filter((t) => t.status === status)
  const count = (s: TaskStatus) => filtered.filter((t) => t.status === s).length
  const agentName = (id: string) => agents.data?.find((a) => a.id === id)?.name ?? '—'
  const targetName = (id?: string | null) => (id ? (targets.data?.find((t) => t.id === id)?.name ?? '—') : '—')

  const changeView = (v: string) => {
    if (!v) return
    setView(v as 'table' | 'board')
    try {
      localStorage.setItem('oc.tasks.view', v)
    } catch {
      /* storage unavailable */
    }
  }

  return (
    <>
      <PageHeader
        icon={ListChecks}
        title="Tasks"
        info={
          <>
            <p>A task is a piece of work for an agent: goal, pages, features and acceptance criteria.</p>
            <p>Press <b>Run now</b> on a task to start a run. Statuses: To do → In progress → Done / Blocked / Failed.</p>
          </>
        }
        description="Work assigned to your agents. Every task can trace back to a goal."
        actions={
          <TaskDialog
            trigger={
              <Button>
                <Plus /> New task
              </Button>
            }
          />
        }
      />

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <InputGroup className="lg:max-w-xs">
          <InputGroupInput placeholder="Search tasks…" value={query} onChange={(e) => setQuery(e.target.value)} />
          <InputGroupAddon>
            <Search />
          </InputGroupAddon>
        </InputGroup>
        <Select value={agentId} onValueChange={setAgentId}>
          <SelectTrigger className="lg:w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>
              <Bot /> All agents
            </SelectItem>
            {(agents.data ?? []).map((a) => (
              <SelectItem key={a.id} value={a.id}>
                <Bot /> {a.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={targetId} onValueChange={setTargetId}>
          <SelectTrigger className="lg:w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>
              <Globe /> All targets
            </SelectItem>
            {(targets.data ?? []).map((t) => (
              <SelectItem key={t.id} value={t.id}>
                <Globe /> {t.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <ToggleGroup type="single" variant="outline" value={view} onValueChange={changeView} className="lg:ml-auto">
          <ToggleGroupItem value="table" aria-label="Table view">
            <List />
          </ToggleGroupItem>
          <ToggleGroupItem value="board" aria-label="Board view">
            <Columns3 />
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      {view === 'table' && (
        <Tabs value={status} onValueChange={setStatus}>
          <TabsList className="h-auto flex-wrap">
            <TabsTrigger value={ALL}>
              All <Badge variant="secondary">{filtered.length}</Badge>
            </TabsTrigger>
            {TASK_STATUSES.map((s) => (
              <TabsTrigger key={s.value} value={s.value}>
                <s.icon className={s.tone} /> {s.label}
                <Badge variant="secondary">{count(s.value)}</Badge>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      )}

      {tasks.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : all.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="No tasks yet"
          description="Create a QA task: pick the app, describe what to test, and the QA agent takes it from there."
          action={
            <TaskDialog
              trigger={
                <Button>
                  <Plus /> Create first task
                </Button>
              }
            />
          }
        />
      ) : view === 'table' ? (
        <Card className="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Task</TableHead>
                <TableHead>Agent</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="pr-4 text-right">Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-muted-foreground h-24 text-center">
                    No tasks match these filters.
                  </TableCell>
                </TableRow>
              )}
              {shown.map((t) => (
                <TableRow key={t.id} className="cursor-pointer" onClick={() => navigate(`/tasks/${t.id}`)}>
                  <TableCell className="max-w-md pl-4">
                    <div className="truncate font-medium">{t.title}</div>
                    {t.goal && <div className="text-muted-foreground truncate text-xs">{t.goal}</div>}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1.5 text-sm">
                      <Bot className="text-primary size-3.5" /> {agentName(t.agent_id)}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm">{targetName(t.target_app_id)}</TableCell>
                  <TableCell>
                    <TaskStatusBadge status={t.status} />
                  </TableCell>
                  <TableCell className="text-muted-foreground pr-4 text-right text-sm">{timeAgo(t.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      ) : (
        <Board tasks={filtered} agentName={agentName} targetName={targetName} />
      )}
    </>
  )
}

function Board({
  tasks,
  agentName,
  targetName,
}: {
  tasks: Task[]
  agentName: (id: string) => string
  targetName: (id?: string | null) => string
}) {
  return (
    <div className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-3">
      {TASK_STATUSES.map((s) => {
        const items = tasks.filter((t) => t.status === s.value)
        return (
          <div key={s.value} className="bg-muted/40 flex w-72 shrink-0 flex-col gap-2 rounded-xl border p-2">
            <div className="flex items-center gap-2 px-1 py-1 text-sm font-medium">
              <s.icon className={`size-4 ${s.tone}`} /> {s.label}
              <Badge variant="secondary" className="ml-auto">
                {items.length}
              </Badge>
            </div>
            {items.map((t) => (
              <Link
                key={t.id}
                to={`/tasks/${t.id}`}
                className="bg-card hover:border-primary/40 space-y-2 rounded-lg border p-3 shadow-xs transition-colors"
              >
                <div className="line-clamp-2 text-sm font-medium">{t.title}</div>
                <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
                  <Bot className="size-3" /> {agentName(t.agent_id)}
                </div>
                <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
                  <Globe className="size-3 shrink-0" />
                  <span className="truncate">{targetName(t.target_app_id)}</span>
                </div>
                <div className="text-muted-foreground border-t pt-2 text-[11px]">{timeAgo(t.created_at)}</div>
              </Link>
            ))}
            {items.length === 0 && <div className="text-muted-foreground py-6 text-center text-xs">Empty</div>}
          </div>
        )
      })}
    </div>
  )
}
