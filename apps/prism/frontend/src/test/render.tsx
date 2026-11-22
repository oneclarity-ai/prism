import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { AppContext, type AppApi } from "@/lib/app-context";
import type { PrismLike } from "@/lib/events";
import { PrismsContext, type PrismsApi } from "@/features/prisms/PrismsContext";

export function fakeApp(overrides: Partial<AppApi> = {}): AppApi {
  return {
    activeTab: "prisms",
    setActiveTab: vi.fn(),
    sidebarSection: "chat",
    setSidebarSection: vi.fn(),
    modes: { v21: false, v22: true, v24: true, singleExecutive: false },
    setStatus: vi.fn(),
    askDialog: vi.fn(async () => true as const),
    settings: { isOpen: false, section: "preferences", open: vi.fn(), close: vi.fn(), setSection: vi.fn() },
    refreshKey: 0,
    refresh: vi.fn(),
    providerStatus: null,
    microsoftConnected: null,
    microsoft: null,
    narrow: false,
    openSidebar: vi.fn(),
    closeSidebarIfNarrow: vi.fn(),
    openSearch: vi.fn(),
    go: vi.fn(),
    refreshStatus: vi.fn(async () => {}),
    setPageHeading: vi.fn(),
    pageActionsRoot: null,
    routes: { prism: vi.fn(), workspace: vi.fn(), requestedPrism: null, requestedLegacy: false },
    ...overrides,
  };
}

interface Options {
  app?: Partial<AppApi>;
  prisms?: Partial<PrismsApi> & { list?: PrismLike[] };
}

export function renderWithApp(ui: ReactElement, { app, prisms }: Options = {}): RenderResult & { app: AppApi } {
  const api = fakeApp(app);
  const prismsValue: PrismsApi = {
    prisms: prisms?.list ?? prisms?.prisms ?? [],
    loading: false,
    selectedId: null,
    reload: vi.fn(async () => {}),
    ...prisms,
  };
  const result = render(
    <AppContext.Provider value={api}>
      <PrismsContext.Provider value={prismsValue}>{ui}</PrismsContext.Provider>
    </AppContext.Provider>,
  );
  return Object.assign(result, { app: api });
}
