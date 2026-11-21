import { ImageIcon } from 'lucide-react'
import { useState } from 'react'

import type { Artifact } from '@/api/client'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { timeAgo } from '@/lib/format'

export const artifactUrl = (id: string) => `/api/v1/artifacts/${id}/file`

function name(a: Artifact) {
  return String((a.meta as { source?: string }).source ?? a.id.slice(0, 8))
}

export function LatestScreenshot({ artifacts }: { artifacts: Artifact[] }) {
  const shots = artifacts.filter((a) => a.mime.startsWith('image/'))
  const latest = shots.at(-1)
  const [open, setOpen] = useState(false)
  if (!latest)
    return (
      <div className="bg-muted/40 text-muted-foreground flex aspect-video flex-col items-center justify-center gap-2 rounded-lg border border-dashed text-xs">
        <ImageIcon className="size-6 opacity-50" />
        No screenshot yet
      </div>
    )
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="group block w-full text-left">
        <img
          src={artifactUrl(latest.id)}
          alt={name(latest)}
          className="aspect-video w-full rounded-lg border object-cover object-top transition-opacity group-hover:opacity-90"
        />
        <div className="text-muted-foreground mt-1.5 flex justify-between text-xs">
          <span className="truncate font-mono">{name(latest)}</span>
          <span>{timeAgo(latest.created_at)}</span>
        </div>
      </button>
      <Lightbox artifact={latest} open={open} onOpenChange={setOpen} />
    </>
  )
}

export function ScreenshotGallery({ artifacts }: { artifacts: Artifact[] }) {
  const shots = artifacts.filter((a) => a.mime.startsWith('image/'))
  const [current, setCurrent] = useState<Artifact | null>(null)
  if (!shots.length)
    return <div className="text-muted-foreground py-12 text-center text-sm">No screenshots in this run.</div>
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {shots.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => setCurrent(a)}
            className="hover:border-primary/40 overflow-hidden rounded-lg border text-left transition-colors"
          >
            <img src={artifactUrl(a.id)} alt={name(a)} className="aspect-video w-full object-cover object-top" loading="lazy" />
            <div className="text-muted-foreground truncate px-2 py-1.5 font-mono text-xs">{name(a)}</div>
          </button>
        ))}
      </div>
      {current && <Lightbox artifact={current} open onOpenChange={(o) => !o && setCurrent(null)} />}
    </>
  )
}

function Lightbox({ artifact, open, onOpenChange }: { artifact: Artifact; open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[95svh] gap-2 overflow-auto p-3 sm:max-w-6xl">
        <DialogTitle className="font-mono text-sm">{name(artifact)}</DialogTitle>
        <DialogDescription className="sr-only">Screenshot taken by the agent</DialogDescription>
        <img src={artifactUrl(artifact.id)} alt={name(artifact)} className="w-full rounded-md border" />
      </DialogContent>
    </Dialog>
  )
}

export function EvidenceThumbs({ ids }: { ids: string[] }) {
  if (!ids.length) return null
  return (
    <div className="flex gap-1.5">
      {ids.map((id) => (
        <a key={id} href={artifactUrl(id)} target="_blank" rel="noreferrer">
          <img src={artifactUrl(id)} alt="evidence" className="h-10 w-16 rounded border object-cover object-top" />
        </a>
      ))}
    </div>
  )
}
