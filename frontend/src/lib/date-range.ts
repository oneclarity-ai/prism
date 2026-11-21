import { format, isToday, isYesterday, startOfDay, startOfMonth, subDays } from 'date-fns'

export type DatePreset = 'today' | 'yesterday' | '7d' | '30d' | '90d' | 'month' | 'all' | 'custom'

/** A period chosen in a date filter. `from` / `to` are local dates (yyyy-MM-dd), both inclusive. */
export type DateRange = { preset: DatePreset; from?: string; to?: string }

export const DATE_PRESETS: { value: DatePreset; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: '90d', label: 'Last 90 days' },
  { value: 'month', label: 'This month' },
  { value: 'all', label: 'All time' },
  { value: 'custom', label: 'Custom range…' },
]

const ymd = (d: Date) => format(d, 'yyyy-MM-dd')
const parse = (s: string) => new Date(`${s}T00:00:00`)

/** Resolve a range to local start (inclusive) and end (exclusive) instants. */
export function bounds(range: DateRange): { start?: Date; end?: Date } {
  const today = startOfDay(new Date())
  const tomorrow = subDays(today, -1)
  switch (range.preset) {
    case 'today':
      return { start: today, end: tomorrow }
    case 'yesterday':
      return { start: subDays(today, 1), end: today }
    case '7d':
      return { start: subDays(today, 6), end: tomorrow }
    case '30d':
      return { start: subDays(today, 29), end: tomorrow }
    case '90d':
      return { start: subDays(today, 89), end: tomorrow }
    case 'month':
      return { start: startOfMonth(today), end: tomorrow }
    case 'custom':
      return {
        start: range.from ? parse(range.from) : undefined,
        end: range.to ? subDays(parse(range.to), -1) : undefined,
      }
    default:
      return {}
  }
}

/** API query params: `since` / `until` as ISO date-times (only the ones that are set). */
export function rangeQuery(range: DateRange): { since?: string; until?: string } {
  const { start, end } = bounds(range)
  return { ...(start ? { since: start.toISOString() } : {}), ...(end ? { until: end.toISOString() } : {}) }
}

export function rangeLabel(range: DateRange): string {
  if (range.preset !== 'custom') return DATE_PRESETS.find((p) => p.value === range.preset)?.label ?? ''
  const f = (s?: string) => (s ? format(parse(s), 'd MMM yyyy') : '…')
  return `${f(range.from)} – ${f(range.to)}`
}

export const defaultRange = (preset: DatePreset = '30d'): DateRange => ({
  preset,
  from: ymd(subDays(new Date(), 6)),
  to: ymd(new Date()),
})

export function dayLabel(d: Date): string {
  if (isToday(d)) return 'Today'
  if (isYesterday(d)) return 'Yesterday'
  return format(d, 'EEEE, d MMM yyyy')
}

/** Group items by local calendar day, newest day first (items keep their order inside a day). */
export function groupByDay<T>(items: T[], at: (item: T) => string): { key: string; label: string; items: T[] }[] {
  const groups = new Map<string, { key: string; label: string; items: T[] }>()
  for (const item of items) {
    const d = new Date(at(item))
    const key = ymd(d)
    if (!groups.has(key)) groups.set(key, { key, label: dayLabel(d), items: [] })
    groups.get(key)!.items.push(item)
  }
  return [...groups.values()].sort((a, b) => b.key.localeCompare(a.key))
}
