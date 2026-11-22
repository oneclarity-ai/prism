"""Fake runtime: a scripted QA agent that needs no model.

It calls the real platform tools (so test cases, bug drafts and approvals are real rows)
and emits the same kind of live events as the real agent. Use it to try the whole flow
without Azure credentials, and in tests.
"""

import asyncio
from urllib.parse import urljoin

from app.runtime.base import Interruption, RunCancelled, RunContext, RunResult

STEP_DELAY = 0.8


class FakeAdapter:
    type = "fake"

    def __init__(self, delay: float = STEP_DELAY):
        self.delay = delay

    def check_ready(self) -> str | None:
        return None

    async def _pause(self, ctx: RunContext) -> None:
        await asyncio.sleep(self.delay)
        if await ctx.is_cancelled():
            raise RunCancelled()

    async def _call(self, ctx: RunContext, tool: str, args: dict, result) -> None:
        await ctx.emit("tool_call", {"tool": tool, "arguments": args})
        await self._pause(ctx)
        await ctx.emit("tool_result", {"tool": tool, "output": str(result)[:2000]})

    async def _say(self, ctx: RunContext, text: str) -> None:
        await ctx.emit("message", {"role": "assistant", "text": text})
        await self._pause(ctx)

    async def execute(self, ctx: RunContext) -> RunResult:
        if ctx.saved_state:
            return await self._resume(ctx)

        t = ctx.tools
        await self._say(ctx, "I am the fake QA agent (scripted, no model). Reading the task first.")
        context = await t.get_task_context()
        await self._call(ctx, "get_task_context", {}, context)

        base = ctx.task.target_url or "http://localhost:4000"
        scope = ctx.task.scope or {}
        pages = scope.get("urls") or ["/", "/login.html", "/shop.html", "/contact.html"]

        if ctx.task.has_test_login and ctx.grant("get_test_login") != "off":
            login = await t.get_test_login()
            await self._call(ctx, "get_test_login", {}, {"username": login["username"], "password": "***"})

        await self._say(ctx, f"Exploring {len(pages)} pages on {base}.")
        for page in pages:
            url = urljoin(base if base.endswith("/") else base + "/", page.lstrip("/"))
            await self._call(ctx, "browser_navigate", {"url": url}, f"Navigated to {url}")
            await self._call(ctx, "browser_snapshot", {}, f"Page snapshot of {url} (simulated)")

        features = scope.get("features") or []
        criteria = scope.get("acceptance_criteria") or []
        cases = [
            {
                "title": "Home page loads",
                "given": "a visitor",
                "when": "they open the home page",
                "then": "the page renders without errors",
            },
            {
                "title": "Login rejects a wrong password",
                "given": "a known user",
                "when": "they sign in with a wrong password",
                "then": "an error is shown and they stay signed out",
            },
            {
                "title": "Login with valid credentials",
                "given": "the test account",
                "when": "they sign in",
                "then": "they are signed in",
            },
            {
                "title": "Contact form requires a message",
                "given": "the contact page",
                "when": "the form is sent without a message",
                "then": "a validation error is shown",
            },
        ]
        cases += [
            {
                "title": f"Feature works: {f}",
                "given": "the app",
                "when": f"the user uses {f}",
                "then": "it behaves as expected",
            }
            for f in features[:3]
        ]
        cases += [{"title": f"Criterion: {c[:80]}", "given": "", "when": "", "then": c} for c in criteria[:3]]
        saved = await t.save_test_plan(cases)
        await self._call(ctx, "save_test_plan", {"cases": len(cases)}, f"Saved {len(saved)} test cases")

        failing = {"Login rejects a wrong password", "Contact form requires a message"}
        bug_ids = []
        for case in saved:
            status = "fail" if case["title"] in failing else "pass"
            notes = (
                "Observed behaviour differs from expected (simulated)."
                if status == "fail"
                else "Works as expected (simulated)."
            )
            msg = await t.record_test_result(case["id"], status, notes)
            await self._call(ctx, "record_test_result", {"case": case["title"], "status": status}, msg)
            if status == "fail":
                bug = await t.draft_bug(
                    title=f"[Simulated] {case['title']} fails",
                    steps=f"1. Open {base}\n2. Follow the test case '{case['title']}'",
                    expected="As described in the test case",
                    actual="The opposite happened (simulated by the fake runtime)",
                    severity="high",
                    case=case["id"],
                )
                bug_ids.append(bug["bug_id"])
                await self._call(ctx, "draft_bug", {"title": bug["title"]}, bug)

        grant = ctx.grant("file_bug")
        if bug_ids and scope.get("allow_bug_filing") and grant != "off":
            if grant == "ask_first":
                await self._say(ctx, f"I want to file {len(bug_ids)} bug(s). Filing needs human approval, pausing.")
                return RunResult(
                    status="waiting_approval",
                    saved_state={"runtime": "fake", "bug_ids": bug_ids},
                    interruptions=[
                        Interruption(call_id=f"fake-{i}", tool="file_bug", arguments={"bug_id": b})
                        for i, b in enumerate(bug_ids)
                    ],
                )
            for b in bug_ids:
                await self._call(ctx, "file_bug", {"bug_id": b}, await t.file_bug(b))

        return await self._finish(ctx, len(saved), len(bug_ids))

    async def _resume(self, ctx: RunContext) -> RunResult:
        t = ctx.tools
        await self._say(ctx, "Resuming after the approval decision.")
        bug_ids = ctx.saved_state.get("bug_ids", [])
        decisions = {d.call_id: d for d in ctx.decisions}
        for i, b in enumerate(bug_ids):
            d = decisions.get(f"fake-{i}")
            if d and d.approved:
                await self._call(ctx, "file_bug", {"bug_id": b}, await t.file_bug(b))
            else:
                reason = f" Reviewer said: {d.comment}" if d and d.comment else ""
                await self._say(ctx, f"Bug {b[:8]} was not approved, leaving it as a draft.{reason}")
        return await self._finish(ctx, None, len(bug_ids))

    async def _finish(self, ctx: RunContext, cases: int | None, bugs: int) -> RunResult:
        summary = (
            f"Simulated QA run finished. {bugs} bug(s) drafted."
            if cases is None
            else f"Simulated QA run: {cases} test cases, {bugs} failed and were drafted as bugs."
        )
        result = await ctx.tools.complete_task(summary, "failed" if bugs else "passed")
        await self._call(ctx, "complete_task", {"outcome": "failed" if bugs else "passed"}, result)
        return RunResult(status="succeeded", summary=summary)
