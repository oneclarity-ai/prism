import { CalendarDays } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DATE_PRESETS, type DatePreset, type DateRange } from '@/lib/date-range'
import { cn } from '@/lib/utils'

/** Period picker used on every list and dashboard: presets plus a custom from / to range. */
export function DateRangeFilter({
  value,
  onChange,
  className,
}: {
  value: DateRange
  onChange: (next: DateRange) => void
  className?: string
}) {
  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <Select value={value.preset} onValueChange={(v) => onChange({ ...value, preset: v as DatePreset })}>
        <SelectTrigger className="w-44">
          <CalendarDays className="text-muted-foreground" />
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {DATE_PRESETS.map((p) => (
            <SelectItem key={p.value} value={p.value}>
              {p.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {value.preset === 'custom' && (
        <div className="flex items-center gap-1.5 text-sm">
          <Input
            type="date"
            aria-label="From"
            className="w-38"
            value={value.from ?? ''}
            max={value.to}
            onChange={(e) => onChange({ ...value, from: e.target.value || undefined })}
          />
          <span className="text-muted-foreground">to</span>
          <Input
            type="date"
            aria-label="To"
            className="w-38"
            value={value.to ?? ''}
            min={value.from}
            onChange={(e) => onChange({ ...value, to: e.target.value || undefined })}
          />
        </div>
      )}
    </div>
  )
}

/** Sticky header row that separates days in a date-wise list. */
export function DayHeader({ label, count, noun }: { label: string; count: number; noun: string }) {
  return (
    <div className="bg-background/90 sticky top-0 z-10 flex items-center gap-2 py-1.5 backdrop-blur">
      <CalendarDays className="text-muted-foreground size-4" />
      <span className="text-sm font-semibold">{label}</span>
      <span className="text-muted-foreground text-xs">
        {count} {noun}
        {count === 1 ? '' : 's'}
      </span>
      <div className="bg-border h-px flex-1" />
    </div>
  )
}
