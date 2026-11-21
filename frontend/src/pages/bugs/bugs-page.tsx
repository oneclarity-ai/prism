import { Bug as BugIcon, ExternalLink } from 'lucide-react'
import { Fragment, useState } from 'react'
import { Link } from 'react-router'

import { useBugs } from '@/api/hooks'
import { SeverityBadge } from '@/components/common/badges'
import { DateRangeFilter, DayHeader } from '@/components/common/date-range-filter'
import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/common/page-header'
import { BugActions } from '@/components/runs/bug-actions'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { defaultRange, groupByDay, rangeQuery, type DateRange } from '@/lib/date-range'
import { dateTime } from '@/lib/format'

const ALL = 'all'

export function BugsPage() {
  const [severity, setSeverity] = useState(ALL)
  const [status, setStatus] = useState(ALL)
  const [range, setRange] = useState<DateRange>(defaultRange('30d'))
  const bugs = useBugs({
    ...(severity !== ALL ? { severity } : {}),
    ...(status !== ALL ? { status } : {}),
    ...rangeQuery(range),
  })
  const list = bugs.data ?? []

  return (
    <>
      <PageHeader
        icon={BugIcon}
        title="Bugs"
        description="Every bug the agents found, across all runs."
        info={
          <>
            <p>The QA agent drafts a bug for each failed test case it can reproduce, with steps, expected and actual result.</p>
            <p>
              <b>Draft</b>: found, not sent anywhere. <b>Approved</b>: a human approved filing it. <b>Filed</b>: created in
              GitHub. <b>Rejected</b>: a human said it is not a real bug.
            </p>
          </>
        }
      />
      <div className="flex flex-wrap gap-2">
        <DateRangeFilter value={range} onChange={setRange} />
        <Select value={severity} onValueChange={setSeverity}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All severities</SelectItem>
            {['critical', 'high', 'medium', 'low'].map((s) => (
              <SelectItem key={s} value={s} className="capitalize">
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            {['draft', 'approved', 'filed', 'rejected'].map((s) => (
              <SelectItem key={s} value={s} className="capitalize">
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-muted-foreground ml-auto self-center text-sm">{list.length} bugs</span>
      </div>
      {bugs.isPending ? (
        <Skeleton className="h-64" />
      ) : list.length === 0 ? (
        <EmptyState icon={BugIcon} title="No bugs here" description="Run the QA agent on a task; confirmed failures show up as bugs." />
      ) : (
        <div className="space-y-3">
          {groupByDay(list, (b) => b.created_at).map((day) => (
            <Fragment key={day.key}>
              <DayHeader label={day.label} count={day.items.length} noun="bug" />
          {day.items.map((b) => (
            <Card key={b.id}>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <BugIcon className="size-4 text-rose-500" />
                  <span className="font-medium">{b.title}</span>
                  <SeverityBadge severity={b.severity} />
                  <Badge variant="outline" className="capitalize">
                    {b.status}
                  </Badge>
                  <span className="text-muted-foreground ml-auto text-xs">
                    {b.target_name ?? 'No target'} · {b.model ?? 'model ?'} · {dateTime(b.created_at)}
                  </span>
                </div>
                <div className="grid gap-3 text-sm md:grid-cols-3">
                  <div>
                    <div className="text-muted-foreground text-xs font-medium uppercase">Steps</div>
                    <p className="whitespace-pre-wrap">{b.steps}</p>
                  </div>
                  <div>
                    <div className="text-muted-foreground text-xs font-medium uppercase">Expected</div>
                    <p className="whitespace-pre-wrap">{b.expected}</p>
                  </div>
                  <div>
                    <div className="text-muted-foreground text-xs font-medium uppercase">Actual</div>
                    <p className="whitespace-pre-wrap">{b.actual}</p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
                  <BugActions title={b.title} />
                  <Link to={`/runs/${b.run_id}`} className="text-primary inline-flex items-center gap-1 text-sm hover:underline">
                    {b.task_title} <ExternalLink className="size-3.5" />
                  </Link>
                </div>
              </CardContent>
            </Card>
          ))}
            </Fragment>
          ))}
        </div>
      )}
    </>
  )
}
