# OneClarity console (frontend)

React + TypeScript web console for the OneClarity agent platform. Full description, screen list and screenshots: [`../docs/16-console-ui.md`](../docs/16-console-ui.md).

## Run

```bash
npm install
npm run dev            # http://localhost:5173 (proxies /api to http://localhost:8080)
```

The backend must be running (`cd ../backend && uv run uvicorn app.main:app --reload`).

## Scripts

| Script | What it does |
| --- | --- |
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Type check and production build to `dist/` |
| `npm run typecheck` | Type check only |
| `npm run lint` | oxlint |
| `npm run gen:api` | Regenerate `src/api/schema.d.ts` from the running backend's OpenAPI |

## Adding a UI component

```bash
npx shadcn@latest add <component>
```

Components land in `src/components/ui/` and can be edited freely.
