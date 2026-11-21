import { Navigate, Outlet, useLocation, useMatches } from 'react-router'

import { useMe } from '@/api/hooks'
import { ThemeToggle } from '@/components/common/theme-toggle'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { Spinner } from '@/components/ui/spinner'
import { Link } from 'react-router'
import { Fragment } from 'react'

import { AppSidebar } from './app-sidebar'

type Crumb = { label: string; to?: string }
export type RouteHandle = { crumbs?: Crumb[] }

function Crumbs() {
  const matches = useMatches()
  const crumbs = matches.flatMap((m) => (m.handle as RouteHandle | undefined)?.crumbs ?? [])
  if (!crumbs.length) return null
  return (
    <Breadcrumb>
      <BreadcrumbList>
        {crumbs.map((c, i) => (
          <Fragment key={`${c.label}-${i}`}>
            {i > 0 && <BreadcrumbSeparator />}
            <BreadcrumbItem>
              {c.to && i < crumbs.length - 1 ? (
                <BreadcrumbLink asChild>
                  <Link to={c.to}>{c.label}</Link>
                </BreadcrumbLink>
              ) : (
                <BreadcrumbPage>{c.label}</BreadcrumbPage>
              )}
            </BreadcrumbItem>
          </Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

export function AppShell() {
  const me = useMe()
  const location = useLocation()

  if (me.isPending) {
    return (
      <div className="flex h-svh items-center justify-center">
        <Spinner className="size-6" />
      </div>
    )
  }
  if (me.isError) return <Navigate to="/login" replace state={{ from: location.pathname }} />

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <header className="bg-background/80 sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 rounded-t-xl border-b px-4 backdrop-blur">
          <SidebarTrigger className="-ml-1" />
          <Crumbs />
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl min-w-0 flex-1 space-y-6 p-4 md:p-8">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
