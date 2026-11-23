"""Per-run metrics from swarm DB (read-only). Writes CSV, no payload bodies."""
import asyncio, csv, sys, re, json
sys.path.insert(0, ".")
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings
OUT = sys.argv[1]
SQL = """
select left(r.id::text,8) run, a.key agent, r.status, r.model, r.attempt,
 extract(epoch from (r.ended_at - r.started_at))::int dur_s,
 r.input_tokens, r.output_tokens, coalesce(r.cached_input_tokens,0) cached, round(r.cost_usd::numeric,4) cost,
 (select count(*) from run_events e where e.run_id=r.id and e.type='tool_call') calls,
 (select count(*) from run_events e where e.run_id=r.id and e.type='tool_result' and (e.payload->>'output') ~* '(^error|### Error|not found|timed? ?out|blocked)') bad_results,
 (select count(*) from run_events e where e.run_id=r.id and e.type='tool_call' and e.payload->>'tool' like 'browser_navigate') navs,
 left(coalesce(r.error,''),90) err, r.resumes_run_id is not null is_resume
from runs r join agents a on a.id=r.agent_id order by a.key, r.created_at
"""
async def main():
    e = create_async_engine(get_settings().database_url)
    async with e.connect() as c:
        await c.execute(text("SET TRANSACTION READ ONLY"))
        res = await c.execute(text(SQL))
        rows = res.all()
        with open(OUT,"w",newline="") as f:
            w = csv.writer(f); w.writerow(res.keys()); w.writerows(rows)
        print(len(rows),"runs written")
    await e.dispose()
asyncio.run(main())
