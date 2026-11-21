import { cn } from '@/lib/utils'

export function LogoMark({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-white shadow-sm',
        className,
      )}
    >
      <svg viewBox="0 0 24 24" className="size-[60%]" fill="none" stroke="currentColor" strokeWidth="2.4">
        <circle cx="12" cy="12" r="7.5" />
        <path d="M12 4.5v15M4.5 12h15" strokeOpacity="0.55" />
        <circle cx="12" cy="12" r="2.4" fill="currentColor" stroke="none" />
      </svg>
    </div>
  )
}

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn('flex items-center gap-2.5', className)}>
      <LogoMark />
      <div className="leading-tight">
        <div className="font-semibold tracking-tight">OneClarity</div>
        <div className="text-muted-foreground text-xs">Agent Platform</div>
      </div>
    </div>
  )
}
