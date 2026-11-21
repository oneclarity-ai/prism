import { Bot, Network, Play, SlidersHorizontal } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'

import type { Agent, RunStart, Task } from '@/api/client'
import { useStartRun } from '@/api/hooks'
import { InfoTip } from '@/components/common/info-tip'
import { ListInput } from '@/components/common/list-input'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { usd } from '@/lib/format'
import { cn } from '@/lib/utils'

// Same defaults as the backend (PARALLEL_DEFAULT_AGENTS, SUBAGENT_MAX_TURNS, SUBAGENT_BUDGET_USD).
const PARALLEL_DEFAULTS = { agents: 3, turns: 80, budget: 1 }
const MAX_CHILDREN = 12

/** Same split rule as the orchestrator: `perAgent` pages each, groups grow above 12 sub-agents. */
function split(pages: string[], perAgent: number): string[][] {
  const size = Math.max(perAgent, Math.ceil(pages.length / MAX_CHILDREN))
  const groups: string[][] = []
  for (let i = 0; i < pages.length; i += size) groups.push(pages.slice(i, i + size))
  return groups
}

function ModeCard({
  active,
  onClick,
  icon: Icon,
  title,
  text,
}: {
  active: boolean
  onClick: () => void
  icon: typeof Bot
  title: string
  text: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex flex-1 items-start gap-3 rounded-xl border p-3 text-left transition-colors',
        active ? 'border-primary bg-primary/5 ring-primary/30 ring-2' : 'hover:bg-muted/50',
      )}
    >
      <Icon className={cn('mt-0.5 size-5 shrink-0', active ? 'text-primary' : 'text-muted-foreground')} />
      <div>
        <div className="text-sm font-medium">{title}</div>
        <div className="text-muted-foreground text-xs">{text}</div>
      </div>
    </button>
  )
}

/** "Run with options": pick pages, one agent or parallel sub-agents, and per-agent limits. */
export function RunDialog({ task, agent, trigger }: { task: Task; agent?: Agent; trigger: ReactNode }) {
  const navigate = useNavigate()
  const start = useStartRun()
  const taskPages = task.scope.urls ?? []
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<string[]>(taskPages)
  const [extra, setExtra] = useState<string[]>([])
  const [mode, setMode] = useState<'single' | 'parallel'>(taskPages.length > 3 ? 'parallel' : 'single')
  const [agents, setAgents] = useState(PARALLEL_DEFAULTS.agents)
  const [perAgent, setPerAgent] = useState(1)
  const [turns, setTurns] = useState('')
  const [budget, setBudget] = useState('')

  const pages = useMemo(() => [...selected, ...extra.filter((p) => !selected.includes(p))], [selected, extra])
  const groups = mode === 'parallel' ? split(pages, perAgent) : []
  const defaultTurns = mode === 'parallel' ? PARALLEL_DEFAULTS.turns : (agent?.max_turns ?? 80)
  const defaultBudget = mode === 'parallel' ? PARALLEL_DEFAULTS.budget : Number(agent?.run_budget_usd ?? 3)
  const perAgentBudget = budget ? Number(budget) : defaultBudget
  const nAgents = mode === 'parallel' ? Math.max(groups.length, 1) : 1
  const allSelected = selected.length === taskPages.length

  function toggle(page: string, on: boolean) {
    setSelected((prev) => (on ? [...prev, page] : prev.filter((p) => p !== page)))
  }

  function submit() {
    const options: RunStart = {
      mode,
      pages: pages.length && (pages.length !== taskPages.length || extra.length) ? pages : null,
      max_parallel: mode === 'parallel' ? agents : null,
      pages_per_agent: perAgent,
      max_turns: turns ? Number(turns) : null,
      budget_usd: budget ? Number(budget) : null,
    }
    start.mutate(
      { taskId: task.id, options },
      {
        onSuccess: (run) => {
          setOpen(false)
          navigate(`/runs/${run.id}`)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SlidersHorizontal className="text-primary size-4" /> Run with options
          </DialogTitle>
          <DialogDescription>Choose the pages for this run and how many agents work on them.</DialogDescription>
        </DialogHeader>

        <FieldGroup>
          <Field>
            <FieldLabel className="flex items-center gap-1.5">
              Pages to test
              <InfoTip title="Pages for this run">
                <p>Untick pages to skip them in this run only; the task keeps its full list.</p>
                <p>Add a page below to test it once without editing the task. Fewer pages = shorter, cheaper run.</p>
              </InfoTip>
              {taskPages.length > 0 && (
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="ml-auto h-auto p-0"
                  onClick={() => setSelected(allSelected ? [] : taskPages)}
                >
                  {allSelected ? 'Select none' : 'Select all'}
                </Button>
              )}
            </FieldLabel>
            {taskPages.length > 0 ? (
              <div className="grid max-h-48 gap-1 overflow-y-auto rounded-lg border p-2 sm:grid-cols-2">
                {taskPages.map((p) => (
                  <label key={p} className="hover:bg-muted flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5">
                    <Checkbox checked={selected.includes(p)} onCheckedChange={(v) => toggle(p, v === true)} />
                    <span className="truncate font-mono text-xs">{p}</span>
                  </label>
                ))}
              </div>
            ) : (
              <FieldDescription>
                This task lists no pages. The agent works from the features and acceptance criteria, or add pages
                below.
              </FieldDescription>
            )}
            <ListInput value={extra} onChange={setExtra} placeholder="Add a page for this run, e.g. /pricing" />
            <FieldDescription>{pages.length || 'No'} page(s) selected.</FieldDescription>
          </Field>

          <Field>
            <FieldLabel>How to run</FieldLabel>
            <div className="flex flex-col gap-2 sm:flex-row">
              <ModeCard
                active={mode === 'single'}
                onClick={() => setMode('single')}
                icon={Bot}
                title="One agent"
                text="Tests the pages one after another in one browser. Best for 1–3 pages."
              />
              <ModeCard
                active={mode === 'parallel'}
                onClick={() => setMode('parallel')}
                icon={Network}
                title="Parallel agents"
                text="An orchestrator splits the pages over sub-agents and merges one final report."
              />
            </div>
          </Field>

          {mode === 'parallel' && (
            <div className="bg-muted/40 space-y-3 rounded-xl border p-3">
              <div className="grid grid-cols-2 gap-3">
                <Field>
                  <FieldLabel htmlFor="rd-agents">Agents at once</FieldLabel>
                  <Input
                    id="rd-agents"
                    type="number"
                    min={1}
                    max={8}
                    value={agents}
                    onChange={(e) => setAgents(Math.min(8, Math.max(1, Number(e.target.value) || 1)))}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="rd-per">Pages per agent</FieldLabel>
                  <Input
                    id="rd-per"
                    type="number"
                    min={1}
                    max={10}
                    value={perAgent}
                    onChange={(e) => setPerAgent(Math.min(10, Math.max(1, Number(e.target.value) || 1)))}
                  />
                </Field>
              </div>
              <div className="space-y-1.5">
                <div className="text-muted-foreground text-xs">
                  {groups.length} sub-agent(s), {Math.min(agents, groups.length || 1)} working at once; the rest wait
                  in the queue.
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {groups.map((g, i) => (
                    <Badge key={i} variant="outline" className="font-mono text-[11px]">
                      #{i + 1} {g.join(', ')}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field>
              <FieldLabel htmlFor="rd-turns">Max turns {mode === 'parallel' && 'per agent'}</FieldLabel>
              <Input
                id="rd-turns"
                type="number"
                min={5}
                max={300}
                placeholder={String(defaultTurns)}
                value={turns}
                onChange={(e) => setTurns(e.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="rd-budget">Budget {mode === 'parallel' && 'per agent'} ($)</FieldLabel>
              <Input
                id="rd-budget"
                type="number"
                min={0.05}
                step={0.05}
                placeholder={defaultBudget.toFixed(2)}
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
              />
            </Field>
          </div>
          <FieldDescription>
            Worst case: {nAgents} agent(s) × {usd(perAgentBudget)} = <b>{usd(nAgents * perAgentBudget)}</b>. Each agent
            stops at its own turn or budget limit; results recorded so far are kept.
          </FieldDescription>
        </FieldGroup>

        <DialogFooter className="mt-2">
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={start.isPending || (taskPages.length > 0 && pages.length === 0)}>
            {start.isPending ? <Spinner /> : mode === 'parallel' ? <Network /> : <Play />}
            {mode === 'parallel' ? `Start ${nAgents} agents` : 'Start run'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
