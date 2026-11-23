import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { installDialogPolyfill } from "@/test/dialog";
import { ComputerButton, ComputerPanel } from "./Panel";
import { checkAvailability, focusRun, getState, initQa, notify, onPrism, resetComputers, setOpen } from "./store";
import { fakeHost, installFetch, json, makeRun, makeWorkRun, plainPrism, qaPrism, stubBlobUrls, type Handler } from "./testkit";
import type { QaRun } from "./types";

beforeAll(installDialogPolyfill);

let host = fakeHost();
let blobs = stubBlobUrls();

function setup(routes: Record<string, Handler> = {}, computers = false) {
  host = fakeHost();
  blobs = stubBlobUrls();
  return installFetch({
    "GET /api/v2/qa/status": () => ({ available: true, computers }),
    "GET /api/v2/prisms/p1/qa/runs": () => [],
    "GET /api/v2/prisms/p2/qa/runs": () => [],
    "GET /api/v2/qa/runs/run-1/stream": () => json({}, 404),
    ...routes,
  });
}
const panelEl = () => document.getElementById("qa-computer-panel") as HTMLElement;
const bodyEl = () => document.getElementById("qa-computer-body") as HTMLElement;
const seed = (run: QaRun) =>
  act(() => {
    getState().runs.set(run.id, run);
    notify();
  });
const mount = () =>
  render(
    <>
      <ComputerButton />
      <ComputerPanel />
    </>,
  );
const flush = () => act(async () => new Promise((resolve) => setTimeout(resolve, 0)));

beforeEach(() => {
  setup();
  initQa(host);
});
afterEach(() => {
  cleanup();
  resetComputers();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("panel and button markup", () => {
  it("renders the frozen drawer structure, closed by default", () => {
    mount();
    const aside = panelEl();
    expect(aside.tagName).toBe("ASIDE");
    expect(aside).toHaveClass("agent-drawer", "computer-panel");
    expect(aside).not.toHaveClass("open");
    expect(aside).toHaveAttribute("aria-label", "Prism's computer");
    expect(screen.getByRole("heading", { level: 3 })).toHaveAttribute("id", "qa-computer-title");
    expect(screen.getByRole("button", { name: "Close computer", hidden: true })).toHaveAttribute("id", "qa-computer-close");
    expect(bodyEl()).toHaveClass("computer-body");
    expect(bodyEl()).toBeEmptyDOMElement();
  });

  it("the toggle button is hidden for Prisms without a computer and mirrors open state", async () => {
    mount();
    const button = document.getElementById("agent-computer-button") as HTMLButtonElement;
    expect(button).toHaveAttribute("hidden");
    expect(button).toHaveAttribute("aria-controls", "qa-computer-panel");
    act(() => onPrism(plainPrism));
    expect(button).toHaveAttribute("hidden");
    act(() => onPrism(qaPrism));
    expect(button).not.toHaveAttribute("hidden");
    expect(button).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(button);
    expect(panelEl()).toHaveClass("open");
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveClass("active");
    expect(document.getElementById("qa-computer-title")).toHaveTextContent("Quinn's computer");
    await userEvent.click(button);
    expect(panelEl()).not.toHaveClass("open");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("the dot shows a running task and turns orange while it waits for the user", () => {
    mount();
    act(() => onPrism(qaPrism));
    const dot = document.getElementById("agent-computer-dot") as HTMLElement;
    expect(dot).toHaveAttribute("hidden");
    act(() => {
      getState().order = ["run-1"];
    });
    seed(makeRun({ state: "running", active: true }));
    expect(dot).not.toHaveAttribute("hidden");
    expect(dot).not.toHaveClass("waiting");
    seed(makeRun({ state: "waiting_approval", active: true }));
    expect(dot).toHaveClass("waiting");
  });

  it("closing from the X button closes; opening announces on the bus", async () => {
    mount();
    act(() => onPrism(qaPrism));
    act(() => setOpen(true));
    expect(panelEl()).toHaveClass("open");
    await userEvent.click(document.getElementById("qa-computer-close") as HTMLElement);
    expect(panelEl()).not.toHaveClass("open");
    expect(getState().open).toBe(false);
  });
});

describe("empty and offline states", () => {
  it("QA Prism without runs invites a test; computer Prism without runs sleeps", async () => {
    setup({}, true);
    await act(async () => void (await checkAvailability()));
    mount();
    act(() => onPrism(qaPrism));
    act(() => setOpen(true));
    expect(bodyEl()).toHaveTextContent(`Ask Quinn to test a website, for example "test example.com and check the contact form". You'll watch the work here.`);
    expect(screen.getByText("Quinn's screen")).toBeInTheDocument();
    act(() => onPrism(plainPrism));
    act(() => setOpen(true));
    await flush();
    expect(bodyEl()).toHaveTextContent(`Asleep. Riya's computer wakes up when you give it a task, for example "find five fintech companies in Bangalore and list their websites". You'll watch the work here.`);
    expect(bodyEl().querySelector(".qa-caption")).toHaveTextContent("Asleep");
  });

  it("shows the computer's offline reason", async () => {
    setup({
      "GET /api/v2/qa/status": () => ({ available: true, computers: true }),
      "GET /api/v2/prisms/p2/computer": () => ({ state: "unavailable", reason: "Computer service is down." }),
      "GET /api/v2/prisms/p2/logins": () => [],
    });
    await act(async () => void (await checkAvailability()));
    mount();
    act(() => onPrism(plainPrism));
    act(() => setOpen(true));
    expect(await screen.findByText("Computer service is down.")).toHaveClass("qa-error");
    expect(bodyEl().querySelector(".qa-caption")).toHaveTextContent("Offline");
  });

  it("saved logins can be removed; reset asks first and clears the list", async () => {
    const net = setup({
      "GET /api/v2/qa/status": () => ({ available: true, computers: true }),
      "GET /api/v2/prisms/p2/computer": () => ({ state: "asleep" }),
      "GET /api/v2/prisms/p2/logins": () => [
        { id: "l1", site: "https://linkedin.com", username: "bob", remember: true },
        { id: "l2", site: "https://x.com", username: "amy", remember: false },
      ],
      "DELETE /api/v2/prisms/p2/logins/l1": () => [{ id: "l2", site: "https://x.com", username: "amy", remember: false }],
      "POST /api/v2/prisms/p2/computer/reset": () => ({ state: "asleep" }),
    });
    await act(async () => void (await checkAvailability()));
    initQa(host);
    mount();
    act(() => onPrism(plainPrism));
    act(() => setOpen(true));
    expect(await screen.findByText("Saved logins (2)")).toBeInTheDocument();
    expect(screen.getByText("linkedin.com")).toBeInTheDocument();
    expect(bodyEl()).toHaveTextContent("amy · one task");
    await userEvent.click(within(bodyEl()).getAllByRole("button", { name: "Remove", hidden: true })[0] as HTMLElement);
    expect(await screen.findByText("Saved logins (1)")).toBeInTheDocument();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    const reset = screen.getByRole("button", { name: "Reset computer" });
    expect(reset).toHaveAttribute("title", "Forget every login and clear the browser");
    await userEvent.click(reset);
    expect(net.count("POST /api/v2/prisms/p2/computer/reset")).toBe(0);
    await userEvent.click(reset);
    expect(confirm).toHaveBeenLastCalledWith("This signs Riya out of every site and clears its browser. Continue?");
    expect(await screen.findByText("Saved logins (0)")).toBeInTheDocument();
    expect(screen.getByText("None. I'll ask you in the chat when a site needs one.")).toBeInTheDocument();
    expect(host.setStatus).toHaveBeenCalledWith("Riya's computer was reset.", false);
  });
});

describe("focusRun and the run view", () => {
  it("focusRun loads the run, opens the panel and shows progress, stop and the activity log", async () => {
    const net = setup({
      "GET /api/v2/qa/runs/run-1": () =>
        makeRun({
          state: "running",
          active: true,
          started_at: new Date(Date.now() - 65_000).toISOString(),
          turn: 3,
          max_turns: 60,
          cost_usd: 0.25,
          budget_usd: 1,
          cases: { total: 4, pass: 2, fail: 1, blocked: 1 },
          activity: "Clicking 'Send'",
          current_url: "https://example.com/contact",
          activity_log: [{ text: "Opened the page" }, { text: "Clicked send" }],
        }),
      "POST /api/v2/qa/runs/run-1/cancel": () => makeRun({ state: "cancelled", active: false }),
      "GET /api/v2/prisms/p1/computer/live": () => json({}, 404),
    });
    mount();
    act(() => onPrism(qaPrism));
    await flush();
    await act(async () => focusRun("run-1"));
    expect(panelEl()).toHaveClass("open");
    // one load by focusRun, one plain read by the followed run when its stream is unavailable
    expect(net.count("GET /api/v2/qa/runs/run-1")).toBeGreaterThanOrEqual(1);
    const body = bodyEl();
    expect(body.querySelector(".qa-address")).toHaveTextContent("https://example.com/contact");
    expect(body.querySelector(".qa-caption")).toHaveTextContent("Testing");
    expect(body.querySelector(".qa-live")).toHaveClass("on");
    expect(body.querySelector(".qa-now")).toHaveClass("live");
    expect(body.querySelector(".qa-now")).toHaveTextContent("Clicking 'Send'");
    expect(body).toHaveTextContent("4 checks · 2 passed · 1 failed · 1 couldn't check");
    expect(body.querySelector(".qa-progress .qa-muted:last-child")).toHaveTextContent("Step 3 of 60 · $0.25 of $1.00 · 1m 05s");
    expect(body.querySelectorAll(".qa-bar .qa-seg")).toHaveLength(3 + 1 - 1 + 0); // pass, fail, blocked (no rest)
    expect(body.querySelector(".qa-stream-status")).toHaveAttribute("role", "status");
    const log = body.querySelector("details.qa-log") as HTMLElement;
    expect(Array.from(log.querySelectorAll("p")).map((p) => p.textContent)).toEqual(["Clicked send", "Opened the page"]);
    await userEvent.click(within(body).getByRole("button", { name: "Stop the test" }));
    await waitFor(() => expect(net.count("POST /api/v2/qa/runs/run-1/cancel")).toBe(1));
    await waitFor(() => expect(body.querySelector(".qa-live")).not.toHaveClass("on"));
    expect(body.querySelector(".qa-muted")).toBeTruthy();
    expect(within(body).queryByRole("button", { name: "Stop the test" })).toBeNull();
  });

  it("work runs show the checklist, step counts and 'Waiting for you in the chat'", () => {
    mount();
    act(() => onPrism(qaPrism));
    act(() => {
      getState().order = ["work-1"];
      getState().focus = "work-1";
    });
    seed(
      makeWorkRun({
        state: "waiting_approval",
        active: true,
        turn: 2,
        max_turns: 40,
        checklist: [
          { title: "Search", status: "done" },
          { title: "Open site", status: "doing" },
          { title: "Skip me", status: "skipped" },
          { title: "List", status: "todo" },
        ],
      }),
    );
    act(() => setOpen(true));
    const body = bodyEl();
    expect(body.querySelector(".qa-now")).toHaveTextContent("Waiting for you in the chat");
    expect(body.querySelector(".qa-live")).toHaveClass("on", "waiting");
    expect(Array.from(body.querySelectorAll(".qa-step")).map((row) => `${row.className}:${row.textContent}`)).toEqual([
      "qa-step done:✓Search",
      "qa-step doing:●Open site",
      "qa-step skipped:–Skip me",
      "qa-step todo:○List",
    ]);
    expect(body).toHaveTextContent("2 of 4 steps done");
    expect(body).toHaveTextContent("Step 2 of up to 40");
    expect(within(body).getByRole("button", { name: "Stop" })).toBeInTheDocument();
    expect(body.querySelector(".qa-runs h4")).toHaveTextContent("Tasks");
  });

  it("starting runs and workspace warnings", () => {
    mount();
    act(() => onPrism(qaPrism));
    act(() => {
      getState().order = ["run-1"];
      getState().focus = "run-1";
    });
    seed(makeRun({ state: "starting", active: true }));
    act(() => setOpen(true));
    expect(bodyEl().querySelector(".qa-now")).toHaveTextContent("Connecting to my testing workspace…");
    seed(makeRun({ state: "starting", active: true, startup_warning: "The testing workspace is unavailable." }));
    expect(bodyEl().querySelector(".qa-caption")).toHaveTextContent("Waiting for workspace");
    expect(bodyEl().querySelector(".qa-now")).toHaveClass("qa-waiting");
    expect(bodyEl().querySelector(".qa-stream-status")).toHaveTextContent("Live view will connect when the testing workspace is available.");
    seed(makeRun({ state: "error", error: "Boom" }));
    expect(bodyEl().querySelector(".qa-error")).toHaveTextContent("Boom");
  });

  it("the run list switches focus and caps at eight", async () => {
    mount();
    act(() => onPrism(qaPrism));
    const runs = Array.from({ length: 10 }, (_, index) => makeRun({ id: `r${index}`, site: `site${index}.com`, state: "succeeded", cases: { total: 2, pass: 1 } }));
    act(() => setOpen(true));
    await flush(); // the run list answered (empty) before the test seeds its own
    act(() => {
      runs.forEach((run) => getState().runs.set(run.id, run));
      getState().order = runs.map((run) => run.id);
      getState().focus = "r0";
      notify();
    });
    const rows = bodyEl().querySelectorAll("button.qa-run");
    expect(rows).toHaveLength(8);
    expect(rows[0]).toHaveClass("current");
    expect(rows[0]).toHaveTextContent("site0.comFinished · 1/2");
    await userEvent.click(rows[3] as HTMLElement);
    expect(getState().focus).toBe("r3");
    expect(bodyEl().querySelectorAll("button.qa-run")[3]).toHaveClass("current");
    expect(bodyEl().querySelector(".qa-runs h4")).toHaveTextContent("Tests");
  });
});

describe("screen, frames and blob lifecycle", () => {
  it("fetches the saved frame, shows it, and revokes the old one 2s after a newer frame arrives", async () => {
    const net = setup({ "GET /api/v2/qa/runs/run-1/frame": () => new Response("jpg") });
    const timeouts = vi.spyOn(globalThis, "setTimeout");
    mount();
    act(() => onPrism(qaPrism));
    act(() => {
      getState().order = ["run-1"];
      getState().focus = "run-1";
    });
    seed(makeRun({ state: "succeeded", frame: 1 }));
    act(() => setOpen(true));
    await waitFor(() => expect(bodyEl().querySelector("img.qa-shot")).toHaveAttribute("src", "blob:fake-1"));
    expect(bodyEl().querySelector("img.qa-shot")).toHaveClass("show");
    expect(bodyEl()).toHaveTextContent("Last screen · task ended");
    expect(net.calls.some((call) => call.url === "/api/v2/qa/runs/run-1/frame?v=1")).toBe(true);
    seed(makeRun({ state: "succeeded", frame: 2 }));
    await waitFor(() => expect(bodyEl().querySelector("img.qa-shot")).toHaveAttribute("src", "blob:fake-2"));
    expect(net.calls.some((call) => call.url === "/api/v2/qa/runs/run-1/frame?v=2")).toBe(true);
    const revoke = timeouts.mock.calls.find(([, delay]) => delay === 2000);
    expect(revoke).toBeTruthy();
    expect(blobs.revoke).not.toHaveBeenCalled();
    (revoke?.[0] as () => void)();
    expect(blobs.revoke).toHaveBeenCalledWith("blob:fake-1");
  });

  it("enlarge opens a modal dialog with the screen and closes with the button", async () => {
    mount();
    act(() => onPrism(qaPrism));
    act(() => setOpen(true));
    await userEvent.click(screen.getByRole("button", { name: "Enlarge the computer screen" }));
    const dialog = document.getElementById("qa-enlarged") as HTMLDialogElement;
    expect(dialog).toHaveAttribute("open");
    expect(dialog).toHaveAttribute("aria-label", "Computer, enlarged");
    expect(within(dialog).getByText("Quinn's computer")).toBeInTheDocument();
    expect(dialog.querySelector(".qa-screen.large")).toBeTruthy();
    expect(dialog.querySelector(".qa-enlarge")).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(dialog).not.toHaveAttribute("open");
    expect(dialog).toBeEmptyDOMElement();
  });
});

describe("live stream and timers", () => {
  const jpeg = (text: string) => new TextEncoder().encode(`--f\r\nContent-Type: image/jpeg\r\nContent-Length: ${text.length}\r\n\r\n${text}\r\n`);

  function liveRoutes() {
    const signals: Array<AbortSignal | null | undefined> = [];
    let push: (chunk: Uint8Array) => void = () => {};
    const handler: Handler = ({ signal }) => {
      signals.push(signal);
      return new Response(new ReadableStream<Uint8Array>({ start: (controller) => (push = (chunk) => controller.enqueue(chunk)) }));
    };
    return { signals, handler, push: (chunk: Uint8Array) => push(chunk) };
  }

  beforeEach(() => {
    HTMLImageElement.prototype.decode = vi.fn(async () => {});
  });

  it("paints the newest live frame while a task runs and stops when the panel closes", async () => {
    const live = liveRoutes();
    setup({ "GET /api/v2/prisms/p1/computer/live": live.handler });
    mount();
    act(() => onPrism(qaPrism));
    act(() => {
      getState().order = ["run-1"];
      getState().focus = "run-1";
    });
    seed(makeRun({ state: "running", active: true }));
    act(() => setOpen(true));
    await waitFor(() => expect(live.signals).toHaveLength(1));
    expect(bodyEl().querySelector(".qa-stream-status")).toHaveTextContent("Connecting live view…");
    expect(bodyEl().querySelector("img.qa-shot")).not.toHaveClass("show");
    await act(async () => live.push(new Uint8Array([...jpeg("AA"), ...jpeg("BBB")])));
    await waitFor(() => expect(bodyEl().querySelector("img.qa-shot")).toHaveClass("show"));
    expect(bodyEl().querySelector("img.qa-shot")).toHaveAttribute("src", "blob:fake-1");
    expect(bodyEl().querySelector(".qa-stream-status")).toHaveTextContent("Live · continuous screen");
    await userEvent.click(document.getElementById("qa-computer-close") as HTMLElement);
    expect(live.signals[0]?.aborted).toBe(true);
    expect(live.signals).toHaveLength(1);
  });

  it("does not open a stream while the workspace is unavailable, and aborts on unmount and Prism change", async () => {
    const live = liveRoutes();
    setup({ "GET /api/v2/prisms/p1/computer/live": live.handler });
    const view = mount();
    act(() => onPrism(qaPrism));
    act(() => {
      getState().order = ["run-1"];
      getState().focus = "run-1";
    });
    seed(makeRun({ state: "starting", active: true, startup_warning: "down" }));
    act(() => setOpen(true));
    await flush();
    expect(live.signals).toHaveLength(0);
    seed(makeRun({ state: "running", active: true }));
    await waitFor(() => expect(live.signals).toHaveLength(1));
    act(() => onPrism(plainPrism));
    expect(live.signals[0]?.aborted).toBe(true);
    act(() => onPrism(qaPrism, true));
    seed(makeRun({ state: "running", active: true }));
    act(() => {
      getState().order = ["run-1"];
      getState().focus = "run-1";
      setOpen(true);
    });
    await waitFor(() => expect(live.signals).toHaveLength(2));
    view.unmount();
    expect(live.signals[1]?.aborted).toBe(true);
  });

  it("ticks the elapsed clock once a second only while the panel is open, and cleans the timer up", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    vi.setSystemTime(new Date("2026-01-01T00:01:00Z"));
    setup({ "GET /api/v2/prisms/p1/computer/live": () => json({}, 404) });
    const view = mount();
    act(() => onPrism(qaPrism));
    act(() => {
      getState().order = ["run-1"];
      getState().focus = "run-1";
    });
    seed(makeRun({ state: "running", active: true, started_at: "2026-01-01T00:00:55Z", turn: 1 }));
    expect(vi.getTimerCount()).toBe(0);
    act(() => setOpen(true));
    expect(vi.getTimerCount()).toBe(1);
    const clock = () => bodyEl().querySelector(".qa-elapsed")?.textContent;
    expect(clock()).toBe("5s");
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(clock()).toBe("8s");
    act(() => setOpen(false));
    expect(vi.getTimerCount()).toBe(0);
    act(() => setOpen(true));
    expect(vi.getTimerCount()).toBe(1);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
