"""Pure deterministic policy used by V2 decisions and scenario evaluation."""

from __future__ import annotations


class ManagementPolicy:
    @staticmethod
    def recommend(signals: dict) -> str:
        """Return an allow-listed action from factual signals only."""
        if signals.get("manager_suppressed"):
            return "NO_ACTION"
        if signals.get("protected_action") or signals.get("urgent_manager_risk"):
            return "REQUEST_MANAGER_APPROVAL"
        if signals.get("completion_confirmed") and signals.get("dependent_waiting"):
            return "UPDATE_DEPENDENT"
        if signals.get("completion_confirmed"):
            return "ACKNOWLEDGE"
        if signals.get("clarification_needed") or (
            signals.get("blocked") and not signals.get("owner_known")
        ):
            return "ASK_CLARIFICATION"
        if signals.get("new_commitment"):
            return "CREATE_COMMITMENT"
        if signals.get("revised_eta"):
            return "UPDATE_COMMITMENT"
        if signals.get("recent_meaningful_response"):
            return "NO_ACTION"
        if signals.get("followups_today", 0) >= signals.get("max_followups_per_day", 1):
            return "NO_ACTION"
        if signals.get("overdue_minutes", 0) > 0:
            if signals.get("dependent_waiting") or signals.get("overdue_minutes", 0) >= 120:
                return "FOLLOW_UP"
            return "NO_ACTION"
        if signals.get("silence_hours", 0) >= 48 and signals.get("blocked"):
            return "FOLLOW_UP"
        if signals.get("unanswered_hours", 0) >= 4 and signals.get("question_material", True):
            return "FOLLOW_UP"
        if signals.get("ordinary_update"):
            return "ACKNOWLEDGE" if signals.get("acknowledgement_useful") else "NO_ACTION"
        return "NO_ACTION"
