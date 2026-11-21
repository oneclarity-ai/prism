"""The browser of a computer: Playwright MCP over HTTP, wrapped so the platform stays in control.

- Clicks on something that sends, posts, pays or deletes wait for a human (SDK approval pause).
- Every result passes through `mask` so a stored login can never reach the model or the run events.
- After each action that changes the page, `after` is called (used to capture a live frame).
"""

import re
from collections.abc import Awaitable, Callable
from typing import Any

from agents.mcp import MCPServerStdio, MCPServerStreamableHttp
from app.core.logging import log

# Browser tools whose result is a page change worth a new live frame.
ACTING_TOOLS = {
    "browser_navigate",
    "browser_navigate_back",
    "browser_click",
    "browser_type",
    "browser_fill_form",
    "browser_select_option",
    "browser_press_key",
    "browser_handle_dialog",
    "browser_wait_for",
}


class OutwardGuard:
    """Decides if a click needs a human. Best effort: it reads the label the agent gave the element."""

    def __init__(self, words: str, *, allowed_origins=None, synthetic_forms=False):
        self.patterns = [
            re.compile(rf"(?<!\w){re.escape(w.strip())}(?!\w)", re.I) for w in words.split(",") if w.strip()
        ]
        self.confirmed = False  # confirm_action was approved for the next click
        self.allowed_origins = allowed_origins
        self.synthetic_forms = synthetic_forms
        self.dummy_form = False
        self.links = {}
        self.low_risk_form = False

    def observed(self, result) -> None:
        text = "\n".join(getattr(item, "text", "") or "" for item in getattr(result, "content", []) or [])
        if "Page URL:" in text:
            self.low_risk_form = bool(
                re.search(r"search|filter|calculator|sandbox|test form|validation", text, re.I)
            ) and not bool(
                re.search(
                    r"password|payment|checkout|delete|contact us|send message|subscribe|sign up|publish",
                    text,
                    re.I,
                )
            )
            self.links = {}
            for ref, href in re.findall(r"\[ref=([^\]]+)\][^\n]*\n\s*- /url: (\S+)", text):
                self.links[ref] = href

    def acted(self, tool: str, args: dict) -> None:
        if tool in {
            "browser_navigate",
            "browser_navigate_back",
            "browser_click",
            "browser_press_key",
        }:
            self.dummy_form = False
            self.confirmed = False
        if tool in {"browser_fill_form", "browser_type", "browser_handle_dialog"}:
            self.confirmed = False
        if tool == "browser_fill_form":
            fields = args.get("fields") or []
            # Only clearly synthetic, low-risk fixtures receive a generic-submit exception.
            self.dummy_form = (
                bool(fields)
                and self.low_risk_form
                and all(isinstance(f, dict) for f in fields)
                and all(
                    not re.search(
                        r"password|card|payment|bank|token|secret",
                        self._text(f.get("name", "")),
                        re.I,
                    )
                    and bool(
                        re.fullmatch(
                            r"(?:Prism QA[^\n]{0,100}|prism-qa[\w.+-]*@example\.(?:invalid|test)|not-an-email|[0-9]{1,3}|)",
                            str(f.get("value", "")),
                            re.I,
                        )
                    )
                    for f in fields
                    if isinstance(f, dict)
                )
            )
        elif tool == "browser_type":
            self.dummy_form = False

    def reason(self, tool: str, args: dict[str, Any]) -> str | None:
        from app.runtime.qa_discovery import origin
        from app.runtime.tools import ToolError

        destination = (
            args.get("url")
            if tool == "browser_navigate"
            else self.links.get(args.get("ref"))
            if tool == "browser_click"
            else None
        )
        if destination and self.allowed_origins is not None:
            if str(destination).startswith(("http://", "https://", "//")):
                try:
                    target = origin("https:" + destination if destination.startswith("//") else destination)
                except ToolError:
                    return "Invalid site address"
                if target not in self.allowed_origins:
                    return f"New site requires request_site_access: {target}"
        if tool not in {
            "browser_click",
            "browser_fill_form",
            "browser_press_key",
            "browser_type",
            "browser_handle_dialog",
        }:
            return None
        if self.confirmed:
            return None
        if tool == "browser_press_key" and str(args.get("key") or "").casefold() in {
            "enter",
            "return",
        }:
            return "press Enter"
        if tool == "browser_type" and args.get("submit"):
            return "Submit typed input"
        if tool == "browser_handle_dialog" and args.get("accept"):
            return "Accept a confirmation dialog"
        label = self._text(args)
        if self.synthetic_forms and re.search(
            r"send|publish|payment|checkout|delet|purchas|invitation|sign.?up|create account|subscrib|transfer",
            label,
            re.I,
        ):
            return label[:200] or "an important change"
        for pattern in self.patterns:
            if pattern.search(label):
                if self.synthetic_forms and self.dummy_form and pattern.pattern == r"(?<!\w)submit(?!\w)":
                    continue
                return label[:200] or "an outward action"
        return None

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, dict):
            return " ".join(OutwardGuard._text(v) for v in value.values())
        if isinstance(value, list):
            return " ".join(OutwardGuard._text(v) for v in value)
        return str(value or "")


class GuardedStdioBrowser(MCPServerStdio):
    """The same approval and observation boundary for the worker's local-browser fallback."""

    def __init__(self, *, guard=None, mask=lambda value: value, observe=None, **kwargs):
        super().__init__(**kwargs)
        self._guard, self._mask, self._observe = guard, mask, observe

    def _get_needs_approval_for_tool(self, tool, agent):
        async def needs_approval(_context, args, _call_id):
            return self._guard is not None and self._guard.reason(tool.name, args or {}) is not None

        return needs_approval

    async def call_tool(self, tool_name, arguments, meta=None):
        result = await super().call_tool(tool_name, arguments, meta)
        if self._guard:
            self._guard.acted(tool_name, arguments or {})
            self._guard.observed(result)
        for item in getattr(result, "content", []) or []:
            if isinstance(getattr(item, "text", None), str):
                item.text = self._mask(item.text)
        if self._observe:
            await self._observe(result)
        return result


class ComputerBrowser(MCPServerStreamableHttp):
    def __init__(
        self,
        url: str,
        *,
        guard: OutwardGuard,
        mask: Callable[[str], str],
        after: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        observe=None,
        tool_filter=None,
    ):
        super().__init__(
            params={"url": url, "timeout": 30, "sse_read_timeout": 300},
            cache_tools_list=True,
            name="browser",
            client_session_timeout_seconds=90,
            tool_filter=tool_filter,
        )
        self._guard = guard
        self._mask = mask
        self._after = after
        self._observe = observe

    def _get_needs_approval_for_tool(self, tool, agent):
        guard = self._guard

        async def needs_approval(_context, args: dict[str, Any], _call_id: str) -> bool:
            return guard.reason(tool.name, args or {}) is not None

        return needs_approval

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None, meta: dict[str, Any] | None = None):
        result = await super().call_tool(tool_name, arguments, meta)
        self._guard.acted(tool_name, arguments or {})
        self._guard.observed(result)
        for item in getattr(result, "content", None) or []:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                item.text = self._mask(text)
        if self._observe:
            await self._observe(result)
        if self._after and tool_name in ACTING_TOOLS:
            try:
                await self._after(tool_name, arguments or {})
            except Exception as exc:  # noqa: BLE001 - a missed frame must never fail the agent's step
                log.warning("frame_hook_failed", tool=tool_name, error=f"{type(exc).__name__}: {exc}"[:300])
        return result
