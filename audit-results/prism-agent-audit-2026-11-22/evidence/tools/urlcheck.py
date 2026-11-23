"""For each run of given agents: URLs navigated vs URLs cited in result/summary. Read-only."""
import asyncio, sys, re, json
sys.path.insert(0, ".")
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings
agents = sys.argv[1:]
U = re.compile(r"https?://[^\s\"'\\)>\]]+")
norm = lambda u: re.sub(r"[#?].*$", "", u).rstrip("/.,;")
async def main():
    e = create_async_engine(get_settings().database_url)
    async with e.connect() as c:
        await c.execute(text("SET TRANSACTION READ ONLY"))
        runs = (await c.execute(text("select r.id, a.key, r.status, to_char(r.created_at,'MM-DD HH24:MI'), r.summary, r.result::text, r.task_id from runs r join agents a on a.id=r.agent_id where a.key = any(:k) order by r.created_at"), {"k": agents})).all()
        for rid, key, st, ts, summ, res, tid in runs:
            ev = (await c.execute(text("select payload->'arguments'->>'url' from run_events where run_id=:r and type='tool_call' and payload->>'tool'='browser_navigate'"), {"r": rid})).all()
            nav = {norm(x[0]) for x in ev if x[0]}
            # page URLs seen in snapshots too (links followed in-page)
            pages = (await c.execute(text("select substring(payload->>'output' from 'Page URL: (https?://[^\\\\\\n ]+)') from run_events where run_id=:r and type='tool_result'"), {"r": rid})).all()
            seen = nav | {norm(x[0]) for x in pages if x[0]}
            cited = {norm(u) for u in U.findall((summ or "") + " " + (res or ""))}
            uncited_visited = len(seen - cited)
            fabricated = sorted(cited - seen)
            host = lambda u: re.sub(r"^https?://(www\.)?","",u).split("/")[0]
            fab_hosts_unvisited = sorted({host(u) for u in fabricated} - {host(u) for u in seen})
            print(f"{str(rid)[:8]} {key[-8:]} {st:9} {ts} navigated={len(nav)} seen={len(seen)} cited={len(cited)} cited_not_seen={len(fabricated)} cited_hosts_never_visited={len(fab_hosts_unvisited)} {fab_hosts_unvisited[:4]}")
    await e.dispose()
asyncio.run(main())
