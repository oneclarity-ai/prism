import { ShieldCheck } from 'lucide-react'
import { useState } from 'react'

import { useApprovals } from '@/api/hooks'
import { DateRangeFilter, DayHeader } from '@/components/common/date-range-filter'
import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/common/page-header'
import { ApprovalCard } from '@/components/runs/approval-card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { defaultRange, groupByDay, rangeQuery, type DateRange } from '@/lib/date-range'

export function ApprovalsPage() {
  const [range, setRange] = useState<DateRange>(defaultRange('30d'))
  const approvals = useApprovals(undefined, rangeQuery(range))
  const [tab, setTab] = useState<'pending' | 'approved' | 'rejected'>('pending')
  const all = approvals.data ?? []
  const shown = all.filter((a) => a.status === tab)

  return (
    <>
      <PageHeader
        icon={ShieldCheck}
        title="Approvals"
        info={
          <>
            <p>Tools marked <b>Ask first</b> (for example filing a bug) pause the run and wait here for you.</p>
            <p>When every request of a run is decided, a follow-up run continues automatically from where the agent stopped.</p>
          </>
        }
        description="Actions your agents want to take that need a human decision first."
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList>
          {(['pending', 'approved', 'rejected'] as const).map((s) => (
            <TabsTrigger key={s} value={s} className="capitalize">
              {s} <Badge variant="secondary">{all.filter((a) => a.status === s).length}</Badge>
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <DateRangeFilter value={range} onChange={setRange} />
      </div>
      {approvals.isPending ? (
        <Skeleton className="h-48" />
      ) : shown.length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title={tab === 'pending' ? 'Nothing waiting for you' : `No ${tab} approvals`}
          description="When an agent wants to do something marked 'Ask first' (like filing a bug), it shows up here."
        />
      ) : (
        <div className="space-y-4">
          {groupByDay(shown, (a) => a.created_at).map((day) => (
            <section key={day.key} className="space-y-3">
              <DayHeader label={day.label} count={day.items.length} noun="request" />
              {day.items.map((a) => (
                <ApprovalCard key={a.id} approval={a} showTask />
              ))}
            </section>
          ))}
        </div>
      )}
    </>
  )
}
