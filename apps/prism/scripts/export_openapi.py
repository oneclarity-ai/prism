"""Write the FastAPI OpenAPI schema to a file; frontend/package.json `types` turns it into TypeScript."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("frontend/openapi.json")
    target.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
