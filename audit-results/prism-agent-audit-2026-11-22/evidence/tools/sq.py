"""Read-only swarm DB query helper. Usage: sq.py "SQL" ; prints rows as TSV."""
import asyncio, sys
sys.path.insert(0, ".")
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings

async def main(sql):
    e = create_async_engine(get_settings().database_url)
    async with e.connect() as c:
        await c.execute(text("SET TRANSACTION READ ONLY"))
        r = await c.execute(text(sql))
        for row in r.all():
            print("\t".join("" if v is None else str(v) for v in row))
    await e.dispose()
asyncio.run(main(sys.argv[1]))
