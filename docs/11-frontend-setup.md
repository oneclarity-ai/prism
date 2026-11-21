# 11 — Frontend Setup (React + TypeScript)

## Stack

| Concern | Choice |
| --- | --- |
| Build | Vite 8, React 19, TypeScript 6 (strict) |
| Routing | React Router 7 |
| Server state | TanStack Query |
| API types | `openapi-typescript` from `http://localhost:8000/openapi.json` + `openapi-fetch` client |
| Live updates | native WebSocket wrapper with reconnect and topic subscribe |
| UI kit | Tailwind CSS v4 + shadcn/ui (Radix, Nova preset) + lucide-react icons; Geist + JetBrains Mono fonts |
| Forms | react-hook-form + zod |
| Markdown | react-markdown + remark-gfm (reports) |
| Tests | Vitest + React Testing Library; Playwright for UI e2e |

## Steps

> Built 2026-10-13 with **npm** (pnpm was not installed). See [16-console-ui.md](16-console-ui.md) for what exists.

1. `npm create vite@latest frontend -- --template react-ts`; enable `strict` in `tsconfig`.
2. Add Tailwind and run `shadcn` init; add base components (button, card, table, badge, dialog, tabs, toast, form, input, textarea, select).
3. `npm install @tanstack/react-query react-router-dom openapi-fetch react-hook-form zod @hookform/resolvers react-markdown remark-gfm lucide-react`.
4. `npm install -D openapi-typescript vitest @testing-library/react`.
5. Script `npm run gen:api` → `openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts`. Re-run after backend changes.
6. `src/api/client.ts`: typed client with `credentials: "include"` for the session cookie.
7. `src/lib/ws.ts`: connect, subscribe(topic, handler), auto-reconnect with backoff, gap fill via `GET /runs/{id}/events?after_seq=`.
8. Vite proxy `/api` → `http://localhost:8000` (no CORS issues in dev).
9. App shell: sidebar (Tasks, Runs, Approvals, Targets, Agents, Usage), top bar with user menu, pending-approvals badge.
10. Auth guard: redirect to `/login` when `GET /auth/me` returns 401.

## Done when

- Login works against the backend.
- `pnpm gen:api` produces types and the app compiles with no `any` in API calls.
