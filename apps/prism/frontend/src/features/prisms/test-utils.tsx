import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { FormDialogProvider } from "@/components/ui";
import { AppContext, type AppApi } from "@/lib/app-context";
import { fakeApp } from "@/test/render";
import { PrismsProvider } from "./PrismsProvider";
import type { Prism } from "./types";

export type Handler = (body: unknown, url: URL) => unknown;
export interface Call {
  method: string;
  path: string;
  body: unknown;
}

/** Install a fake `fetch`: routes are `[method, path-regex, handler]`; handlers return JSON or throw `{status, detail}`. */
export function fakeFetch(routes: ReadonlyArray<readonly [string, RegExp, Handler]>): { calls: Call[] } {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = new URL(String(input), "http://localhost");
      const method = (init.method || "GET").toUpperCase();
      const body = typeof init.body === "string" && init.body ? JSON.parse(init.body) : undefined;
      calls.push({ method, path: url.pathname + url.search, body });
      const route = routes.find(([m, pattern]) => m === method && pattern.test(url.pathname + url.search));
      if (!route) return new Response(JSON.stringify({ detail: `No fake for ${method} ${url.pathname}` }), { status: 404 });
      try {
        const result = route[2](body, url);
        return new Response(JSON.stringify(result ?? null), { status: 200, headers: { "Content-Type": "application/json" } });
      } catch (error) {
        const failure = error as { status?: number; detail?: string };
        return new Response(JSON.stringify({ detail: failure.detail ?? "boom" }), { status: failure.status ?? 500 });
      }
    }),
  );
  return { calls };
}

export function prismRow(overrides: Partial<Prism> = {}): Prism {
  return {
    id: "p1",
    code: "pAbc12",
    name: "Sales Prism",
    description: "Research prospects. Prepare recommendations.",
    state: "active",
    template_key: "blank",
    template_version: null,
    lifecycle_version: 1,
    capabilities: ["browser"],
    logins_policy: "never",
    job_role: "Analyst",
    department: "Sales",
    is_chief_of_staff: false,
    tools_allowed: 0,
    tools_ask_first: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    ...overrides,
  } as Prism;
}

export function renderPrisms(ui: ReactElement, app: Partial<AppApi> = {}): RenderResult & { app: AppApi } {
  const api = fakeApp(app);
  const result = render(
    <AppContext.Provider value={api}>
      <FormDialogProvider>
        <PrismsProvider>{ui}</PrismsProvider>
      </FormDialogProvider>
    </AppContext.Provider>,
  );
  return Object.assign(result, { app: api });
}
