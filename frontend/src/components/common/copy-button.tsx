import { Check, Copy } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [done, setDone] = useState(false)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          onClick={async () => {
            await navigator.clipboard.writeText(value)
            setDone(true)
            setTimeout(() => setDone(false), 1500)
          }}
          aria-label={label}
        >
          {done ? <Check className="text-emerald-500" /> : <Copy />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{done ? 'Copied' : label}</TooltipContent>
    </Tooltip>
  )
}

export function IdChip({ id }: { id: string }) {
  return (
    <span className="text-muted-foreground inline-flex items-center gap-1 font-mono text-xs">
      {id.slice(0, 8)}
      <CopyButton value={id} label="Copy ID" />
    </span>
  )
}
