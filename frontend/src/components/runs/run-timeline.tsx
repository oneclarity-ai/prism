import {
  Bot,
  ChevronRight,
  ClipboardList,
  Flag,
  Globe,
  ImageIcon,
  Info,
  KeyRound,
  MessageSquare,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import type { RunEvent } from '@/api/client'
import { RUN_STATUSES } from '@/lib/constants'
import { cn } from '@/lib/utils'

type Step =
  | { kind: 'message'; seq: number; at: string; text: string; comment?: boolean }
  | { kind: 'tool'; seq: number; at: string; tool: string; args: unknown; output?: string }
  | { kind: 'status'; seq: number; at: string; status: string; detail?: string }
  | { kind: 'log'; seq: number; at: string; text: string }
  | { kind: 'artifact'; seq: number; at: string; file: string }

function toSteps(events: RunEvent[]): Step[] {
  const steps: Step[] = []
  const openTools: Record<string, Step & { kind: 'tool' }> = {}
  for (const e of events) {
    const p = e.payload as Record<string, unknown>
    const base = { seq: e.seq, at: e.created_at }
    if (e.type === 'message') steps.push({ ...base, kind: 'message', text: String(p.text ?? ''), comment: p.kind === 'comment' })
    else if (e.type === 'tool_call') {
      const step = { ...base, kind: 'tool' as const, tool: String(p.tool), args: p.arguments }
      openTools[step.tool] = step
      steps.push(step)
    } else if (e.type === 'tool_result') {
      const open = openTools[String(p.tool)]
      if (open && open.output === undefined) open.output = String(p.output ?? '')
      else steps.push({ ...base, kind: 'tool', tool: String(p.tool), args: undefined, output: String(p.output ?? '') })
    } else if (e.type === 'status')
      steps.push({
        ...base,
        kind: 'status',
        status: String(p.status),
        detail: (p.error as string) || (p.summary as string) || (p.resume ? 'Resumed after approval' : undefined),
      })
    else if (e.type === 'log' || e.type === 'subagent') steps.push({ ...base, kind: 'log', text: String(p.text ?? '') })
    else if (e.type === 'plan') {
      const subs = (p.subagents as { index: number; label: string }[] | undefined) ?? []
      steps.push({
        ...base,
        kind: 'log',
        text: `Plan: ${subs.length} sub-agents (${p.max_parallel} at once): ${subs.map((x) => `#${x.index} ${x.label}`).join(' · ')}`,
      })
    }
    else if (e.type === 'artifact') steps.push({ ...base, kind: 'artifact', file: String(p.file ?? '') })
  }
  return steps
}

function toolIcon(tool: string): LucideIcon {
  if (tool.startsWith('browser_take_screenshot')) return ImageIcon
  if (tool.startsWith('browser_')) return Globe
  if (tool === 'get_test_login') return KeyRound
  if (tool === 'save_test_plan' || tool === 'record_test_result') return ClipboardList
  if (tool === 'draft_bug' || tool === 'file_bug') return Flag
  return Wrench
}

function toolLabel(tool: string, args: unknown): string {
  const a = (args ?? {}) as Record<string, unknown>
  switch (tool) {
    case 'browser_navigate':
      return `Open ${a.url}`
    case 'browser_click':
      return `Click ${a.element ?? a.ref ?? ''}`
    case 'browser_type':
      return `Type into ${a.element ?? 'field'}`
    case 'browser_fill_form':
      return 'Fill a form'
    case 'browser_snapshot':
      return 'Read the page'
    case 'browser_take_screenshot':
      return `Screenshot ${a.filename ?? ''}`
    case 'record_test_result':
      return `Result: ${a.case} → ${a.status}`
    case 'save_test_plan':
      return 'Save test plan'
    case 'draft_bug':
      return `Draft bug: ${a.title ?? ''}`
    case 'file_bug':
      return 'File bug (needs approval)'
    case 'complete_task':
      return `Complete task (${a.outcome ?? ''})`
    case 'get_task_context':
      return 'Read the task'
    case 'get_test_login':
      return 'Read the test login'
    default:
      return tool
  }
}

function time(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function ToolStep({ step }: { step: Step & { kind: 'tool' } }) {
  const [open, setOpen] = useState(false)
  const Icon = toolIcon(step.tool)
  const pending = step.output === undefined
  return (
    <div className="rounded-lg border bg-card">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="hover:bg-muted/50 flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm"
      >
        <Icon className={cn('size-4 shrink-0', pending ? 'text-sky-500' : 'text-muted-foreground')} />
        <span className="min-w-0 flex-1 truncate">{toolLabel(step.tool, step.args)}</span>
        {pending && <span className="size-1.5 animate-pulse rounded-full bg-sky-500" />}
        <code className="text-muted-foreground hidden font-mono text-[11px] sm:inline">{step.tool}</code>
        <ChevronRight className={cn('text-muted-foreground size-3.5 transition-transform', open && 'rotate-90')} />
      </button>
      {open && (
        <div className="space-y-2 border-t px-3 py-2">
          {step.args !== undefined && (
            <pre className="bg-muted/60 max-h-48 overflow-auto rounded p-2 font-mono text-[11px] whitespace-pre-wrap">
              {JSON.stringify(step.args, null, 2)}
            </pre>
          )}
          <pre className="bg-muted/60 max-h-72 overflow-auto rounded p-2 font-mono text-[11px] whitespace-pre-wrap">
            {pending ? 'Waiting for result…' : step.output}
          </pre>
        </div>
      )}
    </div>
  )
}

export function RunTimeline({ events, live }: { events: RunEvent[]; live: boolean }) {
  const steps = useMemo(() => toSteps(events), [events])
  const bottom = useRef<HTMLDivElement>(null)
  const [follow, setFollow] = useState(true)

  useEffect(() => {
    if (live && follow) bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [steps.length, live, follow])

  if (!steps.length)
    return (
      <div className="text-muted-foreground flex flex-col items-center gap-2 py-16 text-sm">
        <Bot className="size-8 animate-pulse opacity-50" />
        {live ? 'Waiting for a worker to pick up this run…' : 'No events recorded.'}
      </div>
    )

  return (
    <div className="space-y-2" onWheel={() => setFollow(false)}>
      {steps.map((s) => (
        <div key={s.seq} className="flex gap-3">
          <div className="text-muted-foreground w-16 shrink-0 pt-2 text-right font-mono text-[10px]">{time(s.at)}</div>
          <div className="min-w-0 flex-1">
            {s.kind === 'message' && (
              <div
                className={cn(
                  'flex gap-2.5 rounded-lg px-3 py-2 text-sm',
                  s.comment ? 'bg-primary/10 text-foreground' : 'bg-muted/60',
                )}
              >
                {s.comment ? (
                  <MessageSquare className="text-primary mt-0.5 size-4 shrink-0" />
                ) : (
                  <Bot className="text-primary mt-0.5 size-4 shrink-0" />
                )}
                <p className="leading-relaxed whitespace-pre-wrap">{s.text}</p>
              </div>
            )}
            {s.kind === 'tool' && <ToolStep step={s} />}
            {s.kind === 'status' && <StatusLine status={s.status} detail={s.detail} />}
            {s.kind === 'log' && (
              <div className="text-muted-foreground flex items-center gap-2 px-3 py-1.5 text-xs">
                <Info className="size-3.5" /> {s.text}
              </div>
            )}
            {s.kind === 'artifact' && (
              <div className="text-muted-foreground flex items-center gap-2 px-3 py-1.5 text-xs">
                <ImageIcon className="size-3.5" /> Screenshot saved: {s.file}
              </div>
            )}
          </div>
        </div>
      ))}
      <div ref={bottom} />
      {live && !follow && (
        <button
          type="button"
          className="bg-primary text-primary-foreground sticky bottom-2 ml-auto block rounded-full px-3 py-1 text-xs shadow"
          onClick={() => setFollow(true)}
        >
          Follow live
        </button>
      )}
    </div>
  )
}

function StatusLine({ status, detail }: { status: string; detail?: string }) {
  const s = RUN_STATUSES.find((x) => x.value === status)
  const Icon = s?.icon ?? Info
  return (
    <div className="flex items-center gap-2 px-1 py-1.5 text-xs font-medium">
      <div className="bg-border h-px flex-1" />
      <Icon className={cn('size-3.5', s?.tone)} />
      <span>{s?.label ?? status}</span>
      {detail && <span className="text-muted-foreground max-w-md truncate font-normal">· {detail}</span>}
      <div className="bg-border h-px flex-1" />
    </div>
  )
}
