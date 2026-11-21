import { Eye, PenLine, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { useGenerateDescription } from '@/api/hooks'
import { Markdown } from '@/components/common/markdown'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

/**
 * "What does this agent do?" editor with a Generate-with-AI button. The AI drafts a full job
 * description (mission, responsibilities, KPIs, boundaries…) from the name and role; the user edits it.
 */
export function JobDescriptionField({
  id,
  value,
  onChange,
  name,
  role,
  department,
  rows = 10,
}: {
  id: string
  value: string
  onChange: (next: string) => void
  name: string
  role: string
  department?: string
  rows?: number
}) {
  const generate = useGenerateDescription()
  const [preview, setPreview] = useState(false)
  const ready = name.trim().length > 0 && role.trim().length > 0

  function run() {
    generate.mutate(
      { name, role, department: department ?? '', notes: value },
      {
        onSuccess: (r) => {
          onChange(r.description)
          setPreview(true)
          toast.success('Job description drafted', {
            description: `Review and edit it before saving. Cost about $${r.cost_usd.toFixed(3)}.`,
          })
        },
      },
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          onClick={run}
          disabled={!ready || generate.isPending}
          className="bg-gradient-to-r from-indigo-500 to-violet-500 text-white hover:opacity-90"
          title={ready ? undefined : 'Fill in name and role first'}
        >
          {generate.isPending ? <Spinner /> : <Sparkles />}
          {value.trim() ? 'Regenerate with AI' : 'Generate with AI'}
        </Button>
        <span className="text-muted-foreground text-xs">
          {ready
            ? 'Uses the name, role and anything you already wrote below.'
            : 'Fill in name and role first.'}
        </span>
        <div className="ml-auto flex rounded-md border p-0.5">
          {(
            [
              [false, PenLine, 'Write'],
              [true, Eye, 'Preview'],
            ] as const
          ).map(([on, Icon, label]) => (
            <button
              key={label}
              type="button"
              onClick={() => setPreview(on)}
              className={cn(
                'flex items-center gap-1 rounded px-2 py-0.5 text-xs',
                preview === on ? 'bg-muted font-medium' : 'text-muted-foreground',
              )}
            >
              <Icon className="size-3" /> {label}
            </button>
          ))}
        </div>
      </div>
      {generate.isPending ? (
        <div className="text-muted-foreground flex items-center justify-center gap-2 rounded-md border border-dashed py-16 text-sm">
          <Spinner /> Writing a job description like you would for a new hire…
        </div>
      ) : preview ? (
        <div className="max-h-96 overflow-y-auto rounded-md border p-4 text-sm">
          {value.trim() ? <Markdown source={value} /> : <span className="text-muted-foreground">Nothing written yet.</span>}
        </div>
      ) : (
        <Textarea
          id={id}
          rows={rows}
          className="font-mono text-xs leading-relaxed"
          placeholder="Researches leads and drafts personalised outreach. Or press Generate with AI."
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  )
}
