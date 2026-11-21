import { createBrowserRouter } from 'react-router'

import { AppShell, type RouteHandle } from '@/components/layout/app-shell'
import { AgentDetailPage } from '@/pages/agents/agent-detail-page'
import { AgentsPage } from '@/pages/agents/agents-page'
import { DashboardPage } from '@/pages/dashboard'
import { LoginPage } from '@/pages/login'
import { BugsPage } from '@/pages/bugs/bugs-page'
import { OrgChartPage } from '@/pages/org/org-chart-page'
import { NotFoundPage } from '@/pages/placeholder-pages'
import { ApprovalsPage } from '@/pages/runs/approvals-page'
import { RunDetailPage } from '@/pages/runs/run-detail-page'
import { RunsPage } from '@/pages/runs/runs-page'
import { UsagePage } from '@/pages/runs/usage-page'
import { SecretsPage } from '@/pages/secrets/secrets-page'
import { TargetsPage } from '@/pages/targets/targets-page'
import { TaskDetailPage } from '@/pages/tasks/task-detail-page'
import { TasksPage } from '@/pages/tasks/tasks-page'

const h = (...crumbs: { label: string; to?: string }[]): RouteHandle => ({ crumbs })

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage />, handle: h({ label: 'Dashboard' }) },
      {
        path: 'tasks',
        handle: h({ label: 'Tasks', to: '/tasks' }),
        children: [
          { index: true, element: <TasksPage /> },
          { path: ':taskId', element: <TaskDetailPage />, handle: h({ label: 'Task' }) },
        ],
      },
      {
        path: 'agents',
        handle: h({ label: 'Agents', to: '/agents' }),
        children: [
          { index: true, element: <AgentsPage /> },
          { path: ':agentId', element: <AgentDetailPage />, handle: h({ label: 'Agent' }) },
        ],
      },
      { path: 'org', element: <OrgChartPage />, handle: h({ label: 'Organization' }) },
      { path: 'targets', element: <TargetsPage />, handle: h({ label: 'Target apps' }) },
      { path: 'secrets', element: <SecretsPage />, handle: h({ label: 'Secrets' }) },
      {
        path: 'runs',
        handle: h({ label: 'Runs', to: '/runs' }),
        children: [
          { index: true, element: <RunsPage /> },
          { path: ':runId', element: <RunDetailPage />, handle: h({ label: 'Run' }) },
        ],
      },
      { path: 'approvals', element: <ApprovalsPage />, handle: h({ label: 'Approvals' }) },
      { path: 'bugs', element: <BugsPage />, handle: h({ label: 'Bugs' }) },
      { path: 'usage', element: <UsagePage />, handle: h({ label: 'Usage & analytics' }) },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
