import createClient from 'openapi-fetch'

import type { components, paths } from './schema'

export type Schemas = components['schemas']
export type User = Schemas['UserRead']
export type Agent = Schemas['AgentRead']
export type AgentCreate = Schemas['AgentCreate']
export type AgentUpdate = Schemas['AgentUpdate']
export type ToolGrant = Schemas['ToolGrant']
export type Target = Schemas['TargetRead']
export type TargetCreate = Schemas['TargetCreate']
export type TargetUpdate = Schemas['TargetUpdate']
export type Secret = Schemas['SecretRead']
export type SecretCreate = Schemas['SecretCreate']
export type Task = Schemas['TaskRead']
export type TaskCreate = Schemas['TaskCreate']
export type TaskUpdate = Schemas['TaskUpdate']
export type TaskStatus = Schemas['TaskStatus']
export type Environment = Schemas['Environment']
export type Run = Schemas['RunRead']
export type RunStatus = Schemas['RunStatus']
export type RunEvent = Schemas['RunEventRead']
export type TestCase = Schemas['TestCaseRead']
export type Bug = Schemas['BugRead']
export type Artifact = Schemas['ArtifactRead']
export type Approval = Schemas['ApprovalRead']
export type UsageRow = Schemas['UsageRow']
export type RuntimeStatus = Schemas['RuntimeStatus']
export type Position = Schemas['PositionRead']
export type PositionCreate = Schemas['PositionCreate']
export type PositionUpdate = Schemas['PositionUpdate']
export type AgentRole = Schemas['AgentRoleRead']
export type Analytics = Schemas['AnalyticsRead']
export type BugItem = Schemas['BugListItem']
export type RunStart = Schemas['RunStart']
export type SubAgent = Schemas['SubAgentRead']

export const api = createClient<paths>({ baseUrl: '', credentials: 'include' })

/** Error thrown for any non-2xx response, carrying the backend's {error: {code, message}} body. */
export class ApiError extends Error {
  status: number
  code: string
  details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

type ErrorBody = { error?: { code?: string; message?: string; details?: { loc: (string | number)[]; msg: string }[] } }

/** Unwrap an openapi-fetch result: return data or throw ApiError with a readable message. */
export async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise
  if (response.ok) return data as T
  const body = (error ?? {}) as ErrorBody
  let message = body.error?.message ?? response.statusText ?? 'Request failed'
  const details = body.error?.details
  if (Array.isArray(details) && details.length) {
    message = details.map((d) => `${d.loc.filter((l) => l !== 'body').join('.')}: ${d.msg}`).join(' · ')
  }
  throw new ApiError(response.status, body.error?.code ?? 'error', message, details)
}
