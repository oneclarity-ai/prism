import type { Position } from '@/api/client'

export const LEVELS = [
  { value: 'ceo', label: 'CEO' },
  { value: 'executive', label: 'Executive' },
  { value: 'senior_manager', label: 'Senior manager' },
  { value: 'manager', label: 'Manager' },
  { value: 'member', label: 'Member' },
] as const

export const DEPARTMENTS = [
  'Leadership',
  'Technology',
  'Sales',
  'Marketing',
  'Customer Success',
  'Operations',
  'Finance',
  'People',
]

const DEPT_TONES: Record<string, { bar: string; chip: string; dot: string }> = {
  Leadership: { bar: 'bg-violet-500', chip: 'bg-violet-500/10 text-violet-700 dark:text-violet-300', dot: 'bg-violet-500' },
  Technology: { bar: 'bg-sky-500', chip: 'bg-sky-500/10 text-sky-700 dark:text-sky-300', dot: 'bg-sky-500' },
  Sales: { bar: 'bg-emerald-500', chip: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-500' },
  Marketing: { bar: 'bg-pink-500', chip: 'bg-pink-500/10 text-pink-700 dark:text-pink-300', dot: 'bg-pink-500' },
  'Customer Success': { bar: 'bg-amber-500', chip: 'bg-amber-500/10 text-amber-700 dark:text-amber-300', dot: 'bg-amber-500' },
  Operations: { bar: 'bg-slate-500', chip: 'bg-slate-500/10 text-slate-700 dark:text-slate-300', dot: 'bg-slate-500' },
  Finance: { bar: 'bg-teal-500', chip: 'bg-teal-500/10 text-teal-700 dark:text-teal-300', dot: 'bg-teal-500' },
  People: { bar: 'bg-orange-500', chip: 'bg-orange-500/10 text-orange-700 dark:text-orange-300', dot: 'bg-orange-500' },
}
const FALLBACK = { bar: 'bg-indigo-500', chip: 'bg-indigo-500/10 text-indigo-700 dark:text-indigo-300', dot: 'bg-indigo-500' }

export const deptTone = (d: string) => DEPT_TONES[d] ?? FALLBACK

export type TreeNode = Position & { children: TreeNode[] }

export function buildTree(positions: Position[]): TreeNode[] {
  const byId = new Map<string, TreeNode>(positions.map((p) => [p.id, { ...p, children: [] }]))
  const roots: TreeNode[] = []
  for (const node of byId.values()) {
    const parent = node.parent_id ? byId.get(node.parent_id) : undefined
    if (parent) parent.children.push(node)
    else roots.push(node)
  }
  const sort = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.created_at.localeCompare(b.created_at))
    nodes.forEach((n) => sort(n.children))
  }
  sort(roots)
  return roots
}

export function descendantIds(positions: Position[], id: string): Set<string> {
  const out = new Set<string>()
  const walk = (pid: string) => {
    for (const p of positions) if (p.parent_id === pid && !out.has(p.id)) (out.add(p.id), walk(p.id))
  }
  walk(id)
  return out
}

export function sortDepartments(depts: string[]): string[] {
  return [...new Set(depts)].sort((a, b) => (a === 'Leadership' ? -1 : b === 'Leadership' ? 1 : a.localeCompare(b)))
}
