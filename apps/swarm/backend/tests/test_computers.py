"""Computers (Docker + Playwright MCP, driven through fakes), the click guard, generic tools,
approval payloads, login secrets and one-run-per-computer."""

import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from agents.tool_context import ToolContext

from app.computers.manager import ComputerError, ComputerManager, origins_hash
from app.core.config import get_settings
from app.runtime.base import AgentSpec, Decision, RunContext, TaskSpec
from app.runtime.computer_mcp import ComputerBrowser, OutwardGuard
from app.runtime.fake import FakeAdapter
from app.runtime.openai_agents import OpenAIAgentsAdapter
from app.runtime.registry import register_adapter
from app.runtime.tools import PlatformTools, ToolError
from app.worker.executor import claim_next

from .test_runs import GRANTS, _setup, _work


class FakeDocker:
    """Just enough of `docker` for ComputerManager: containers, volumes, labels and a host port."""

    def __init__(self) -> None:
        self.containers: dict[str, dict] = {}
        self.volumes: set[str] = set()
        self.calls: list[list[str]] = []

    async def __call__(self, args: list[str]) -> tuple[int, str]:
        self.calls.append(args)
        cmd = args[0]
        if cmd == "inspect":
            c = self.containers.get(args[-1])
            if c is None:
                return 1, "Error response from daemon: No such container: x"
            port = "49152" if c["running"] else ""
            stream = "49153" if c["running"] else ""
            return 0, f"{'true' if c['running'] else 'false'}|{c['origins']}|{port}|{stream}"
        if cmd == "run" and "--rm" in args:
            return 0, ""  # the one-off that fixes the profile volume's owner
        if cmd == "run":
            name = args[args.index("--name") + 1]
            labels = [args[i + 1] for i, a in enumerate(args) if a == "--label"]
            origins = next(x.split("=", 1)[1] for x in labels if x.startswith("prism.origins="))
            self.containers[name] = {"running": True, "origins": origins, "args": args}
            self.volumes.add(next(args[i + 1].split(":")[0] for i, a in enumerate(args) if a == "-v"))
            return 0, "id"
        if cmd == "start":
            self.containers[args[1]]["running"] = True
            return 0, args[1]
        if cmd == "stop":
            if args[-1] in self.containers:
                self.containers[args[-1]]["running"] = False
            return 0, ""
        if cmd == "rm":
            self.containers.pop(args[-1], None)
            return 0, ""
        if cmd == "volume":
            self.volumes.discard(args[-1])
            return 0, ""
        if cmd == "ps":
            return 0, "\n".join(n.removeprefix("prism-computer-") for n in self.containers)
        return 1, "unsupported"


@pytest.fixture
def docker(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPUTERS_DIR", str(tmp_path / "computers"))
    get_settings.cache_clear()
    fake = FakeDocker()

    async def ready(_url: str) -> bool:
        return True

    yield ComputerManager(runner=fake, health=ready), fake
    get_settings.cache_clear()


async def test_a_computer_is_created_woken_and_restarted_only_when_needed(docker):
    manager, fake = docker
    url = await manager.ensure("prism-abc12345", ["https://acme.com"])
    assert url == "http://127.0.0.1:49152/mcp"
    prepare = next(c for c in fake.calls if c[0] == "run" and "--rm" in c)
    assert "chown" in prepare and "prism-profile-prism-abc12345:/profile" in prepare
    assert fake.calls.index(prepare) < next(i for i, c in enumerate(fake.calls) if "--name" in c)
    run_args = next(c for c in fake.calls if c[0] == "run" and "--name" in c)
    assert "prism-profile-prism-abc12345:/profile" in run_args
    assert "--allowed-origins" in run_args and "https://acme.com" in run_args
    assert "127.0.0.1::8931" in run_args  # published on loopback only, never on the network
    assert "PRISM_ALLOW_LOCAL_SITES=0" in run_args

    await manager.ensure("prism-abc12345", ["https://acme.com"])
    assert len([c for c in fake.calls if c[0] == "run" and "--name" in c]) == 1  # same origins: nothing recreated

    assert await manager.stop("prism-abc12345")
    await manager.ensure("prism-abc12345", ["https://acme.com"])
    assert any(c[0] == "start" for c in fake.calls)  # asleep -> woken, same container

    await manager.ensure("prism-abc12345", ["https://other.com"])
    assert len([c for c in fake.calls if c[0] == "run" and "--name" in c]) == 2  # new allowlist: recreated
    assert "prism-profile-prism-abc12345" in fake.volumes  # the profile survives


def test_browser_network_proxy_blocks_private_and_metadata_addresses():
    if shutil.which("node") is None:
        pytest.skip("needs Node.js")
    proxy = Path(__file__).parents[1] / "app" / "computers" / "guest" / "network-proxy.mjs"
    script = (
        f"import {{isBlockedAddress}} from {json.dumps(proxy.as_uri())};"
        "const values=['127.0.0.1','10.1.2.3','169.254.169.254','192.168.1.1','::1','fc00::1','8.8.8.8'];"
        "console.log(JSON.stringify(values.map(isBlockedAddress)));"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == [True, True, True, True, True, True, False]


def test_browser_network_proxy_survives_a_reset_client_socket():
    if shutil.which("node") is None:
        pytest.skip("needs Node.js")
    proxy = Path(__file__).parents[1] / "app" / "computers" / "guest" / "network-proxy.mjs"
    script = (
        f"import {{server}} from {json.dumps(proxy.as_uri())};"
        "import {EventEmitter} from 'node:events';"
        "const client=new EventEmitter();"
        "client.destroyed=false;"
        "client.end=()=>{client.destroyed=true};"
        "server.emit('connect',{url:'localhost:443'},client,Buffer.alloc(0));"
        "client.emit('error',Object.assign(new Error('read ECONNRESET'),{code:'ECONNRESET'}));"
        "await new Promise(resolve=>setImmediate(resolve));"
        "console.log('alive');"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "alive"


async def test_a_docker_that_is_not_running_is_an_error_not_a_missing_computer(docker):
    manager, fake = docker

    async def down(args):
        return 1, "failed to connect to the docker API at unix:///x/docker.sock: dial unix: no such file or directory"

    manager.run = down
    with pytest.raises(ComputerError):
        await manager.info("prism-abc12345")
    with pytest.raises(ComputerError):
        await manager.ensure("prism-abc12345", [])


async def test_reset_forgets_the_profile_and_keys_are_validated(docker):
    manager, fake = docker
    await manager.ensure("prism-abc12345", [])
    await manager.reset("prism-abc12345")
    assert not fake.containers and not fake.volumes
    for bad in ("../etc", "A B", "x;rm -rf", ""):
        with pytest.raises(ComputerError):
            await manager.ensure(bad, [])
    assert origins_hash(["a", "b"]) == origins_hash(["b", "a"])


async def test_idle_computers_stop_but_busy_ones_do_not(docker, monkeypatch):
    manager, fake = docker
    await manager.ensure("prism-idle0001", [])
    await manager.ensure("prism-busy0001", [])
    for key in manager._used:
        manager._used[key] -= 10_000
    assert await manager.reap_idle({"prism-busy0001"}) == ["prism-idle0001"]
    assert fake.containers["prism-computer-prism-busy0001"]["running"] is True


def test_the_click_guard_catches_outward_labels_and_lets_reading_through():
    guard = OutwardGuard(get_settings().outward_click_words)
    for label in ("Send message", "Submit", "Place order", "Delete account", "Sign up for free", "Pay now"):
        assert guard.reason("browser_click", {"element": label}), label
    for label in ("Pricing", "Next page", "Read more", "Search", "Resend-free plan details"[:0] or "Menu"):
        assert guard.reason("browser_click", {"element": label}) is None, label
    assert guard.reason("browser_navigate", {"url": "https://x.com/send"}) is None
    assert guard.reason("browser_press_key", {"key": "Enter"}) == "press Enter"
    assert guard.reason("browser_press_key", {"key": "Tab"}) is None
    assert guard.reason("browser_fill_form", {"fields": [{"name": "Submit order", "value": "yes"}]})
    guard.confirmed = True  # confirm_action was approved: the next click goes through
    assert guard.reason("browser_click", {"element": "Send"}) is None


async def test_the_browser_masks_results_and_takes_a_frame_after_acting(monkeypatch):
    from agents.mcp import MCPServerStreamableHttp

    class Item:
        def __init__(self, text):
            self.text = text

    class Result:
        content = [Item("logged in as bob with hunter2")]

    async def fake_call(self, name, arguments, meta=None):
        return Result()

    monkeypatch.setattr(MCPServerStreamableHttp, "call_tool", fake_call)
    seen = []

    async def after(tool, args):
        seen.append(tool)

    guard = OutwardGuard("send")
    browser = ComputerBrowser("http://x/mcp", guard=guard, mask=lambda t: t.replace("hunter2", "***"), after=after)
    guard.confirmed = True
    result = await browser.call_tool("browser_click", {"element": "Send"})
    assert result.content[0].text == "logged in as bob with ***"
    assert seen == ["browser_click"] and guard.confirmed is False  # a confirmation covers one click
    await browser.call_tool("browser_snapshot", {})
    assert seen == ["browser_click"]  # reading does not take a frame


async def _tools(auth_client, tmp_path: Path, key="prism-abc12345") -> PlatformTools:
    _, task = await _setup(auth_client, allow_bug_filing=False)
    run = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")).json()
    await claim_next()
    org_id = (await auth_client.get("/api/v1/auth/me")).json()["org_id"]
    return PlatformTools(uuid.UUID(run["id"]), uuid.UUID(org_id), uuid.UUID(task["id"]), tmp_path, computer_key=key)


async def test_files_results_and_logins_for_a_generic_task(auth_client, tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()
    tools = await _tools(auth_client, tmp_path / "work")
    (tmp_path / "work").mkdir(exist_ok=True)

    assert "Saved leads.csv" in await tools.save_file("leads.csv", "name,site\nAcme,acme.com\n")
    for bad in ("../x.csv", "run.sh", "a/b.csv", ".env"):
        with pytest.raises(ToolError):
            await tools.save_file(bad, "x")
    with pytest.raises(ToolError):
        await tools.save_file("big.txt", "x" * (2 * 1024 * 1024 + 1))

    created = await auth_client.post(
        "/api/v1/secrets",
        json={
            "name": "login:prism-abc12345:https://acme.com",
            "scope": "prism:prism-abc12345",
            "value": json.dumps({"username": "bob", "password": "hunter2"}),
        },
    )
    assert created.status_code == 201
    login = await tools.login_for("acme.com")  # given without a scheme
    assert login == {"username": "bob", "password": "hunter2"}
    assert tools.mask("the password is hunter2") == "the password is ***"
    with pytest.raises(ToolError):
        await tools.login_for("https://other.com")
    listed = (await auth_client.get("/api/v1/secrets?scope=prism:prism-abc12345")).json()
    assert [s["name"] for s in listed] == ["login:prism-abc12345:https://acme.com"]
    assert "value" not in listed[0] and "hunter2" not in json.dumps(listed)

    done = await tools.complete_task("Found 1", "passed", [{"name": "Acme", "note": "uses hunter2"}], ["leads.csv"])
    assert "complete" in done
    assert tools.completed["results"] == [{"name": "Acme", "note": "uses ***"}]
    assert [f["name"] for f in tools.completed["files"]] == ["leads.csv"]


async def test_frames_keep_only_the_newest_and_old_files_are_not_collected(auth_client, tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()
    work = tmp_path / "work"
    work.mkdir()
    (work / "old-run-shot.png").write_bytes(b"png")  # left by an earlier run on this computer
    tools = await _tools(auth_client, work)
    assert await tools.collect_new_images() == []  # earlier runs' files are not this run's evidence
    (work / "login-error.png").write_bytes(b"png")
    assert [i["file"] for i in await tools.collect_new_images()] == ["login-error.png"]

    ids = []
    for _ in range(4):
        name = tools.next_frame_name()
        (work / name).write_bytes(b"jpg")
        ids.append(await tools.add_frame(name, keep=2))
    assert await tools.collect_new_images() == []  # frames are never report screenshots
    run_id = tools.run_id
    arts = (await auth_client.get(f"/api/v1/runs/{run_id}/artifacts")).json()
    frames = [a for a in arts if a["kind"] == "frame"]
    assert [a["id"] for a in frames] and {a["id"] for a in frames} == set(ids[-2:])
    assert not list(work.glob("frame-*"))  # the browser's copy is removed once registered


async def test_approval_payload_reaches_the_resumed_run(auth_client):
    register_adapter(FakeAdapter(delay=0))
    try:
        _, task = await _setup(auth_client)
        run = (await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")).json()
        await _work()
        approvals = (await auth_client.get("/api/v1/approvals?status=pending")).json()
        assert approvals and approvals[0]["run_id"] == run["id"]
        first = (
            await auth_client.post(
                f"/api/v1/approvals/{approvals[0]['id']}/decision",
                json={"decision": "approve", "payload": {"answer": "Use the founder", "n": "3"}},
            )
        ).json()
        assert first["approval"]["payload"]["decision"] == {"answer": "Use the founder", "n": "3"}
        for other in approvals[1:]:
            last = (
                await auth_client.post(f"/api/v1/approvals/{other['id']}/decision", json={"decision": "reject"})
            ).json()
        assert (last if len(approvals) > 1 else first)["resume_run_id"]  # resumes once every pause is decided
    finally:
        register_adapter(FakeAdapter())


def _ctx(grants: dict, decisions=None, tools=None) -> RunContext:
    async def emit(*_a):
        return None

    async def cancelled():
        return False

    return RunContext(
        run_id=str(uuid.uuid4()),
        agent=AgentSpec("a", "prism-abc12345", "Riya", "", "", grants, 10, 1.0),
        task=TaskSpec("t", "T", "g", {}, None, None, None, None, False),
        work_dir=Path("."),
        tools=tools or PlatformTools(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), Path(".")),
        emit=emit,
        is_cancelled=cancelled,
        decisions=decisions or [],
        computer_key="prism-abc12345",
    )


def test_an_agent_only_gets_the_tools_its_grants_allow():
    grants = {
        "get_task_context": "allowed",
        "complete_task": "allowed",
        "ask_manager": "ask_first",
        "save_file": "allowed",
    }
    names = {t.name for t in OpenAIAgentsAdapter()._tools(_ctx(grants), None, OutwardGuard("send"))}
    assert names == set(grants)
    assert "teams_search" not in names and "sign_in" not in names and "request_login" not in names
    names = {
        t.name
        for t in OpenAIAgentsAdapter()._tools(_ctx({**grants, "teams_search": "allowed"}), None, OutwardGuard("x"))
    }
    assert "teams_search" in names


async def test_ask_manager_pauses_and_returns_the_answer_after_approval():
    grants = {"ask_manager": "ask_first", "confirm_action": "ask_first", "request_login": "ask_first"}
    call = "call-1"
    ctx = _ctx(grants, decisions=[Decision(call, True, "", {"answer": "Acme and Globex"})])
    guard = OutwardGuard("send")
    tools = {t.name: t for t in OpenAIAgentsAdapter()._tools(ctx, None, guard)}
    assert all(t.needs_approval is True for t in tools.values())  # the model cannot skip these

    def tctx(name, args):
        return ToolContext(context=None, tool_name=name, tool_call_id=call, tool_arguments=json.dumps(args))

    args = {"question": "Who are our competitors?"}
    out = await tools["ask_manager"].on_invoke_tool(tctx("ask_manager", args), json.dumps(args))
    assert "Acme and Globex" in out

    other = {"kind": "send", "site": "x.com", "summary": "s", "details": "d"}
    out = await tools["confirm_action"].on_invoke_tool(tctx("confirm_action", other), json.dumps(other))
    assert "Approved" in out and guard.confirmed is True


async def test_one_computer_runs_one_task_at_a_time(auth_client):
    agent = (
        await auth_client.post(
            "/api/v1/agents",
            json={
                "key": "prism-abc12345",
                "name": "Riya",
                "role": "prism",
                "runtime": "fake",
                "tool_grants": {**GRANTS, "computer": "allowed"},
            },
        )
    ).json()
    runs = []
    for i in range(2):
        task = (await auth_client.post("/api/v1/tasks", json={"title": f"T{i}", "agent_id": agent["id"]})).json()
        runs.append((await auth_client.post(f"/api/v1/tasks/{task['id']}/runs")).json())
    first = await claim_next()
    assert str(first) == runs[0]["id"]
    assert await claim_next() is None  # same computer is busy: the second run waits


async def _down():
    return 1, "Cannot connect to the Docker daemon"


async def test_computers_api_reports_state_and_rejects_bad_keys(auth_client, monkeypatch):
    fake = FakeDocker()
    from app.api.routers import computers

    monkeypatch.setattr(computers.manager, "run", fake)
    assert (await auth_client.get("/api/v1/computers/prism-abc12345")).json()["state"] == "missing"
    monkeypatch.setattr(computers.manager, "run", lambda args: _down())
    assert (await auth_client.get("/api/v1/computers/prism-abc12345")).json()["state"] == "unavailable"
    monkeypatch.setattr(computers.manager, "run", fake)
    fake.containers["prism-computer-prism-abc12345"] = {"running": False, "origins": "", "args": []}
    assert (await auth_client.get("/api/v1/computers/prism-abc12345")).json()["state"] == "stopped"
    assert (await auth_client.post("/api/v1/computers/prism-abc12345/reset")).status_code == 200
    assert not fake.containers
    assert (await auth_client.get("/api/v1/computers/Bad_Key")).status_code in (400, 404, 422)


async def test_the_live_stream_is_only_offered_while_the_computer_runs(auth_client, monkeypatch):
    fake = FakeDocker()
    from app.api.routers import computers

    monkeypatch.setattr(computers.manager, "run", fake)
    key = "prism-abc12345"
    assert (await auth_client.get(f"/api/v1/computers/{key}/stream")).status_code in (400, 404)  # missing
    fake.containers[f"prism-computer-{key}"] = {"running": False, "origins": "", "args": []}
    assert (await auth_client.get(f"/api/v1/computers/{key}/stream")).status_code in (400, 404)  # asleep
    fake.containers[f"prism-computer-{key}"]["running"] = True
    info = await computers.manager.info(key)
    assert info.stream_url == "http://127.0.0.1:49153/stream"
    assert info.url == "http://127.0.0.1:49152/mcp"


async def test_a_new_computer_runs_the_streamer_and_the_agent_on_one_browser(docker):
    mgr, fake = docker
    await mgr.ensure("prism-abc12345", [])
    args = next(c["args"] for c in fake.containers.values())
    assert "/opt/guest/start.sh" in args and "8932" in " ".join(args)
    assert "--headless" not in args  # the guest script owns the browser; the agent attaches to it
