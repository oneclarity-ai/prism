import asyncio, sys, os
from pathlib import Path
sys.path.insert(0, ".")
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings
async def main():
    e = create_async_engine(get_settings().database_url)
    async with e.connect() as c:
        await c.execute(text("SET TRANSACTION READ ONLY"))
        rows = (await c.execute(text("select kind, path, to_char(created_at,'MM-DD') d from artifacts order by created_at"))).all()
    await e.dispose()
    root = get_settings().artifacts_dir.resolve()
    print("api artifacts root (cwd-resolved):", root)
    import collections
    stat = collections.Counter()
    for kind, p, d in rows:
        pth = Path(p).resolve()
        api_ok = root in pth.parents and pth.is_file()
        alt = (Path("var") / p).resolve().is_file()   # file exists one level deeper
        stat[(d >= "11-19", api_ok, alt)] += 1
    print("(recent>=11-19, servable_by_api_resolution, exists_under_var/var):")
    for k, v in sorted(stat.items()): print(" ", k, v)
    print("total artifacts:", len(rows))
asyncio.run(main())
