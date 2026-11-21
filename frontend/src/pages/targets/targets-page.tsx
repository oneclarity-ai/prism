import { ExternalLink, FolderGit2, Globe, ListPlus, Lock, LockOpen, MoreHorizontal, Pencil, Plus, Trash2 } from 'lucide-react'

import { useDeleteTarget, useTargets, useTasks } from '@/api/hooks'
import { EnvironmentBadge } from '@/components/common/badges'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/common/page-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { hostOf, timeAgo } from '@/lib/format'
import { TaskDialog } from '../tasks/task-dialog'
import { TargetSheet } from './target-sheet'

export function TargetsPage() {
  const targets = useTargets()
  const tasks = useTasks()
  const remove = useDeleteTarget()

  return (
    <>
      <PageHeader
        icon={Globe}
        title="Target apps"
        info={
          <>
            <p>A target app is a website the QA agent tests: base URL, environment, optional test login and notes.</p>
            <p>The agent's browser may only load the base URL's domain plus the <b>extra allowed domains</b> you list (CDN, login provider, API).</p>
            <p>Prefer staging. On production, write strict rules in Notes (e.g. never submit forms with real data).</p>
          </>
        }
        description="Web apps the QA agent tests. Test logins are stored encrypted."
        actions={
          <TargetSheet
            trigger={
              <Button>
                <Plus /> Add target
              </Button>
            }
          />
        }
      />

      {targets.isPending ? (
        <Skeleton className="h-64" />
      ) : !targets.data?.length ? (
        <EmptyState
          icon={Globe}
          title="No target apps yet"
          description="Add the URL of the app you want tested, ideally a staging environment with a test account."
          action={
            <TargetSheet
              trigger={
                <Button>
                  <Plus /> Add your first app
                </Button>
              }
            />
          }
        />
      ) : (
        <Card className="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">App</TableHead>
                <TableHead>Environment</TableHead>
                <TableHead>Login</TableHead>
                <TableHead>Tasks</TableHead>
                <TableHead>Added</TableHead>
                <TableHead className="w-12 pr-4" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {targets.data.map((t) => {
                const taskCount = tasks.data?.filter((x) => x.target_app_id === t.id).length ?? 0
                return (
                  <TableRow key={t.id}>
                    <TableCell className="pl-4">
                      <div className="flex items-center gap-3">
                        <div className="bg-primary/10 text-primary flex size-9 items-center justify-center rounded-lg">
                          <Globe className="size-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="truncate font-medium">{t.name}</div>
                          <a
                            href={t.base_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-muted-foreground inline-flex items-center gap-1 text-xs hover:underline"
                          >
                            {hostOf(t.base_url)} <ExternalLink className="size-3" />
                          </a>
                        </div>
                        {t.repo_url && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <a href={t.repo_url} target="_blank" rel="noreferrer" className="text-muted-foreground">
                                <FolderGit2 className="size-4" />
                              </a>
                            </TooltipTrigger>
                            <TooltipContent>{t.repo_url}</TooltipContent>
                          </Tooltip>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <EnvironmentBadge env={t.environment} />
                    </TableCell>
                    <TableCell>
                      {t.has_test_login ? (
                        <span className="inline-flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
                          <Lock className="size-3.5" /> Stored
                        </span>
                      ) : (
                        <span className="text-muted-foreground inline-flex items-center gap-1.5 text-sm">
                          <LockOpen className="size-3.5" /> None
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="tabular-nums">{taskCount}</TableCell>
                    <TableCell className="text-muted-foreground text-sm">{timeAgo(t.created_at)}</TableCell>
                    <TableCell className="pr-4">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon-sm" aria-label="Actions">
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-44">
                          <TargetSheet
                            target={t}
                            trigger={
                              <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                                <Pencil /> Edit
                              </DropdownMenuItem>
                            }
                          />
                          <TaskDialog
                            defaultTargetId={t.id}
                            trigger={
                              <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                                <ListPlus /> New task
                              </DropdownMenuItem>
                            }
                          />
                          <DropdownMenuSeparator />
                          <ConfirmDialog
                            title={`Delete ${t.name}?`}
                            description="Its stored test login is deleted too. Tasks keep their history but lose the link to this app."
                            onConfirm={() => remove.mutate(t.id)}
                            trigger={
                              <DropdownMenuItem variant="destructive" onSelect={(e) => e.preventDefault()}>
                                <Trash2 /> Delete
                              </DropdownMenuItem>
                            }
                          />
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Card>
      )}
    </>
  )
}
