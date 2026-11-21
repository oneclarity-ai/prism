import { Info } from 'lucide-react'
import type { ReactNode } from 'react'

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

/** Small "i" button that explains a feature. Click (or tap) to open; works on touch screens too. */
export function InfoTip({ title, children, className }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={title ? `About ${title}` : 'More information'}
          className={cn(
            'text-muted-foreground hover:text-primary focus-visible:ring-ring inline-flex size-5 shrink-0 items-center justify-center rounded-full align-middle transition-colors focus-visible:ring-2 focus-visible:outline-none',
            className,
          )}
          onClick={(e) => e.stopPropagation()}
        >
          <Info className="size-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 text-sm leading-relaxed" align="start">
        {title && <div className="mb-1 font-semibold">{title}</div>}
        <div className="text-muted-foreground space-y-2">{children}</div>
      </PopoverContent>
    </Popover>
  )
}
