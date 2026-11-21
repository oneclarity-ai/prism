"""Platform tools: the only way an agent changes OneClarity state.

Runtime adapters wrap these methods as framework tools (OpenAI Agents SDK function tools,
or direct calls from the fake runtime). Every method opens its own short DB session.
"""

import json
import mimetypes
import re
import shutil
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.logging import log
from app.core.security import decrypt_secret
from app.db.enums import ArtifactKind, BugStatus, Severity, TestCaseStatus
from app.db.models import Artifact, BugDraft, Run, Secret, TargetApp, Task, TestCase
from app.db.session import SessionLocal

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_FILE_BYTES = 2 * 1024 * 1024


def site_origin(site: str) -> str:
    """scheme://host[:port] of a site given with or without a scheme."""
    parts = urlsplit(site if "://" in site else f"https://{site}")
    return f"{parts.scheme}://{parts.netloc}".lower()


GITHUB_REPO = re.compile(r"github\.com[/:]([^/]+)/([^/.]+)")


class ToolError(Exception):
    """Raised for bad tool input; the message is returned to the agent."""


class PlatformTools:
    def __init__(
        self,
        run_id: uuid.UUID,
        org_id: uuid.UUID,
        task_id: uuid.UUID,
        work_dir: Path,
        related_run_ids: list[uuid.UUID] | None = None,
        scope: dict[str, Any] | None = None,
        computer_key: str | None = None,
    ):
        self.run_id = run_id
        # This run plus the runs it resumes: test cases from the paused run stay addressable.
        self.related_run_ids = related_run_ids or [run_id]
        self.org_id = org_id
        self.task_id = task_id
        self.work_dir = work_dir
        self.scope = scope  # the scope of this run (the task's, narrowed to the chosen pages)
        self.completed: dict[str, Any] | None = None
        self._warned_pending = False
        self._registered: dict[str, str] = {}  # source file name -> artifact id
        self.secret_values: set[str] = set()  # values to mask in run events
        self.computer_key = computer_key
        self.files: list[dict[str, Any]] = []  # files the agent made for the user
        # A computer's work folder outlives runs: files already there belong to earlier runs.
        self._skip: set[str] = {p.name for p in work_dir.rglob("*") if p.is_file()} if work_dir.exists() else set()
        self._frame_no = 0

    # ---------- read ----------

    async def get_task_context(self) -> dict[str, Any]:
        async with SessionLocal() as s:
            task = await s.get(Task, self.task_id)
            target = await s.get(TargetApp, task.target_app_id) if task.target_app_id else None
            previous = await s.scalar(
                select(Run.summary)
                .where(Run.task_id == self.task_id, Run.id != self.run_id, Run.summary != "")
                .order_by(Run.created_at.desc())
                .limit(1)
            )
        return {
            "task": {"title": task.title, "goal": task.goal, "scope": self.scope or task.scope},
            "target_app": (
                {
                    "name": target.name,
                    "base_url": target.base_url,
                    "environment": target.environment,
                    "notes": target.notes,
                    "has_test_login": target.has_test_login,
                }
                if target
                else None
            ),
            "previous_run_summary": previous or None,
        }

    async def get_test_login(self) -> dict[str, str]:
        async with SessionLocal() as s:
            task = await s.get(Task, self.task_id)
            target = await s.get(TargetApp, task.target_app_id) if task.target_app_id else None
            if not target or not target.auth_secret_id:
                raise ToolError("This target app has no test login configured.")
            secret = await s.get(Secret, target.auth_secret_id)
            login = json.loads(decrypt_secret(secret.encrypted_value))
        self.secret_values.add(login.get("password", ""))
        return {"username": login["username"], "password": login["password"]}

    # ---------- test plan and results ----------

    async def save_test_plan(self, cases: list[dict[str, str]]) -> list[dict[str, str]]:
        if not cases:
            raise ToolError("Provide at least one test case.")
        saved = []
        async with SessionLocal() as s:
            for c in cases:
                tc = TestCase(
                    run_id=self.run_id,
                    title=(c.get("title") or "Untitled case")[:300],
                    given=c.get("given", ""),
                    when=c.get("when", ""),
                    then=c.get("then", ""),
                )
                s.add(tc)
                await s.flush()
                saved.append({"id": str(tc.id), "title": tc.title})
            await s.commit()
        return saved

    async def _find_case(self, s, case: str) -> TestCase:
        try:
            tc = await s.get(TestCase, uuid.UUID(case))
            if tc and tc.run_id in self.related_run_ids:
                return tc
        except ValueError:
            pass
        tc = await s.scalar(
            select(TestCase)
            .where(TestCase.run_id.in_(self.related_run_ids), func.lower(TestCase.title) == case.lower())
            .limit(1)
        )
        if tc is None:
            raise ToolError(f"No test case '{case}' in this run. Use an id or exact title from save_test_plan.")
        return tc

    async def record_test_result(self, case: str, status: str, notes: str = "", screenshot: str | None = None) -> str:
        valid = {s.value for s in TestCaseStatus} - {"pending"}
        if status not in valid:
            raise ToolError(f"status must be one of {sorted(valid)}")
        artifact_id = await self.register_file(screenshot, ArtifactKind.screenshot) if screenshot else None
        async with SessionLocal() as s:
            tc = await self._find_case(s, case)
            tc.status = status
            tc.notes = notes
            if artifact_id:
                tc.evidence_artifact_ids = [*tc.evidence_artifact_ids, uuid.UUID(artifact_id)]
            await s.commit()
            return f"Recorded '{tc.title}' as {status}."

    # ---------- bugs ----------

    async def draft_bug(
        self,
        title: str,
        steps: str,
        expected: str,
        actual: str,
        severity: str = "medium",
        case: str | None = None,
    ) -> dict[str, str]:
        if severity not in {s.value for s in Severity}:
            raise ToolError("severity must be critical, high, medium or low")
        async with SessionLocal() as s:
            tc = await self._find_case(s, case) if case else None
            bug = BugDraft(
                run_id=self.run_id,
                test_case_id=tc.id if tc else None,
                title=title[:300],
                steps=steps,
                expected=expected,
                actual=actual,
                severity=severity,
            )
            s.add(bug)
            await s.commit()
            return {"bug_id": str(bug.id), "title": bug.title}

    async def file_bug(self, bug_id: str) -> str:
        """Create an external issue. Only reached after a human approved it (ask-first)."""
        async with SessionLocal() as s:
            bug = await s.get(BugDraft, uuid.UUID(bug_id))
            if bug is None or bug.run_id not in await self._task_run_ids(s):
                raise ToolError("Unknown bug id for this task.")
            task = await s.get(Task, self.task_id)
            target = await s.get(TargetApp, task.target_app_id) if task.target_app_id else None
            token_row = await s.scalar(
                select(Secret).where(Secret.org_id == self.org_id, Secret.name == "github-token")
            )
            match = GITHUB_REPO.search(target.repo_url or "") if target else None
            if match and token_row:
                owner, repo = match.groups()
                body = f"**Steps**\n{bug.steps}\n\n**Expected**\n{bug.expected}\n\n**Actual**\n{bug.actual}\n\n_Filed by the OneClarity QA agent._"
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.post(
                        f"https://api.github.com/repos/{owner}/{repo}/issues",
                        headers={
                            "Authorization": f"Bearer {decrypt_secret(token_row.encrypted_value)}",
                            "Accept": "application/vnd.github+json",
                        },
                        json={"title": bug.title, "body": body, "labels": ["qa-agent", bug.severity]},
                    )
                if r.status_code >= 300:
                    raise ToolError(f"GitHub refused the issue ({r.status_code}): {r.text[:200]}")
                bug.status = BugStatus.filed
                bug.external_url = r.json().get("html_url")
                await s.commit()
                return f"Filed on GitHub: {bug.external_url}"
            bug.status = BugStatus.approved
            await s.commit()
            return (
                "Approved by a human. No GitHub repo or 'github-token' secret is configured, "
                "so the bug is marked approved inside OneClarity instead of being filed externally."
            )

    async def _task_run_ids(self, s) -> list[uuid.UUID]:
        return list(await s.scalars(select(Run.id).where(Run.task_id == self.task_id)))

    # ---------- files ----------

    async def register_file(self, name: str | None, kind: str = ArtifactKind.screenshot) -> str | None:
        """Copy a file the browser wrote into artifact storage and record it. Returns the artifact id."""
        if not name:
            return None
        src = self._resolve(name)
        if src is None:
            raise ToolError(f"File '{name}' not found in this run's work folder.")
        if src.name in self._registered:
            return self._registered[src.name]
        dest_dir = get_settings().artifacts_dir / str(self.run_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        async with SessionLocal() as s:
            art = Artifact(
                run_id=self.run_id,
                kind=kind,
                path=str(dest),
                mime=mimetypes.guess_type(dest.name)[0] or "application/octet-stream",
                meta={"source": src.name, "bytes": dest.stat().st_size},
            )
            s.add(art)
            await s.commit()
            self._registered[src.name] = str(art.id)
            return str(art.id)

    def _resolve(self, name: str) -> Path | None:
        candidate = Path(name)
        if not candidate.is_absolute():
            candidate = self.work_dir / candidate
        try:
            candidate = candidate.resolve()
            candidate.relative_to(self.work_dir.resolve())  # never leave the run folder
        except (ValueError, OSError):
            return None
        if candidate.is_file():
            return candidate
        matches = list(self.work_dir.rglob(Path(name).name))
        return matches[0] if matches else None

    async def collect_new_images(self) -> list[dict[str, str]]:
        """Register every new image in the work folder (screenshots taken by the browser tool)."""
        found = []
        for f in sorted(self.work_dir.rglob("*")):
            if f.name in self._skip or f.name.startswith("frame-"):
                continue
            if f.suffix.lower() in IMAGE_SUFFIXES and f.name not in self._registered:
                art_id = await self.register_file(str(f), ArtifactKind.screenshot)
                found.append({"artifact_id": art_id, "file": f.name})
        return found

    # ---------- comments and completion ----------

    async def complete_task(
        self,
        summary: str,
        outcome: str = "passed",
        results: list[dict[str, Any]] | None = None,
        files: list[str] | None = None,
    ) -> str:
        if outcome not in {"passed", "failed", "blocked"}:
            raise ToolError("outcome must be passed, failed or blocked")
        pending = await self.pending_cases()
        if pending and not self._warned_pending:
            self._warned_pending = True  # ask once; a second call finishes anyway
            names = "; ".join(pending[:20])
            return (
                f"Not finished yet: {len(pending)} planned case(s) have no result: {names}. "
                "Run them and call record_test_result, or record them as 'skipped' with the reason. "
                "Then call complete_task again."
            )
        rows = [{str(k)[:60]: self.mask(str(v))[:1000] for k, v in row.items()} for row in (results or [])[:200]]
        names = {f["name"] for f in self.files}
        for name in files or []:
            if name not in names:
                await self.save_existing(name)
        self.completed = {
            "summary": summary,
            "outcome": outcome,
            "results": rows,
            "files": [{"name": f["name"], "artifact_id": f["artifact_id"]} for f in self.files],
        }
        log.info("task_completed", run_id=str(self.run_id), outcome=outcome)
        return "Task marked complete. Stop now."

    async def pending_cases(self) -> list[str]:
        async with SessionLocal() as s:
            rows = await s.scalars(
                select(TestCase.title).where(
                    TestCase.run_id.in_(self.related_run_ids), TestCase.status == TestCaseStatus.pending
                )
            )
            return list(rows)

    async def close_pending_cases(self, reason: str) -> int:
        """Planned cases that never got a result are marked skipped, so no case stays 'pending'
        forever after the run has ended."""
        async with SessionLocal() as s:
            rows = list(
                await s.scalars(
                    select(TestCase).where(
                        TestCase.run_id.in_(self.related_run_ids), TestCase.status == TestCaseStatus.pending
                    )
                )
            )
            for tc in rows:
                tc.status = TestCaseStatus.skipped
                tc.notes = f"Not run: {reason}"
            await s.commit()
        return len(rows)

    # ---------- generic work: files, logins, frames ----------

    async def save_file(self, name: str, content: str) -> str:
        """Write a text file for the user (csv, md, txt, json) and keep it with the run."""
        clean = Path(name).name
        if clean != name or not re.fullmatch(r"[\w][\w .\-]{0,100}\.(csv|md|txt|json)", clean):
            raise ToolError("Use a plain file name ending in .csv, .md, .txt or .json.")
        if len(content.encode()) > MAX_FILE_BYTES:
            raise ToolError("File too large (2 MB limit).")
        out = self.work_dir / "out"
        out.mkdir(parents=True, exist_ok=True)
        (out / clean).write_text(self.mask(content), encoding="utf-8")
        return await self.save_existing(str(out / clean))

    async def save_existing(self, name: str) -> str:
        artifact_id = await self.register_file(name, ArtifactKind.file)
        label = Path(name).name
        if artifact_id and label not in {f["name"] for f in self.files}:
            self.files.append({"name": label, "artifact_id": artifact_id})
        return f"Saved {label}."

    async def login_for(self, site: str) -> dict[str, str]:
        """The stored login for a site of this computer. The password is masked from every event."""
        origin = site_origin(site)
        async with SessionLocal() as s:
            secret = await s.scalar(
                select(Secret).where(Secret.org_id == self.org_id, Secret.name == f"login:{self.computer_key}:{origin}")
            )
            if secret is None:
                raise ToolError(f"No login is stored for {origin}. Call request_login first.")
            login = json.loads(decrypt_secret(secret.encrypted_value))
        for value in (login.get("password"), login.get("username")):
            if value:
                self.secret_values.add(value)
        return {"username": login["username"], "password": login["password"]}

    def next_frame_name(self) -> str:
        self._frame_no += 1
        return f"frame-{str(self.run_id)[:8]}-{self._frame_no:04d}.jpeg"

    async def add_frame(self, name: str, keep: int) -> str | None:
        """Register a live frame; only the newest `keep` frames of the run are kept."""
        src = self._resolve(name)
        if src is None:
            return None
        artifact_id = await self.register_file(str(src), ArtifactKind.frame)
        async with SessionLocal() as s:
            old = list(
                await s.scalars(
                    select(Artifact)
                    .where(Artifact.run_id == self.run_id, Artifact.kind == ArtifactKind.frame)
                    .order_by(Artifact.created_at.desc())
                    .offset(keep)
                )
            )
            for art in old:
                Path(art.path).unlink(missing_ok=True)
                await s.delete(art)
            await s.commit()
        src.unlink(missing_ok=True)
        return artifact_id

    def mask(self, text: str) -> str:
        for value in self.secret_values:
            if value:
                text = text.replace(value, "***")
        return text
