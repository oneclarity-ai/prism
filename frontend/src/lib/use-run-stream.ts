import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import type { Run, RunEvent } from '@/api/client'
import { keys } from '@/api/hooks'

const REFRESH_ON = new Set(['save_test_plan', 'record_test_result', 'draft_bug', 'file_bug'])

/**
 * Live events of a run over Server-Sent Events.
 * Keeps the run in the query cache fresh and refreshes test cases, bugs and screenshots
 * when the agent's tools change them. Reconnects with `after_seq`, so no event is lost.
 * Mount it once per run (the run page is keyed by run id); bump `nonce` to force a reconnect.
 */
export function useRunStream(runId: string, nonce = 0) {
  const qc = useQueryClient()
  const [events, setEvents] = useState<RunEvent[]>([])
  const [connected, setConnected] = useState(false)
  const lastSeq = useRef(0)

  useEffect(() => {
    let source: EventSource | null = null
    let closed = false
    let retry: ReturnType<typeof setTimeout> | undefined

    const open = () => {
      source = new EventSource(`/api/v1/runs/${runId}/stream?after_seq=${lastSeq.current}`)
      source.onopen = () => setConnected(true)
      source.addEventListener('run_event', (msg) => {
        const ev = JSON.parse((msg as MessageEvent).data) as RunEvent
        if (ev.seq <= lastSeq.current) return
        lastSeq.current = ev.seq
        setEvents((prev) => [...prev, ev])
        const tool = (ev.payload as { tool?: string }).tool
        if (ev.type === 'tool_result' && tool && REFRESH_ON.has(tool)) {
          qc.invalidateQueries({ queryKey: keys.runPart(runId, 'test-cases') })
          qc.invalidateQueries({ queryKey: keys.runPart(runId, 'bugs') })
        }
        if (ev.type === 'artifact' || (ev.type === 'tool_result' && tool?.includes('screenshot'))) {
          qc.invalidateQueries({ queryKey: keys.runPart(runId, 'artifacts') })
        }
        if (ev.type === 'subagent' || ev.type === 'plan') {
          qc.invalidateQueries({ queryKey: keys.runPart(runId, 'subagents') })
          qc.invalidateQueries({ queryKey: keys.runPart(runId, 'test-cases') })
          qc.invalidateQueries({ queryKey: keys.runPart(runId, 'bugs') })
          qc.invalidateQueries({ queryKey: keys.runPart(runId, 'artifacts') })
        }
        if (ev.type === 'status') {
          qc.invalidateQueries({ queryKey: ['approvals'] })
          qc.invalidateQueries({ queryKey: ['tasks'] })
          qc.invalidateQueries({ queryKey: ['task'] })
        }
      })
      source.addEventListener('run', (msg) => {
        const run = JSON.parse((msg as MessageEvent).data) as Run
        qc.setQueryData(keys.run(runId), run)
        qc.invalidateQueries({ queryKey: ['runs'] })
      })
      source.addEventListener('end', () => {
        closed = true
        source?.close()
        setConnected(false)
        qc.invalidateQueries({ queryKey: keys.runPart(runId, 'test-cases') })
        qc.invalidateQueries({ queryKey: keys.runPart(runId, 'bugs') })
        qc.invalidateQueries({ queryKey: keys.runPart(runId, 'artifacts') })
      })
      source.onerror = () => {
        source?.close()
        setConnected(false)
        if (!closed) retry = setTimeout(open, 2000)
      }
    }

    open()
    return () => {
      closed = true
      clearTimeout(retry)
      source?.close()
    }
  }, [runId, qc, nonce])

  return { events, connected }
}
