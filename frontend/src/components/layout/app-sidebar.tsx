import {
  Bot,
  Bug,
  ChevronsUpDown,
  ClipboardCheck,
  Globe,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Network,
  PlayCircle,
  ShieldCheck,
  Wallet,
} from 'lucide-react'
import { Link, NavLink, useLocation, useNavigate, useSearchParams } from 'react-router'

import { useApprovals, useLogout, useMe, usePositions, useRuns, useTasks } from '@/api/hooks'
import { Logo } from '@/components/common/logo'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { initials } from '@/lib/format'
import { deptTone, sortDepartments } from '@/lib/org'

const WORK = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/tasks', label: 'Tasks', icon: ListChecks },
  { to: '/runs', label: 'Runs', icon: PlayCircle },
  { to: '/approvals', label: 'Approvals', icon: ShieldCheck },
  { to: '/bugs', label: 'Bugs', icon: Bug },
]
const SETUP = [
  { to: '/agents', label: 'Agents', icon: Bot },
  { to: '/targets', label: 'Target apps', icon: Globe },
  { to: '/secrets', label: 'Secrets', icon: KeyRound },
  { to: '/usage', label: 'Usage & analytics', icon: Wallet },
]


export function AppSidebar() {
  const { pathname } = useLocation()
  const { data: me } = useMe()
  const { data: openTasks } = useTasks({ status: 'todo' })
  const { data: positions } = usePositions()
  const [search] = useSearchParams()
  const deptParam = search.get('dept')
  const departments = sortDepartments((positions ?? []).map((p) => p.department))
  const { data: pending } = useApprovals('pending')
  const { data: runs } = useRuns({}, true)
  const liveRuns = (runs ?? []).filter((r) => r.status === 'running' || r.status === 'queued').length
  const logout = useLogout()
  const navigate = useNavigate()

  const isActive = (to: string, end?: boolean) => (end ? pathname === to : pathname.startsWith(to))

  return (
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <NavLink to="/">
                <Logo />
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Organization</SidebarGroupLabel>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild isActive={pathname === '/org' && !deptParam} tooltip="Org chart">
                <NavLink to="/org">
                  <Network />
                  <span>Org chart</span>
                </NavLink>
              </SidebarMenuButton>
              <SidebarMenuBadge>{positions?.length || ''}</SidebarMenuBadge>
              {departments.length > 0 && (
                <SidebarMenuSub>
                  {departments.map((d) => (
                    <SidebarMenuSubItem key={d}>
                      <SidebarMenuSubButton asChild isActive={pathname === '/org' && deptParam === d}>
                        <Link to={`/org?dept=${encodeURIComponent(d)}`}>
                          <span className={`size-2 shrink-0 rounded-full ${deptTone(d).dot}`} />
                          <span>{d}</span>
                        </Link>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  ))}
                </SidebarMenuSub>
              )}
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Work</SidebarGroupLabel>
          <SidebarMenu>
            {WORK.map((item) => (
              <SidebarMenuItem key={item.to}>
                <SidebarMenuButton asChild isActive={isActive(item.to, item.end)} tooltip={item.label}>
                  <NavLink to={item.to} end={item.end}>
                    <item.icon />
                    <span>{item.label}</span>
                  </NavLink>
                </SidebarMenuButton>
                {item.to === '/tasks' && !!openTasks?.length && (
                  <SidebarMenuBadge>{openTasks.length}</SidebarMenuBadge>
                )}
                {item.to === '/runs' && !!liveRuns && (
                  <SidebarMenuBadge>
                    <span className="mr-1 size-1.5 animate-pulse rounded-full bg-sky-500" />
                    {liveRuns}
                  </SidebarMenuBadge>
                )}
                {item.to === '/approvals' && !!pending?.length && (
                  <SidebarMenuBadge>
                    <Badge className="h-5 border-0 bg-amber-500 px-1.5 text-white">{pending.length}</Badge>
                  </SidebarMenuBadge>
                )}
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Setup</SidebarGroupLabel>
          <SidebarMenu>
            {SETUP.map((item) => (
              <SidebarMenuItem key={item.to}>
                <SidebarMenuButton asChild isActive={isActive(item.to)} tooltip={item.label}>
                  <NavLink to={item.to}>
                    <item.icon />
                    <span>{item.label}</span>
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>

      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton size="lg" className="data-[state=open]:bg-sidebar-accent">
                  <Avatar className="size-8 rounded-lg">
                    <AvatarFallback className="bg-primary/15 text-primary rounded-lg text-xs font-semibold">
                      {initials(me?.name || me?.email || '?')}
                    </AvatarFallback>
                  </Avatar>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-medium">{me?.name || 'User'}</span>
                    <span className="text-muted-foreground truncate text-xs">{me?.email}</span>
                  </div>
                  <ChevronsUpDown className="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="top" align="start" className="w-56">
                <DropdownMenuLabel className="flex items-center gap-2">
                  <ClipboardCheck className="text-primary size-4" />
                  <span className="capitalize">{me?.role}</span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  variant="destructive"
                  onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/login') })}
                >
                  <LogOut /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
