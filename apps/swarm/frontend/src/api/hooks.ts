import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  api,
  unwrap,
  type AgentCreate,
  type AgentUpdate,
  type SecretCreate,
  type TargetCreate,
  type TargetUpdate,
  type TaskCreate,
  type TaskStatus,
  type TaskUpdate,
  type RunStart,
  type RunStatus,
  type PositionCreate,
  type PositionUpdate,
} from './client'

export const keys = {
  me: ['me'] as const,
  agents: ['agents'] as const,
  agent: (id: string) => ['agents', id] as const,
  targets: ['targets'] as const,
  target: (id: string) => ['targets', id] as const,
  secrets: ['secrets'] as const,
  tasks: (filters?: object) => ['tasks', filters ?? {}] as const,
  task: (id: string) => ['task', id] as const,
  runs: (filters?: object) => ['runs', filters ?? {}] as const,
  run: (id: string) => ['run', id] as const,
  runPart: (id: string, part: 'test-cases' | 'bugs' | 'artifacts' | 'subagents') => ['run', id, part] as const,
  approvals: (status?: string) => ['approvals', status ?? 'all'] as const,
  usage: ['usage'] as const,
  runtime: ['runtime'] as const,
  positions: ['positions'] as const,
  agentRoles: ['agent-roles'] as const,
}

function onError(error: Error) {
  toast.error(error.message)
}

/* ---------- auth ---------- */

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => unwrap(api.GET('/api/v1/auth/me')),
    retry: false,
    staleTime: 5 * 60_000,
  })
}

export function useLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { email: string; password: string }) => unwrap(api.POST('/api/v1/auth/login', { body })),
    onSuccess: (user) => qc.setQueryData(keys.me, user),
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/auth/logout')),
    onSuccess: () => qc.clear(),
  })
}

/* ---------- agents ---------- */

export function useAgents() {
  return useQuery({ queryKey: keys.agents, queryFn: () => unwrap(api.GET('/api/v1/agents')) })
}

export function useAgent(id: string) {
  return useQuery({
    queryKey: keys.agent(id),
    queryFn: () => unwrap(api.GET('/api/v1/agents/{agent_id}', { params: { path: { agent_id: id } } })),
  })
}

export function useCreateAgent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: AgentCreate) => unwrap(api.POST('/api/v1/agents', { body })),
    onSuccess: (agent) => {
      qc.invalidateQueries({ queryKey: keys.agents })
      toast.success(`Agent "${agent.name}" created`)
    },
    onError,
  })
}

export function useUpdateAgent(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: AgentUpdate) =>
      unwrap(api.PATCH('/api/v1/agents/{agent_id}', { params: { path: { agent_id: id } }, body })),
    onSuccess: (agent) => {
      qc.setQueryData(keys.agent(id), agent)
      qc.invalidateQueries({ queryKey: keys.agents })
      toast.success('Agent saved')
    },
    onError,
  })
}

export function useSetAgentStatus(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (action: 'pause' | 'resume') =>
      action === 'pause'
        ? unwrap(api.POST('/api/v1/agents/{agent_id}/pause', { params: { path: { agent_id: id } } }))
        : unwrap(api.POST('/api/v1/agents/{agent_id}/resume', { params: { path: { agent_id: id } } })),
    onSuccess: (agent) => {
      qc.setQueryData(keys.agent(id), agent)
      qc.invalidateQueries({ queryKey: keys.agents })
      toast.success(agent.status === 'paused' ? `${agent.name} paused` : `${agent.name} is active`)
    },
    onError,
  })
}

/* ---------- targets ---------- */

export function useTargets() {
  return useQuery({ queryKey: keys.targets, queryFn: () => unwrap(api.GET('/api/v1/targets')) })
}

export function useCreateTarget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TargetCreate) => unwrap(api.POST('/api/v1/targets', { body })),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: keys.targets })
      qc.invalidateQueries({ queryKey: keys.secrets })
      toast.success(`Target "${t.name}" added`)
    },
    onError,
  })
}

export function useUpdateTarget(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TargetUpdate) =>
      unwrap(api.PATCH('/api/v1/targets/{target_id}', { params: { path: { target_id: id } }, body })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.targets })
      qc.invalidateQueries({ queryKey: keys.secrets })
      toast.success('Target saved')
    },
    onError,
  })
}

export function useDeleteTarget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE('/api/v1/targets/{target_id}', { params: { path: { target_id: id } } })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.targets })
      qc.invalidateQueries({ queryKey: keys.secrets })
      toast.success('Target deleted')
    },
    onError,
  })
}

/* ---------- secrets ---------- */

export function useSecrets() {
  return useQuery({ queryKey: keys.secrets, queryFn: () => unwrap(api.GET('/api/v1/secrets')) })
}

export function useCreateSecret() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SecretCreate) => unwrap(api.POST('/api/v1/secrets', { body })),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: keys.secrets })
      toast.success(`Secret "${s.name}" stored`)
    },
    onError,
  })
}

export function useDeleteSecret() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE('/api/v1/secrets/{secret_id}', { params: { path: { secret_id: id } } })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.secrets })
      toast.success('Secret deleted')
    },
    onError,
  })
}

/* ---------- tasks ---------- */

export type TaskFilters = { status?: TaskStatus; agent_id?: string; target_app_id?: string }

export function useTasks(filters: TaskFilters = {}) {
  return useQuery({
    queryKey: keys.tasks(filters),
    queryFn: () => unwrap(api.GET('/api/v1/tasks', { params: { query: { ...filters, limit: 200 } } })),
  })
}

export function useTask(id: string) {
  return useQuery({
    queryKey: keys.task(id),
    queryFn: () => unwrap(api.GET('/api/v1/tasks/{task_id}', { params: { path: { task_id: id } } })),
  })
}

export function useCreateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TaskCreate) => unwrap(api.POST('/api/v1/tasks', { body })),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success(`Task "${t.title}" created`)
    },
    onError,
  })
}

export function useUpdateTask(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TaskUpdate) =>
      unwrap(api.PATCH('/api/v1/tasks/{task_id}', { params: { path: { task_id: id } }, body })),
    onSuccess: (t) => {
      qc.setQueryData(keys.task(id), t)
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Task saved')
    },
    onError,
  })
}

/* ---------- runs ---------- */

export function useRuntimeStatus() {
  return useQuery({
    queryKey: keys.runtime,
    queryFn: () => unwrap(api.GET('/api/v1/runtime/status')),
    refetchInterval: 10_000,
  })
}

export type RunFilters = { task_id?: string; status?: RunStatus; top_level?: boolean; since?: string; until?: string }
export type Period = { since?: string; until?: string }

/** Run statuses during which the page keeps refreshing. */
export const ACTIVE_RUN = ['queued', 'running', 'waiting_children']

export function useRuns(filters: RunFilters = {}, live = false) {
  return useQuery({
    queryKey: keys.runs(filters),
    queryFn: () => unwrap(api.GET('/api/v1/runs', { params: { query: { ...filters, limit: 100 } } })),
    refetchInterval: live ? 3000 : false,
  })
}

export function useRun(id: string) {
  return useQuery({
    queryKey: keys.run(id),
    queryFn: () => unwrap(api.GET('/api/v1/runs/{run_id}', { params: { path: { run_id: id } } })),
    // Safety net next to the live stream: keep the status fresh while the run is active.
    refetchInterval: (q) => (q.state.data && ACTIVE_RUN.includes(q.state.data.status) ? 4000 : false),
  })
}

export function useRunTestCases(id: string) {
  return useQuery({
    queryKey: keys.runPart(id, 'test-cases'),
    queryFn: () => unwrap(api.GET('/api/v1/runs/{run_id}/test-cases', { params: { path: { run_id: id } } })),
  })
}

export function useRunBugs(id: string) {
  return useQuery({
    queryKey: keys.runPart(id, 'bugs'),
    queryFn: () => unwrap(api.GET('/api/v1/runs/{run_id}/bugs', { params: { path: { run_id: id } } })),
  })
}

export function useRunArtifacts(id: string) {
  return useQuery({
    queryKey: keys.runPart(id, 'artifacts'),
    queryFn: () => unwrap(api.GET('/api/v1/runs/{run_id}/artifacts', { params: { path: { run_id: id } } })),
  })
}

/** Live lanes of a parallel run (one per sub-agent). Polls while the run is active. */
export function useSubAgents(runId: string, enabled: boolean, live: boolean) {
  return useQuery({
    queryKey: keys.runPart(runId, 'subagents'),
    queryFn: () => unwrap(api.GET('/api/v1/runs/{run_id}/subagents', { params: { path: { run_id: runId } } })),
    enabled,
    refetchInterval: live ? 2500 : false,
  })
}

/** Start a run. Pass a task id for the default (whole task, one agent), or options. */
export function useStartRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: string | { taskId: string; options?: RunStart }) => {
      const { taskId, options } = typeof input === 'string' ? { taskId: input, options: undefined } : input
      return unwrap(
        api.POST('/api/v1/tasks/{task_id}/runs', { params: { path: { task_id: taskId } }, body: options ?? null }),
      )
    },
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ['runs'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: keys.task(run.task_id) })
      toast.success(run.kind === 'orchestrator' ? 'Parallel run started' : 'Run started')
    },
    onError,
  })
}

export function useCancelRun(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/runs/{run_id}/cancel', { params: { path: { run_id: id } } })),
    onSuccess: (run) => {
      qc.setQueryData(keys.run(id), run)
      qc.invalidateQueries({ queryKey: ['runs'] })
      toast.success(run.status === 'cancelled' ? 'Run cancelled' : 'Stopping the run…')
    },
    onError,
  })
}

/* ---------- approvals ---------- */

export function useApprovals(status?: 'pending' | 'approved' | 'rejected', period: Period = {}) {
  return useQuery({
    queryKey: [...keys.approvals(status), period],
    queryFn: () =>
      unwrap(api.GET('/api/v1/approvals', { params: { query: { ...(status ? { status } : {}), ...period } } })),
    refetchInterval: 5000,
  })
}

export function useDecide() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; decision: 'approve' | 'reject'; comment?: string }) =>
      unwrap(
        api.POST('/api/v1/approvals/{approval_id}/decision', {
          params: { path: { approval_id: v.id } },
          body: { decision: v.decision, comment: v.comment ?? '' },
        }),
      ),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['approvals'] })
      qc.invalidateQueries({ queryKey: ['runs'] })
      qc.invalidateQueries({ queryKey: ['run'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success(
        res.approval.status === 'approved' ? 'Approved' : 'Rejected',
        res.resume_run_id ? { description: 'All decisions made: the agent is continuing.' } : undefined,
      )
    },
    onError,
  })
}

/* ---------- usage ---------- */

export function useUsage() {
  return useQuery({ queryKey: keys.usage, queryFn: () => unwrap(api.GET('/api/v1/usage')) })
}

/* ---------- organization ---------- */

export function usePositions() {
  return useQuery({ queryKey: keys.positions, queryFn: () => unwrap(api.GET('/api/v1/org/positions')) })
}

export function useAgentRoles() {
  return useQuery({
    queryKey: keys.agentRoles,
    queryFn: () => unwrap(api.GET('/api/v1/agent-roles')),
    staleTime: 5 * 60_000,
  })
}

export function useCreatePosition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: PositionCreate) => unwrap(api.POST('/api/v1/org/positions', { body })),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: keys.positions })
      toast.success(`Added "${p.title}"`)
    },
    onError,
  })
}

export function useUpdatePosition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: PositionUpdate }) =>
      unwrap(api.PATCH('/api/v1/org/positions/{position_id}', { params: { path: { position_id: id } }, body })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.positions })
      toast.success('Position saved')
    },
    onError,
  })
}

export function useDeletePosition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE('/api/v1/org/positions/{position_id}', { params: { path: { position_id: id } } })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.positions })
      toast.success('Position removed; its reports moved up')
    },
    onError,
  })
}

/* ---------- analytics & bugs ---------- */

/** Analytics for a period (`since` / `until`); without `since`, the last `days` days. */
export function useAnalytics(period: Period & { days?: number }, agentId?: string) {
  return useQuery({
    queryKey: ['analytics', period, agentId ?? 'all'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/analytics', {
          params: { query: { days: period.days ?? 365, ...period, ...(agentId ? { agent_id: agentId } : {}) } },
        }),
      ),
    refetchInterval: 30_000,
  })
}

export function useBugs(filters: { severity?: string; status?: string } & Period = {}) {
  return useQuery({
    queryKey: ['bugs', filters],
    queryFn: () => unwrap(api.GET('/api/v1/bugs', { params: { query: filters } })),
  })
}

/** Draft an agent's job description with Azure OpenAI. Nothing is saved until the form is submitted. */
export function useGenerateDescription() {
  return useMutation({
    mutationFn: (body: { name: string; role: string; department?: string; notes?: string }) =>
      unwrap(api.POST('/api/v1/agents/generate-description', { body: { department: '', notes: '', ...body } })),
    onError,
  })
}
