"""Bounded search of the manager's private Prism conversations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_v21 import AgentThread, AgentThreadMessage
from app.models.enums import PrismLifecycleState
from app.models.prism_v22 import Prism


def _snippet(content: str, query: str) -> str:
    flat = " ".join(content.split())
    offset = flat.casefold().find(query.casefold())
    start = max(0, offset - 45) if offset >= 0 else 0
    end = min(len(flat), start + 160)
    return f"{'…' if start else ''}{flat[start:end]}{'…' if end < len(flat) else ''}"


class PrismSearchService:
    @staticmethod
    def search(db: Session, query: str) -> list[dict]:
        text = query.strip()
        if len(text) < 2:
            return []
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        active = Prism.state != PrismLifecycleState.ARCHIVED
        names = db.scalars(
            select(Prism)
            .where(active, Prism.name.ilike(pattern, escape="\\"))
            .order_by(Prism.name, Prism.id)
            .limit(10)
        )
        found = [
            {
                "kind": "prism",
                "prism_id": prism.id,
                "prism_name": prism.name,
                "message_id": None,
                "role": None,
                "created_at": None,
                "snippet": prism.description[:160],
            }
            for prism in names
        ]
        messages = db.execute(
            select(AgentThreadMessage, Prism.id, Prism.name)
            .join(AgentThread, AgentThread.id == AgentThreadMessage.thread_id)
            .join(Prism, Prism.id == AgentThread.prism_id)
            .where(
                active,
                AgentThread.is_canonical.is_(True),
                AgentThreadMessage.role.in_(("manager", "assistant")),
                AgentThreadMessage.content.ilike(pattern, escape="\\"),
            )
            .order_by(AgentThreadMessage.created_at.desc(), AgentThreadMessage.id.desc())
            .limit(20)
        )
        found.extend(
            {
                "kind": "message",
                "prism_id": prism_id,
                "prism_name": name,
                "message_id": message.id,
                "role": message.role,
                "created_at": message.created_at,
                "snippet": _snippet(message.content, text),
            }
            for message, prism_id, name in messages
        )
        return found
