#!/bin/sh
# Runs inside a Prism's computer: one Chromium (so the stream and the agent see the same page),
# the live-view streamer, and the Playwright MCP server attached to that Chromium.
CHROME=$(ls -d /ms-playwright/chromium-*/chrome-linux*/chrome | head -1)
rm -f /profile/SingletonLock /profile/SingletonCookie /profile/SingletonSocket
node /opt/guest/network-proxy.mjs &
"$CHROME" --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --disable-quic \
  --proxy-server=http://127.0.0.1:8899 '--proxy-bypass-list=<-loopback>' \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 \
  --user-data-dir=/profile --window-size=1280,720 --no-first-run --no-default-browser-check about:blank &
node -e '
const until = async () => { for (let i = 0; i < 100; i++) { try { if ((await fetch("http://127.0.0.1:9222/json/version")).ok) return; } catch {} await new Promise(r => setTimeout(r, 200)); } process.exit(1); };
until();'
node /opt/guest/stream.mjs &
exec node /app/cli.js --cdp-endpoint http://127.0.0.1:9222 --viewport-size 1280x720 "$@"
