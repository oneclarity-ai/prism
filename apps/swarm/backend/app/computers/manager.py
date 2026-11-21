"""Computers: one Docker container per agent, running the Playwright MCP server and Chromium.

The container is created on the first run, stopped when idle, and woken on the next run. Its
browser profile (logins, cookies) lives in a named volume and survives stop/start; `reset` deletes it.
The Docker CLI is used (not the SDK) so there is nothing extra to install; tests inject a fake runner.
"""

import asyncio
import hashlib
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.logging import log

MCP_PORT = 8931
STREAM_PORT = 8932  # live view of the screen (multipart JPEG)
GUEST_DIR = Path(__file__).parent / "guest"
LABEL = "prism.computer"
_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

Runner = Callable[[list[str]], Awaitable[tuple[int, str]]]


class ComputerError(Exception):
    """The computer could not be started or reached. The message is safe to log, not to show a user."""


async def docker(args: list[str]) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    except FileNotFoundError as exc:
        raise ComputerError("Docker is not installed on the worker machine.") from exc
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace").strip()


@dataclass
class ComputerInfo:
    key: str
    state: str  # missing | stopped | running
    url: str | None = None
    origins_hash: str | None = None
    stream_url: str | None = None


# Bump when the container's start options change: older computers are recreated (their profile is kept).
SPEC_VERSION = "5"


def origins_hash(origins: list[str]) -> str:
    return hashlib.sha256((SPEC_VERSION + ";".join(sorted(set(origins)))).encode()).hexdigest()[:12]


class ComputerManager:
    def __init__(self, runner: Runner | None = None, health: Callable[[str], Awaitable[bool]] | None = None):
        self.run = runner or docker
        self.health = health or self._mcp_up
        self._locks: dict[str, asyncio.Lock] = {}
        self._used: dict[str, float] = {}

    # ---------- names ----------

    @staticmethod
    def check_key(key: str) -> str:
        if not _KEY.match(key):
            raise ComputerError("Invalid computer key.")
        return key

    @staticmethod
    def container(key: str) -> str:
        return f"prism-computer-{key}"

    @staticmethod
    def volume(key: str) -> str:
        return f"prism-profile-{key}"

    @staticmethod
    def work_dir(key: str) -> Path:
        return (get_settings().computers_dir / key / "work").resolve()

    # ---------- state ----------

    async def info(self, key: str) -> ComputerInfo:
        self.check_key(key)
        code, out = await self.run(
            [
                "inspect",
                "-f",
                '{{.State.Running}}|{{index .Config.Labels "prism.origins"}}|'
                f'{{{{with index .NetworkSettings.Ports "{MCP_PORT}/tcp"}}}}{{{{(index . 0).HostPort}}}}{{{{end}}}}|'
                f'{{{{with index .NetworkSettings.Ports "{STREAM_PORT}/tcp"}}}}{{{{(index . 0).HostPort}}}}{{{{end}}}}',
                self.container(key),
            ]
        )
        if code != 0:
            if "no such container" in out.lower() or "no such object" in out.lower():
                return ComputerInfo(key, "missing")
            raise ComputerError(f"Docker is not available: {out[:200]}")  # e.g. the daemon is not running
        running, _, rest = out.partition("|")
        hashed, _, ports = rest.partition("|")
        port, _, stream_port = ports.partition("|")
        if running != "true":
            return ComputerInfo(key, "stopped", origins_hash=hashed or None)
        return ComputerInfo(
            key,
            "running",
            f"http://127.0.0.1:{port}/mcp" if port else None,
            hashed or None,
            f"http://127.0.0.1:{stream_port}/stream" if stream_port else None,
        )

    async def _mcp_up(self, url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(url.rsplit("/mcp", 1)[0] + "/")
            return response.status_code < 600
        except httpx.HTTPError:
            return False

    # ---------- lifecycle ----------

    async def ensure(self, key: str, origins: list[str] | None = None) -> str:
        """Start (or create) the computer and return its MCP URL. `origins` limits where it may browse."""
        self.check_key(key)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            wanted = origins_hash(origins or [])
            info = await self.info(key)
            if info.state != "missing" and info.origins_hash != wanted:
                await self.run(["rm", "-f", self.container(key)])  # profile volume stays
                info = ComputerInfo(key, "missing")
            if info.state == "missing":
                await self._create(key, origins or [], wanted)
            elif info.state == "stopped":
                code, out = await self.run(["start", self.container(key)])
                if code != 0:
                    raise ComputerError(f"docker start failed: {out[:300]}")
            url = await self._wait_ready(key)
            self._used[key] = time.monotonic()
            return url

    async def _create(self, key: str, origins: list[str], hashed: str) -> None:
        settings = get_settings()
        work = self.work_dir(key)
        work.mkdir(parents=True, exist_ok=True)
        # A new volume is owned by root but the browser runs as "node": without this Chromium cannot write its
        # profile and Playwright misreports it as "Browser is already in use".
        code, out = await self.run(
            [
                "run",
                "--rm",
                "--user",
                "root",
                "--entrypoint",
                "chown",
                "-v",
                f"{self.volume(key)}:/profile",
                settings.computer_image,
                "-R",
                "1000:1000",
                "/profile",
            ]
        )
        if code != 0:
            raise ComputerError(f"could not prepare the browser profile: {out[:300]}")
        args = [
            "run",
            "-d",
            "--name",
            self.container(key),
            "--label",
            f"{LABEL}={key}",
            "--label",
            f"prism.origins={hashed}",
            "--memory",
            settings.computer_memory,
            "--cpus",
            settings.computer_cpus,
            "--init",
            "--workdir",
            "/work",  # relative screenshot / file names land in the shared folder
            "-p",
            f"127.0.0.1::{MCP_PORT}",
            "-p",
            f"127.0.0.1::{STREAM_PORT}",
            "-v",
            f"{self.volume(key)}:/profile",
            "-v",
            f"{work}:/work",
            "-v",
            f"{GUEST_DIR}:/opt/guest:ro",
            "--entrypoint",
            "/bin/sh",
            "-e",
            f"PRISM_ALLOW_LOCAL_SITES={'1' if settings.computer_allow_local_sites else '0'}",
            settings.computer_image,
            "/opt/guest/start.sh",
            "--host",
            "0.0.0.0",
            "--port",
            str(MCP_PORT),
            "--allowed-hosts",
            "*",
            "--output-dir",
            "/work",
            "--image-responses",
            "omit",
            "--snapshot-mode",
            "none",
        ]
        if origins and "*" not in origins:
            args += ["--allowed-origins", ";".join(dict.fromkeys(origins))]
        code, out = await self.run(args)
        if code != 0:
            raise ComputerError(f"docker run failed: {out[:300]}")
        log.info("computer_created", key=key)

    async def _wait_ready(self, key: str) -> str:
        deadline = time.monotonic() + get_settings().computer_start_timeout_sec
        while time.monotonic() < deadline:
            info = await self.info(key)
            if info.state == "running" and info.url and await self.health(info.url):
                return info.url
            await asyncio.sleep(0.5)
        raise ComputerError("The computer did not become ready in time.")

    def touch(self, key: str) -> None:
        self._used[key] = time.monotonic()

    async def stop(self, key: str) -> bool:
        self.check_key(key)
        code, _ = await self.run(["stop", "-t", "5", self.container(key)])
        self._used.pop(key, None)
        return code == 0

    async def reset(self, key: str) -> None:
        """Forget everything: logins, cookies, downloads. The next run starts with a clean browser."""
        self.check_key(key)
        await self.run(["rm", "-f", self.container(key)])
        await self.run(["volume", "rm", "-f", self.volume(key)])
        self._used.pop(key, None)
        log.info("computer_reset", key=key)

    async def keys(self) -> list[str]:
        code, out = await self.run(
            ["ps", "-a", "--filter", f"label={LABEL}", "--format", '{{.Label "prism.computer"}}']
        )
        return [k for k in out.splitlines() if k] if code == 0 else []

    async def adopt(self) -> None:
        """After a worker restart: computers that are already running start their idle clock now."""
        for key in await self.keys():
            if (await self.info(key)).state == "running":
                self._used.setdefault(key, time.monotonic())

    async def reap_idle(self, busy: set[str]) -> list[str]:
        """Stop computers nobody has used for `computer_idle_minutes`. `busy` keys are never stopped."""
        limit = get_settings().computer_idle_minutes * 60
        stopped = []
        for key in list(self._used):
            if key not in busy and time.monotonic() - self._used[key] > limit:
                if await self.stop(key):
                    stopped.append(key)
        return stopped


manager = ComputerManager()
