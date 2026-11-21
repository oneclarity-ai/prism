import { Bot, Cpu, Plus, ShieldCheck, Wallet } from 'lucide-react'
import { Link } from 'react-router'

import { useAgents, useTasks } from '@/api/hooks'
import { AgentStatusBadge } from '@/components/common/badges'
import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/common/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { usd } from '@/lib/format'
import { AgentCreateDialog } from './agent-create-dialog'

const GRADIENTS = [
  'from-indigo-500 to-violet-500',
  'from-sky-500 to-cyan-500',
  'from-emerald-500 to-teal-500',
  'from-amber-500 to-orange-500',
  'from-rose-500 to-pink-500',
]

export function AgentsPage() {
  const agents = useAgents()
  const tasks = useTasks()

  return (
    <>
      <PageHeader
        icon={Bot}
        title="Agents"
        info={
          <>
            <p>An agent is an AI "employee": a role, instructions, tools it may use, a model and budgets.</p>
            <p>Agent roles are defined in code under <code>backend/app/agents/&lt;role&gt;/</code>; the cards here are the live, editable copies.</p>
          </>
        }
        description="Your AI team. Each agent has a role, instructions, tools and a budget."
        actions={
          <AgentCreateDialog
            trigger={
              <Button>
                <Plus /> New agent
              </Button>
            }
          />
        }
      />

      {agents.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-56" />
          ))}
        </div>
      ) : agents.data?.length === 0 ? (
        <EmptyState
          icon={Bot}
          title="No agents yet"
          description="Run the seed script to create the QA agent, or onboard one here."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {agents.data?.map((a, i) => {
            const grants = Object.values(a.tool_grants ?? {})
            const asks = grants.filter((g) => g === 'ask_first').length
            const allowed = grants.filter((g) => g === 'allowed').length
            const taskCount = tasks.data?.filter((t) => t.agent_id === a.id).length ?? 0
            return (
              <Link key={a.id} to={`/agents/${a.id}`} className="group">
                <Card className="group-hover:border-primary/40 h-full transition-all group-hover:shadow-md">
                  <CardHeader className="flex flex-row items-start gap-4">
                    <div
                      className={`flex size-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br text-white shadow-sm ${GRADIENTS[i % GRADIENTS.length]}`}
                    >
                      <Bot className="size-6" />
                    </div>
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <div className="truncate font-semibold">{a.name}</div>
                        <AgentStatusBadge status={a.status} />
                      </div>
                      <div className="text-muted-foreground font-mono text-xs">{a.key}</div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-muted-foreground line-clamp-2 min-h-10 text-sm">
                      {a.description || 'No description yet.'}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="secondary" className="capitalize">
                        {a.role}
                      </Badge>
                      <Badge variant="outline" className="gap-1">
                        <Cpu className="size-3" /> {a.model || 'default model'}
                      </Badge>
                      <Badge variant="outline">{a.runtime}</Badge>
                    </div>
                  </CardContent>
                  <CardFooter className="text-muted-foreground grid grid-cols-3 gap-2 border-t text-xs">
                    <div>
                      <div className="text-foreground text-base font-semibold tabular-nums">{taskCount}</div>
                      tasks
                    </div>
                    <div>
                      <div className="text-foreground flex items-center gap-1 text-base font-semibold tabular-nums">
                        <ShieldCheck className="size-3.5 text-emerald-500" /> {allowed}
                        {asks > 0 && <span className="text-amber-500">+{asks}</span>}
                      </div>
                      tools
                    </div>
                    <div>
                      <div className="text-foreground flex items-center gap-1 text-base font-semibold tabular-nums">
                        <Wallet className="size-3.5" /> {usd(a.monthly_budget_usd)}
                      </div>
                      monthly budget
                    </div>
                  </CardFooter>
                </Card>
              </Link>
            )
          })}
        </div>
      )}
    </>
  )
}
