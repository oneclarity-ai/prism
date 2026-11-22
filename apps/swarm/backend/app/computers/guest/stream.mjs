// Live view of a Prism's browser: Chrome DevTools screencast -> multipart JPEG over HTTP.
// Each frame is "--frame", headers with Content-Length, the JPEG bytes. Also draws a cursor on the page
// (the agent drives Chromium over DevTools, so no real pointer exists) and a ripple on every click.
import http from "node:http";

const CDP = "http://127.0.0.1:9222";
const PORT = Number(process.env.STREAM_PORT || 8932);
const clients = new Set();
let last = null;

const OVERLAY = `(() => {
  if (window.__prismCursor) return;
  window.__prismCursor = true;
  let host, dot, shown = false;
  const mount = () => {
    if (host || !document.documentElement) return;
    host = document.createElement("div");
    host.style.cssText = "position:fixed;inset:0;z-index:2147483647;pointer-events:none;";
    const root = host.attachShadow({ mode: "closed" });
    root.innerHTML = '<style>.c{position:fixed;left:0;top:0;width:22px;height:22px;transition:transform .18s ease-out,opacity .2s;opacity:0;will-change:transform}.c svg{filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))}.r{position:fixed;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;border:3px solid #2563eb;animation:p .5s ease-out forwards}@keyframes p{from{transform:scale(.3);opacity:1}to{transform:scale(1.3);opacity:0}}</style><div class="c"><svg viewBox="0 0 24 24" width="22" height="22"><path d="M4 2l16 9-7 2-3 7z" fill="#111" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg></div>';
    dot = root.querySelector(".c");
    host.root = root;
    document.documentElement.appendChild(host);
  };
  const move = (e) => { mount(); if (!dot) return; shown = true; dot.style.opacity = "1"; dot.style.transform = "translate(" + e.clientX + "px," + e.clientY + "px)"; };
  window.addEventListener("mousemove", move, true);
  window.addEventListener("mousedown", (e) => { move(e); const r = document.createElement("div"); r.className = "r"; r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px"; host.root.appendChild(r); setTimeout(() => r.remove(), 600); }, true);
  document.addEventListener("DOMContentLoaded", mount);
})();`;

function send(buffer) {
  const head = Buffer.from(`--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${buffer.length}\r\n\r\n`);
  for (const res of clients) {
    if (res.writableLength > 4_000_000) continue; // a slow viewer skips frames instead of lagging behind
    res.write(head);
    res.write(buffer);
    res.write("\r\n");
  }
}

// At most ~15 frames a second; a frame dropped for that is replaced by the newest one a moment later.
const MIN_GAP_MS = 66;
let lastSent = 0;
let timer = null;
function push() {
  const wait = lastSent + MIN_GAP_MS - Date.now();
  if (wait <= 0) {
    lastSent = Date.now();
    if (last) send(last);
  } else if (!timer) {
    timer = setTimeout(() => { timer = null; push(); }, wait);
  }
}

async function run() {
  const version = await (await fetch(`${CDP}/json/version`)).json();
  const ws = new WebSocket(version.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  let activeSession = null;
  let capturing = false;
  const call = (method, params = {}, sessionId) =>
    new Promise((resolve) => {
      const n = ++id;
      const timeout = setTimeout(() => { pending.delete(n); resolve({}); }, 3000);
      pending.set(n, (result) => { clearTimeout(timeout); resolve(result); });
      ws.send(JSON.stringify({ id: n, method, params, sessionId }));
    });
  const sessions = new Map(); // sessionId -> targetId

  async function attach(targetId) {
    const { result } = await call("Target.attachToTarget", { targetId, flatten: true });
    if (!result?.sessionId) return;
    const sessionId = result.sessionId;
    sessions.set(sessionId, targetId);
    activeSession = sessionId;
    await call("Page.enable", {}, sessionId);
    await call("Page.addScriptToEvaluateOnNewDocument", { source: OVERLAY }, sessionId);
    await call("Runtime.evaluate", { expression: OVERLAY }, sessionId);
    await call("Page.startScreencast", { format: "jpeg", quality: 60, maxWidth: 1280, maxHeight: 800, everyNthFrame: 1 }, sessionId);
  }

  ws.addEventListener("message", async (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
      return;
    }
    if (message.method === "Target.targetCreated" && message.params.targetInfo.type === "page") {
      attach(message.params.targetInfo.targetId).catch(() => {});
    } else if (message.method === "Target.detachedFromTarget") {
      sessions.delete(message.params.sessionId);
      if (activeSession === message.params.sessionId) activeSession = [...sessions.keys()].at(-1) || null;
    } else if (message.method === "Page.frameNavigated" && !message.params.frame.parentId) {
      activeSession = message.sessionId;
    } else if (message.method === "Page.screencastVisibilityChanged" && message.params.visible) {
      activeSession = message.sessionId;
    } else if (message.method === "Page.screencastFrame") {
      const { data, sessionId: ack } = message.params;
      call("Page.screencastFrameAck", { sessionId: ack }, message.sessionId);
      if (message.sessionId !== activeSession) return;
      last = Buffer.from(data, "base64");
      push();
    }
  });

  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve);
    ws.addEventListener("error", reject);
  });
  await call("Target.setDiscoverTargets", { discover: true });
  // Keep fresh frames flowing even when Chromium stops emitting screencast events after navigation.
  // Capture only while somebody watches, with one in-flight capture and no frame backlog.
  const capture = setInterval(async () => {
    if (!clients.size || capturing || !activeSession || ws.readyState !== WebSocket.OPEN) return;
    capturing = true;
    const session = activeSession;
    try {
      const { result } = await call("Page.captureScreenshot", { format: "jpeg", quality: 60 }, session);
      if (session === activeSession && result?.data) {
        last = Buffer.from(result.data, "base64");
        push();
      }
    } catch { /* a tab closed or Chromium is reconnecting; retry on the next tick */ }
    finally { capturing = false; }
  }, 125);
  const closed = new Promise((resolve) => ws.addEventListener("close", resolve));
  try { await closed; } finally {
    clearInterval(capture);
    for (const resolve of pending.values()) resolve({});
    pending.clear();
    last = null;
  }
}

http
  .createServer((req, res) => {
    if (req.url === "/healthz") return res.end("ok");
    if (req.url !== "/stream") { res.statusCode = 404; return res.end(); }
    res.writeHead(200, { "Content-Type": "multipart/x-mixed-replace; boundary=frame", "Cache-Control": "no-store", Connection: "keep-alive" });
    clients.add(res);
    if (last) send(last); // a new viewer sees the current screen at once
    req.on("close", () => clients.delete(res));
  })
  .listen(PORT, "0.0.0.0");

// Keeps a still page visible: repeat the last frame every couple of seconds.
setInterval(() => { if (last && clients.size) send(last); }, 2000);

for (;;) {
  try { await run(); } catch { /* the browser is still starting or restarted */ }
  await new Promise((resolve) => setTimeout(resolve, 1000));
}
