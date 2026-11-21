import { Check, ExternalLink, Flag, ShieldQuestion, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import type { Approval } from '@/api/client'
import { useDecide } from '@/api/hooks'
import { SeverityBadge } from '@/components/common/badges'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { timeAgo } from '@/lib/format'

type BugPayload = { title: string; severity: string; steps: string; expected: string; actual: string }

export function ApprovalCard({ approval, showTask = false }: { approval: Approval; showTask?: boolean }) {
  const decide = useDecide()
  const [comment, setComment] = useState('')
  const bug = (approval.payload as { bug?: BugPayload }).bug
  const pending = approval.status === 'pending'

  return (
    <Card className={pending ? 'border-amber-500/40' : ''}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {bug ? <Flag className="size-4 text-rose-500" /> : <ShieldQuestion className="size-4 text-amber-500" />}
          {bug ? 'File this bug in the tracker?' : `Allow "${approval.action}"?`}
        </CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-x-2">
          <span>Requested {timeAgo(approval.created_at)}</span>
          {showTask && approval.task_id && (
            <>
              ·
              <Link to={`/runs/${approval.run_id}`} className="text-primary inline-flex items-center gap-1 hover:underline">
                {approval.task_title} <ExternalLink className="size-3" />
              </Link>
            </>
          )}
        </CardDescription>
        <CardAction>
          {pending ? (
            <Badge className="border-0 bg-amber-500/15 text-amber-700 dark:text-amber-300">Waiting for you</Badge>
          ) : (
            <Badge variant={approval.status === 'approved' ? 'default' : 'secondary'} className="capitalize">
              {approval.status}
            </Badge>
          )}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        {bug ? (
          <div className="space-y-3 rounded-lg border p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="font-medium">{bug.title}</div>
              <SeverityBadge severity={bug.severity} />
            </div>
            <div className="grid gap-3 text-sm md:grid-cols-3">
              <div>
                <div className="text-muted-foreground mb-1 text-xs font-medium uppercase">Steps</div>
                <p className="whitespace-pre-wrap">{bug.steps}</p>
              </div>
              <div>
                <div className="text-muted-foreground mb-1 text-xs font-medium uppercase">Expected</div>
                <p className="whitespace-pre-wrap">{bug.expected}</p>
              </div>
              <div>
                <div className="text-muted-foreground mb-1 text-xs font-medium uppercase">Actual</div>
                <p className="whitespace-pre-wrap">{bug.actual}</p>
              </div>
            </div>
          </div>
        ) : (
          <pre className="bg-muted/60 overflow-auto rounded p-2 font-mono text-xs">
            {JSON.stringify((approval.payload as { arguments?: unknown }).arguments ?? approval.payload, null, 2)}
          </pre>
        )}
        {pending ? (
          <Textarea
            rows={2}
            placeholder="Optional comment for the agent (e.g. why you reject it)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        ) : (
          approval.comment && <p className="text-muted-foreground text-sm">Comment: {approval.comment}</p>
        )}
      </CardContent>
      {pending && (
        <CardFooter className="justify-end gap-2 border-t">
          <Button
            variant="outline"
            disabled={decide.isPending}
            onClick={() => decide.mutate({ id: approval.id, decision: 'reject', comment })}
          >
            <X /> Reject
          </Button>
          <Button disabled={decide.isPending} onClick={() => decide.mutate({ id: approval.id, decision: 'approve', comment })}>
            {decide.isPending ? <Spinner /> : <Check />} Approve
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}
