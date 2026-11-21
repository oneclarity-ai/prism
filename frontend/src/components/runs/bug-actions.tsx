import { Mail, Send, Ticket } from 'lucide-react'
import { toast } from 'sonner'

import { InfoTip } from '@/components/common/info-tip'
import { Button } from '@/components/ui/button'

const ACTIONS = [
  { key: 'email', label: 'Email developer', icon: Mail, soon: 'Will email the bug with steps and screenshots to the developer who owns this area.' },
  { key: 'jira', label: 'Raise Jira ticket', icon: Ticket, soon: 'Will create a Jira issue in the project linked to this target app.' },
  { key: 'manager', label: 'Send to manager', icon: Send, soon: 'Will send the bug to the manager in the org chart above the QA seat for triage.' },
] as const

/** Follow-up actions on a bug. Buttons are in place; the integrations come later. */
export function BugActions({ title, size = 'sm' }: { title: string; size?: 'sm' | 'xs' }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {ACTIONS.map((a) => (
        <Button
          key={a.key}
          type="button"
          variant="outline"
          size={size}
          onClick={() => toast.info(`${a.label}: coming soon`, { description: `${a.soon} (Bug: ${title})` })}
        >
          <a.icon /> {a.label}
        </Button>
      ))}
      <InfoTip title="Bug actions">
        <p>These buttons will hand a confirmed bug to the right person or system:</p>
        <ul className="list-disc pl-4">
          <li>Email the developer</li>
          <li>Create a Jira ticket</li>
          <li>Send to your manager for triage</li>
        </ul>
        <p>They show a "coming soon" note for now; the integrations are next on the roadmap.</p>
      </InfoTip>
    </div>
  )
}
