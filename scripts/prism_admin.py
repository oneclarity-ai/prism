"""Operator commands for Prism v2.2 (run from the repository root).

    python scripts/prism_admin.py status
    python scripts/prism_admin.py recover-runs [--cancel-queued-older-than 60] [--force-running]
    python scripts/prism_admin.py recover-notifications [--stale-minutes 5]
    python scripts/prism_admin.py reset-cursors [--prism-id UUID]
    python scripts/prism_admin.py compact
    python scripts/prism_admin.py migrate-v21

Every command is idempotent, prints counts only, and never reads Teams or sends anything.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.services.prism_migration_service import PrismMigrationService  # noqa: E402
from app.services.prism_recovery_service import PrismRecoveryService  # noqa: E402
from app.services.prism_retention_service import PrismRetentionService  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    runs = commands.add_parser("recover-runs")
    runs.add_argument("--cancel-queued-older-than", type=int, metavar="MINUTES")
    runs.add_argument("--force-running", action="store_true")
    notifications = commands.add_parser("recover-notifications")
    notifications.add_argument("--stale-minutes", type=int, default=5)
    cursors = commands.add_parser("reset-cursors")
    cursors.add_argument("--prism-id", type=uuid.UUID)
    commands.add_parser("compact")
    commands.add_parser("migrate-v21")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        if args.command == "status":
            result = PrismRecoveryService.status(db)
        elif args.command == "recover-runs":
            result = PrismRecoveryService.recover_runs(
                db,
                cancel_queued_older_than_minutes=args.cancel_queued_older_than,
                force_running=args.force_running,
            )
        elif args.command == "recover-notifications":
            result = {
                "closed": PrismRecoveryService.recover_notifications(
                    db, stale_minutes=args.stale_minutes
                )
            }
        elif args.command == "reset-cursors":
            result = {"reset": PrismRecoveryService.reset_cursors(db, args.prism_id)}
        elif args.command == "compact":
            result = PrismRetentionService.compact(db)
        else:
            result = PrismMigrationService.adopt_legacy_conversation(db)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
