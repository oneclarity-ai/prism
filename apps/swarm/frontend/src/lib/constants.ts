import {
  Ban,
  CircleCheck,
  Clock,
  Loader,
  Network,
  ShieldQuestion,
  TimerOff,
  CircleDashed,
  CircleDot,
  CircleSlash,
  CircleX,
  type LucideIcon,
} from 'lucide-react'

import type { Environment, RunStatus, TaskStatus, ToolGrant } from '@/api/client'

export const TASK_STATUSES: { value: TaskStatus; label: string; icon: LucideIcon; tone: string }[] = [
  { value: 'todo', label: 'To do', icon: CircleDashed, tone: 'text-muted-foreground' },
  { value: 'in_progress', label: 'In progress', icon: CircleDot, tone: 'text-sky-500' },
  { value: 'blocked', label: 'Blocked', icon: CircleSlash, tone: 'text-amber-500' },
  { value: 'done', label: 'Done', icon: CircleCheck, tone: 'text-emerald-500' },
  { value: 'failed', label: 'Failed', icon: CircleX, tone: 'text-rose-500' },
]

export const ENVIRONMENTS: { value: Environment; label: string; tone: string }[] = [
  { value: 'local', label: 'Local', tone: 'bg-slate-500/10 text-slate-600 dark:text-slate-300' },
  { value: 'dev', label: 'Dev', tone: 'bg-sky-500/10 text-sky-600 dark:text-sky-300' },
  { value: 'staging', label: 'Staging', tone: 'bg-amber-500/10 text-amber-700 dark:text-amber-300' },
  { value: 'production', label: 'Production', tone: 'bg-rose-500/10 text-rose-600 dark:text-rose-300' },
]

export const GRANTS: { value: ToolGrant; label: string; hint: string }[] = [
  { value: 'allowed', label: 'Allowed', hint: 'Agent may use it freely' },
  { value: 'ask_first', label: 'Ask first', hint: 'Pauses for human approval' },
  { value: 'off', label: 'Off', hint: 'Tool is not given to the agent' },
]

/** Tools the platform knows about. Agents can also hold grants for tools not listed here. */
export const KNOWN_TOOLS: { name: string; label: string; description: string }[] = [
  { name: 'get_task_context', label: 'Read task context', description: 'Goal, scope and target app of the task' },
  { name: 'get_test_login', label: 'Read test login', description: 'Username and password for the target app' },
  { name: 'browser', label: 'Browser (Playwright)', description: 'Navigate, click, type, screenshot' },
  { name: 'save_test_plan', label: 'Save test plan', description: 'Write Given / When / Then cases' },
  { name: 'record_test_result', label: 'Record test result', description: 'Pass, fail or blocked with evidence' },
  { name: 'save_artifact', label: 'Save artifact', description: 'Store screenshots and reports' },
  { name: 'draft_bug', label: 'Draft bug', description: 'Prepare a bug report for review' },
  { name: 'file_bug', label: 'File bug externally', description: 'Create an issue in GitHub or Jira' },
  { name: 'add_comment', label: 'Comment on task', description: 'Progress notes on the task' },
  { name: 'complete_task', label: 'Complete task', description: 'Final report and status' },
]

export const RUN_STATUSES: { value: RunStatus; label: string; icon: LucideIcon; tone: string; live?: boolean }[] = [
  { value: 'queued', label: 'Queued', icon: Clock, tone: 'text-muted-foreground', live: true },
  { value: 'running', label: 'Running', icon: Loader, tone: 'text-sky-500', live: true },
  { value: 'waiting_children', label: 'Sub-agents working', icon: Network, tone: 'text-violet-500', live: true },
  { value: 'waiting_approval', label: 'Needs approval', icon: ShieldQuestion, tone: 'text-amber-500' },
  { value: 'succeeded', label: 'Succeeded', icon: CircleCheck, tone: 'text-emerald-500' },
  { value: 'failed', label: 'Failed', icon: CircleX, tone: 'text-rose-500' },
  { value: 'cancelled', label: 'Cancelled', icon: Ban, tone: 'text-muted-foreground' },
  { value: 'timed_out', label: 'Timed out', icon: TimerOff, tone: 'text-rose-500' },
]

export const RUNTIME_LABELS: Record<string, string> = {
  openai_agents: 'OpenAI Agents SDK · Azure',
  fake: 'Fake (scripted demo)',
  orchestrator: 'Orchestrator (parallel)',
  claude_sdk: 'Claude Agent SDK',
}
