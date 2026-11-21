import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { InfoTip } from './info-tip'

export function PageHeader({
  icon: Icon,
  title,
  description,
  actions,
  info,
}: {
  icon?: LucideIcon
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  /** Longer explanation shown behind an "i" button next to the title. */
  info?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex items-start gap-3">
        {Icon && (
          <div className="bg-primary/10 text-primary flex size-10 shrink-0 items-center justify-center rounded-xl">
            <Icon className="size-5" />
          </div>
        )}
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            {title}
            {info && <InfoTip title={typeof title === 'string' ? title : undefined}>{info}</InfoTip>}
          </h1>
          {description && <p className="text-muted-foreground mt-1 text-sm">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
