"""Operator commands for Prism v2.2 (run from the repository root).

    python scripts/prism_admin.py status
    python scripts/prism_admin.py recover-runs [--cancel-queued-older-than 60] [--force-running]
    python scripts/prism_admin.py recover-notifications [--stale-minutes 5]
    python scripts/prism_admin.py reset-cursors [--prism-id UUID]
    python scripts/prism_admin.py compact
    python scripts/prism_admin.py migrate-v21
    python scripts/prism_admin.py qa-check
    python scripts/prism_admin.py work-check
    python scripts/prism_admin.py computers list|stop|reset [--key prism-xxxxxxxx]

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


def _qa_check() -> dict:
    """Confirm Prism can sign in to the testing workspace and that a tester is online."""

    from app.core.config import get_settings
    from app.services.qa_swarm_client import QaSwarmClient, SwarmError

    if not get_settings().qa_swarm_configured:
        return {"ok": False, "problem": "Set QA_SWARM_URL, QA_SWARM_EMAIL and QA_SWARM_PASSWORD"}
    try:
        with QaSwarmClient() as client:
            status = client.status()
            client.agent_id()
    except SwarmError as exc:
        return {"ok": False, "problem": str(exc)}
    return {
        "ok": status.get("workers_online", 0) > 0,
        "workers_online": status.get("workers_online", 0),
        "model_configured": bool(status.get("azure_configured")),
    }


def _work_check() -> dict:
    """v2.4: the engine is reachable, Docker answers on its machine, and the Teams bridge is signed."""

    from app.core.config import get_settings
    from app.services.qa_swarm_client import QaSwarmClient, SwarmError

    settings = get_settings()
    result: dict = {"v24_enabled": settings.prism_v24_enabled}
    if not settings.qa_swarm_configured:
        return {
            **result,
            "ok": False,
            "problem": "Set QA_SWARM_URL, QA_SWARM_EMAIL and QA_SWARM_PASSWORD",
        }
    try:
        with QaSwarmClient() as client:
            status = client.status()
            docker = client.computer("prism-check").get("state")
    except SwarmError as exc:
        return {**result, "ok": False, "problem": str(exc)}
    result.update(
        workers_online=status.get("workers_online", 0),
        model_configured=bool(status.get("azure_configured")),
        docker="ok"
        if docker in ("missing", "stopped", "running")
        else "not available on the engine machine",
        teams_bridge="configured"
        if settings.work_bridge_secret
        else "not configured (Teams tools off)",
    )
    result["ok"] = bool(
        settings.prism_v24_enabled and result["workers_online"] and result["docker"] == "ok"
    )
    return result


def _computers(action: str, key: str | None) -> dict:
    from app.models.work import PrismComputer
    from app.services.qa_swarm_client import QaSwarmClient, SwarmError

    with SessionLocal() as db:
        keys = [
            row.computer_key for row in db.query(PrismComputer).order_by(PrismComputer.computer_key)
        ]
    if action == "list":
        try:
            with QaSwarmClient() as client:
                return {k: client.computer(k).get("state") for k in keys}
        except SwarmError as exc:
            return {"ok": False, "problem": str(exc)}
    targets = [key] if key else keys
    done = []
    try:
        with QaSwarmClient() as client:
            for target in targets:
                (client.stop_computer if action == "stop" else client.reset_computer)(target)
                done.append(target)
    except SwarmError as exc:
        return {"ok": False, "problem": str(exc), "done": done}
    return {"ok": True, action: done}


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
    commands.add_parser("qa-check")
    commands.add_parser("work-check")
    computers = commands.add_parser("computers")
    computers.add_argument("action", choices=["list", "stop", "reset"])
    computers.add_argument("--key")
    args = parser.parse_args(argv)

    if args.command == "qa-check":
        print(json.dumps(_qa_check(), indent=2))
        return 0
    if args.command == "work-check":
        print(json.dumps(_work_check(), indent=2))
        return 0
    if args.command == "computers":
        print(json.dumps(_computers(args.action, args.key), indent=2))
        return 0
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
