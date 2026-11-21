// Fail-closed browser egress proxy. It resolves each destination itself and connects to that
// address, preventing DNS rebinding from reaching loopback, private, link-local or metadata IPs.
import dns from "node:dns/promises";
import http from "node:http";
import net from "node:net";
import { fileURLToPath } from "node:url";

const PORT = 8899;
const allowLocal = process.env.PRISM_ALLOW_LOCAL_SITES === "1";

function ipv4Number(address) {
  const parts = address.split(".").map(Number);
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) return null;
  return parts.reduce((value, part) => (value * 256 + part) >>> 0, 0);
}

function inV4(address, network, bits) {
  const value = ipv4Number(address);
  const base = ipv4Number(network);
  if (value === null || base === null) return false;
  const divisor = 2 ** (32 - bits);
  return Math.floor(value / divisor) === Math.floor(base / divisor);
}

export function isBlockedAddress(address) {
  if (allowLocal) return false;
  if (net.isIPv4(address)) {
    return [
      ["0.0.0.0", 8], ["10.0.0.0", 8], ["100.64.0.0", 10], ["127.0.0.0", 8],
      ["169.254.0.0", 16], ["172.16.0.0", 12], ["192.0.0.0", 24], ["192.0.2.0", 24],
      ["192.168.0.0", 16], ["198.18.0.0", 15], ["198.51.100.0", 24], ["203.0.113.0", 24],
      ["224.0.0.0", 4], ["240.0.0.0", 4],
    ].some(([network, bits]) => inV4(address, network, bits));
  }
  if (net.isIPv6(address)) {
    const normalized = address.toLowerCase();
    return normalized === "::" || normalized === "::1" || normalized.startsWith("fc") ||
      normalized.startsWith("fd") || /^fe[89ab]/.test(normalized) || normalized.startsWith("ff") ||
      normalized.startsWith("2001:db8:") || normalized.startsWith("::ffff:");
  }
  return true;
}

async function publicAddress(hostname) {
  const host = String(hostname || "").replace(/^\[|\]$/g, "").toLowerCase();
  if (!host || (!allowLocal && (host === "localhost" || host.endsWith(".localhost") || host.endsWith(".local")))) {
    throw new Error("Destination is blocked");
  }
  const rows = await dns.lookup(host, { all: true, verbatim: true });
  const row = rows.find(({ address }) => !isBlockedAddress(address));
  if (!row || rows.some(({ address }) => isBlockedAddress(address))) throw new Error("Destination is blocked");
  return row.address;
}

function reject(socketOrResponse) {
  if ("writeHead" in socketOrResponse) {
    if (socketOrResponse.destroyed) return;
    if (socketOrResponse.headersSent) return socketOrResponse.destroy();
    socketOrResponse.writeHead(403, { "content-type": "text/plain", connection: "close" });
    socketOrResponse.end("Destination blocked by Prism browser policy.");
  } else if (!socketOrResponse.destroyed) {
    socketOrResponse.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
  }
}

export const server = http.createServer(async (request, response) => {
  let upstream;
  request.on("error", () => { upstream?.destroy(); response.destroy(); });
  response.on("close", () => upstream?.destroy());
  try {
    const url = new URL(request.url);
    const address = await publicAddress(url.hostname);
    if (request.destroyed || response.destroyed) return;
    upstream = http.request({
      host: address, port: Number(url.port || 80), method: request.method, path: `${url.pathname}${url.search}`,
      headers: { ...request.headers, host: url.host },
    }, (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers);
      upstreamResponse.on("error", () => response.destroy());
      upstreamResponse.pipe(response);
    });
    upstream.on("error", () => reject(response));
    request.pipe(upstream);
  } catch {
    reject(response);
  }
});

server.on("connect", async (request, client, head) => {
  let upstream;
  client.on("error", () => upstream?.destroy());
  client.on("close", () => upstream?.destroy());
  try {
    const split = request.url.lastIndexOf(":");
    const hostname = split > -1 ? request.url.slice(0, split) : request.url;
    const port = split > -1 ? Number(request.url.slice(split + 1)) : 443;
    if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("Invalid port");
    const address = await publicAddress(hostname);
    if (client.destroyed) return;
    upstream = net.connect(port, address, () => {
      client.write("HTTP/1.1 200 Connection Established\r\n\r\n");
      if (head.length) upstream.write(head);
      upstream.pipe(client);
      client.pipe(upstream);
    });
    upstream.on("error", () => client.destroy());
    upstream.on("close", () => client.destroy());
  } catch {
    if (!client.destroyed) reject(client);
  }
});

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  server.listen(PORT, "127.0.0.1");
}
