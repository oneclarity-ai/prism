import { CircleAlert } from 'lucide-react'

import { useRuntimeStatus } from '@/api/hooks'
import { CopyButton } from '@/components/common/copy-button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

const CMD = './scripts/dev.sh'

/** Shown when no worker process is alive: queued runs would wait forever. */
export function WorkerWarning({ hasQueued = true }: { hasQueued?: boolean }) {
  const status = useRuntimeStatus()
  if (!status.data || status.data.workers_online > 0) return null
  return (
    <Alert variant="destructive">
      <CircleAlert />
      <AlertTitle>No worker is running{hasQueued ? ': queued runs cannot start' : ''}</AlertTitle>
      <AlertDescription>
        <p>
          The worker is the process that executes agent runs. Stop your current terminals and start everything from the
          project folder (API, UI, worker and Demo Shop):
        </p>
        <div className="bg-muted text-foreground mt-1 flex items-center gap-2 rounded-md px-2 py-1 font-mono text-xs">
          {CMD} <CopyButton value={CMD} label="Copy command" />
        </div>
        <p className="mt-1 text-xs">
          Or start only the worker: <code className="font-mono">cd backend &amp;&amp; uv run python -m app.worker.main</code>. Queued
          runs start within a second once it is up.
        </p>
      </AlertDescription>
    </Alert>
  )
}
