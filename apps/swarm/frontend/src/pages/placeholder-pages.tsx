import { ArrowLeft, Compass, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router'

import { PageHeader } from '@/components/common/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

export function ComingSoonPage({
  icon,
  title,
  description,
  milestone,
  bullets,
}: {
  icon: LucideIcon
  title: string
  description: string
  milestone: string
  bullets: string[]
}) {
  return (
    <>
      <PageHeader icon={icon} title={title} description={description} actions={<Badge variant="outline">{milestone}</Badge>} />
      <Card className="bg-grid relative overflow-hidden">
        <div className="from-background/30 to-background absolute inset-0 bg-gradient-to-b" />
        <CardContent className="relative flex flex-col items-center gap-6 py-16 text-center">
          <div className="from-primary/20 to-primary/5 text-primary flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br">
            {(() => {
              const Icon = icon
              return <Icon className="size-8" />
            })()}
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-semibold">Coming in {milestone.toLowerCase()}</h2>
            <p className="text-muted-foreground max-w-md text-sm">This screen is planned. Here is what it will do:</p>
          </div>
          <ul className="grid max-w-xl gap-2 text-left text-sm sm:grid-cols-2">
            {bullets.map((b) => (
              <li key={b} className="bg-card rounded-lg border px-3 py-2">
                {b}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </>
  )
}

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60svh] flex-col items-center justify-center gap-4 text-center">
      <Compass className="text-muted-foreground size-12" />
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-muted-foreground text-sm">The page you are looking for does not exist.</p>
      <Button variant="outline" asChild>
        <Link to="/">
          <ArrowLeft /> Back to dashboard
        </Link>
      </Button>
    </div>
  )
}
