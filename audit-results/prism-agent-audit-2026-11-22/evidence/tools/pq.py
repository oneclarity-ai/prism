"""Read-only Prism DB query helper. Usage: pq.py "SQL"."""
import sys
sys.path.insert(0, ".")
from sqlalchemy import create_engine, text
from app.core.config import get_settings
e = create_engine(get_settings().database_url)
with e.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    for row in c.execute(text(sys.argv[1])).all():
        print("\t".join("" if v is None else str(v) for v in row))
