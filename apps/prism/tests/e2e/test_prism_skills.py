"""Real API/browser and disposable PostgreSQL; fake LLM/Graph/engine only."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid

from playwright.sync_api import Page, expect


def create_prism(page: Page, name="Sales assistant", *, activate=True):
    organization = page.request.get("/api/v2/prisms/organization").json()
    chief_id = organization["chief_of_staff_id"]
    if not chief_id:
        chief = page.request.post(
            "/api/v2/prisms",
            data={
                "name": "Chief of Staff",
                "description": "Coordinate the team",
                "job_role": "Chief of Staff",
                "department": "Leadership",
                "activate": True,
            },
        )
        assert chief.status == 201, chief.text()
        chief_id = chief.json()["id"]
    response = page.request.post(
        "/api/v2/prisms",
        data={
            "name": name,
            "description": "Research prospects and prepare sales recommendations.",
            "job_role": "Sales analyst",
            "department": "Sales",
            "reports_to_prism_id": chief_id,
            "activate": activate,
        },
    )
    assert response.status == 201, response.text()
    return response.json()


def onboard_prism(page: Page, name="Sales assistant"):
    prism = create_prism(page, name, activate=False)
    url = f"/api/v2/prisms/{prism['id']}"
    session = page.request.post(f"{url}/onboarding/start", data={}).json()
    for question in session["questions"]:
        payload = {"expected_revision": session["revision"]}
        if question["key"] == "mission":
            payload["custom_text"] = (
                "Prepare account research for private Project Finch, using my agreed lead criteria."
            )
        elif question["key"] == "restrictions":
            payload["custom_text"] = (
                "Never contact a customer or change external data without approval."
            )
        elif question["choices"]:
            payload["selected_values"] = [question["choices"][0]["value"]]
        else:
            payload["custom_text"] = "Give me a concise report with evidence."
        response = page.request.post(
            f"{url}/onboarding/questions/{question['id']}/answer", data=payload
        )
        assert response.status == 200, response.text()
        session = response.json()
    agreement = page.request.get(f"{url}/agreement").json()
    prism = page.request.get(url).json()
    response = page.request.post(
        f"{url}/agreement/confirm",
        data={
            "expected_agreement_revision": agreement["revision"],
            "expected_lifecycle_version": prism["lifecycle_version"],
        },
    )
    assert response.status == 200, response.text()
    assert response.json()["skills_created"] == 3, response.text()
    return response.json()["prism"]


def create_skill(page: Page, name="Qualify leads", **overrides):
    content = {
        "name": name,
        "description": "Research prospective customers",
        "instructions": "Compare public evidence and report uncertainties. Ask before contacting anyone.",
        "required_tools": [],
        "required_connections": [],
        **overrides,
    }
    response = page.request.post("/api/v2/prisms/skills/library", data=content)
    assert response.status == 201, response.text()
    return response.json()


def assign(page, prism, skill, enabled=True, revision=0):
    response = page.request.put(
        f"/api/v2/prisms/{prism['id']}/skills/{skill['id']}",
        data={
            "enabled": enabled,
            "expected_skill_revision": skill["revision"],
            "expected_assignment_revision": revision,
        },
    )
    assert response.status == 200, response.text()
    return response.json()


def test_skills_are_isolated_versioned_and_do_not_grant_tools(page: Page):
    from app.db.session import SessionLocal
    from app.models.prisms.prism_v22 import Prism
    from app.services.prisms.prism_agent_service import PrismAgentService
    from app.services.prisms.prism_presets import effective_grants
    from app.services.prisms.prism_skill_service import PrismSkillService

    first = create_prism(page)
    other = create_prism(page, "Customer service")
    skill = create_skill(page)
    with SessionLocal() as db:
        before = effective_grants(db.get(Prism, uuid.UUID(first["id"])))
    assign(page, first, skill)
    with SessionLocal() as db:
        assert PrismSkillService.context(db, uuid.UUID(other["id"])) == []
        prism = db.get(Prism, uuid.UUID(first["id"]))
        assert effective_grants(prism) == before
        assert "Compare public evidence" in PrismAgentService.spec(db, prism)["instructions"]
    updated = page.request.put(
        f"/api/v2/prisms/skills/library/{skill['id']}",
        data={
            **{
                key: skill[key]
                for key in (
                    "name",
                    "description",
                    "instructions",
                    "required_tools",
                    "required_connections",
                )
            },
            "instructions": "New instructions awaiting explicit adoption.",
            "expected_revision": 1,
        },
    ).json()
    assert updated["revision"] == 2
    with SessionLocal() as db:
        assert (
            "Compare public evidence"
            in PrismSkillService.context(db, uuid.UUID(first["id"]))[0]["instructions"]
        )
    stale = page.request.put(
        f"/api/v2/prisms/{first['id']}/skills/{skill['id']}",
        data={"enabled": True, "expected_skill_revision": 1, "expected_assignment_revision": 1},
    )
    assert stale.status == 409
    assign(page, first, updated, revision=1)
    with SessionLocal() as db:
        assert (
            "New instructions"
            in PrismSkillService.context(db, uuid.UUID(first["id"]))[0]["instructions"]
        )
    assign(page, first, updated, enabled=False, revision=2)
    with SessionLocal() as db:
        assert PrismSkillService.context(db, uuid.UUID(first["id"])) == []
    assert (
        page.request.post(
            "/api/v2/prisms/skills/library",
            data={
                "name": " qualify LEADS ",
                "description": "Duplicate",
                "instructions": "Duplicate",
            },
        ).status
        == 409
    )


def test_interview_resumes_keeps_answers_private_and_requires_explicit_approval(page: Page):
    first = create_prism(page)
    other = create_prism(page, "Marketing")
    url = f"/api/v2/prisms/{first['id']}/skills/interview"
    setup = page.request.post(f"{url}/start", data={}).json()
    assert setup["status"] == "questions"
    assert page.request.get("/api/v2/prisms/skills/library").json() == []
    setup = page.request.post(
        f"{url}/answer",
        data={
            "expected_revision": setup["revision"],
            "key": "tasks",
            "answer": "Private customer context: Project Finch",
        },
    ).json()
    assert (
        page.request.post(f"{url}/start", data={})
        .json()["answers"]["tasks"]
        .endswith("Project Finch")
    )
    assert (
        page.request.post(
            f"{url}/answer", data={"expected_revision": 1, "key": "outputs", "answer": "old tab"}
        ).status
        == 409
    )
    for key, answer in (("outputs", "A concise report"), ("boundaries", "No external changes")):
        setup = page.request.post(
            f"{url}/answer",
            data={"expected_revision": setup["revision"], "key": key, "answer": answer},
        ).json()
    assert setup["status"] == "review" and setup["suggestions"]
    assert page.request.get("/api/v2/prisms/skills/library").json() == []
    other_setup = page.request.post(
        f"/api/v2/prisms/{other['id']}/skills/interview/start", data={}
    ).json()
    assert "Project Finch" not in str(other_setup)
    edited = {
        **setup["suggestions"][0],
        "name": "Sales research",
        "instructions": "Research public company information and cite sources.",
    }
    response = page.request.post(
        f"{url}/approve", data={"expected_revision": setup["revision"], "skills": [edited]}
    )
    assert response.status == 200, response.text()
    assert response.json()["skills"][0]["enabled"]
    library = page.request.get("/api/v2/prisms/skills/library").json()
    assert "Project Finch" not in str(library)
    assert (
        page.request.get(f"/api/v2/prisms/{other['id']}/skills").json()["skills"][0]["enabled"]
        is False
    )
    assert (
        page.request.post(
            f"{url}/approve", data={"expected_revision": setup["revision"], "skills": [edited]}
        ).status
        == 409
    )


def test_missing_connections_limits_archived_prisms_and_library_restore(page: Page):
    from app.db.session import SessionLocal
    from app.models.enums import PrismLifecycleState
    from app.models.prisms.prism_v22 import Prism
    from app.services.prisms.prism_skill_service import PrismSkillService

    prism = create_prism(page)
    skill = create_skill(
        page, required_tools=["save_file", "invented_tool"], required_connections=["outlook"]
    )
    result = assign(page, prism, skill)
    assert "Connection not supported yet: outlook" in result["skills"][0]["missing"]
    assert "Tool access is off: save_file" in result["skills"][0]["missing"]
    with SessionLocal() as db:
        ctx = PrismSkillService.context(db, uuid.UUID(prism["id"]))
        assert ctx[0]["instructions"].startswith("Unavailable")
    for i in range(7):
        assign(page, prism, create_skill(page, name=f"Workflow {i}"))
    ninth = create_skill(page, name="Ninth workflow")
    assert (
        page.request.put(
            f"/api/v2/prisms/{prism['id']}/skills/{ninth['id']}",
            data={"enabled": True, "expected_skill_revision": 1},
        ).status
        == 422
    )
    data = {
        key: skill[key]
        for key in ("name", "description", "instructions", "required_tools", "required_connections")
    }
    assert (
        page.request.put(
            f"/api/v2/prisms/skills/library/{skill['id']}",
            data={**data, "expected_revision": 1, "archived": True},
        ).status
        == 200
    )
    assert (
        page.request.put(
            f"/api/v2/prisms/skills/library/{skill['id']}",
            data={**data, "expected_revision": 2, "archived": False},
        ).status
        == 200
    )
    rows = page.request.get(f"/api/v2/prisms/{prism['id']}/skills").json()["skills"]
    assert next(row for row in rows if row["id"] == skill["id"])["enabled"] is False
    with SessionLocal() as db:
        db.get(Prism, uuid.UUID(prism["id"])).state = PrismLifecycleState.ARCHIVED
        db.commit()
    assert (
        page.request.post(f"/api/v2/prisms/{prism['id']}/skills/interview/start", data={}).status
        == 422
    )
    assert (
        page.request.put(
            f"/api/v2/prisms/{prism['id']}/skills/{ninth['id']}",
            data={"enabled": True, "expected_skill_revision": 1},
        ).status
        == 422
    )


def test_skills_and_tools_are_separate_and_onboarding_skills_are_editable(page: Page):
    first = onboard_prism(page)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.reload()
    page.wait_for_load_state("networkidle")
    assert not errors, errors
    page.evaluate("window.prism.openSettings('skills')")
    library = page.locator("#settings-skills-library")
    expect(library).to_contain_text("No shared skills yet")
    library.get_by_role("button", name="Add skill", exact=True).click()
    dialog = page.locator("dialog.workspace-dialog")
    dialog.get_by_label("Skill name", exact=True).fill("Write sales briefs")
    dialog.get_by_label("What this skill does").fill("Summarize sales opportunities")
    dialog.get_by_label("Reusable instructions").fill(
        "Cite sources; draft recommendations for approval."
    )
    dialog.get_by_role("button", name="Save", exact=True).click()
    expect(library).to_contain_text("Write sales briefs")
    page.evaluate("window.prism.closeSettings()")
    page.route(
        "**/api/v2/operations/overview",
        lambda route: route.fulfill(
            json={
                key: []
                for key in ("agents", "positions", "tasks", "runs", "approvals", "bugs", "targets")
            }
        ),
    )
    page.evaluate("window.prism.applyV24Mode(true)")
    page.evaluate(
        "id => document.dispatchEvent(new CustomEvent('prism:workspace-navigate', {detail: {page: 'prism', id}}))",
        first["id"],
    )
    page.get_by_role("tab", name="Skills").click()
    cards = page.locator(".prism-skill-grid").first.locator(".prism-skill-card")
    expect(cards).to_have_count(3)
    expect(page.locator("#prism-skill-setup")).to_have_count(0)
    cards.first.get_by_role("button", name="Edit skill").click()
    dialog = page.locator("dialog.workspace-dialog")
    dialog.get_by_label("Skill name", exact=True).fill("Account research workflow")
    dialog.get_by_label("Reusable instructions").fill(
        "Compare account research with approved criteria. Cite sources and ask before outreach."
    )
    dialog.get_by_role("button", name="Save", exact=True).click()
    expect(cards.filter(has_text="Account research workflow")).to_have_count(1)
    if os.getenv("PRISM_SKILL_CAPTURES"):
        from pathlib import Path

        for theme in ("dark", "light"):
            page.evaluate("theme => window.prismTheme.set(theme)", theme)
            page.screenshot(
                path=Path(os.environ["PRISM_SKILL_CAPTURES"])
                / f"skill-cards-{theme}-{page.viewport_size['width']}.png",
                animations="disabled",
            )
    before = page.request.get(f"/api/v2/prisms/{first['id']}/tools").json()
    page.get_by_role("tab", name="Tools").click()
    expect(page.locator("#operations-content")).to_contain_text("Tool access")
    expect(page.locator(".prism-skill-card")).to_have_count(0)
    expect(page.locator(".pd-grant").first).to_be_visible()
    page.get_by_role("tab", name="Skills").click()
    expect(cards).to_have_count(3)
    assert page.request.get(f"/api/v2/prisms/{first['id']}/tools").json() == before
    shared = page.request.get("/api/v2/prisms/skills/library").json()
    assert len(shared) == 1 and shared[0]["name"] == "Write sales briefs"
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
    assert not errors, errors


def test_automatic_skills_are_private_idempotent_and_do_not_reenable_disabled_skills(page: Page):
    from app.db.session import SessionLocal
    from app.models.prisms.prism_v22 import Prism
    from app.services.prisms.prism_presets import effective_grants, grants_for

    prism = onboard_prism(page)
    url = f"/api/v2/prisms/{prism['id']}"
    own = page.request.get(f"{url}/skills").json()["skills"]
    assert len(own) == 3 and all(
        skill["owner_prism_id"] == prism["id"] and skill["enabled"] for skill in own
    )
    assert page.request.get("/api/v2/prisms/skills/library").json() == []
    assert all("Project Finch" in skill["instructions"] for skill in own)
    conversation = page.request.get(f"{url}/conversation").json()
    notices = [
        message
        for message in conversation["messages"]
        if message["message_metadata"].get("kind") == "skills_created"
    ]
    assert len(notices) == 1 and "3 skills" in notices[0]["content"]
    other = create_prism(page, "Customer assistant")
    assert page.request.get(f"/api/v2/prisms/{other['id']}/skills").json()["skills"] == []
    assert (
        page.request.put(
            f"/api/v2/prisms/{other['id']}/skills/{own[0]['id']}",
            data={"enabled": True, "expected_skill_revision": own[0]["revision"]},
        ).status
        == 404
    )
    assign(page, prism, own[0], enabled=False, revision=1)
    retry = page.request.post(f"{url}/skills/from-onboarding", data={})
    assert retry.status == 200 and retry.json()["skills_created"] == 0
    assert len(retry.json()["skills"]) == 3
    assert (
        next(skill for skill in retry.json()["skills"] if skill["id"] == own[0]["id"])["enabled"]
        is False
    )
    messages = page.request.get(f"{url}/conversation").json()["messages"]
    assert (
        len(
            [
                message
                for message in messages
                if message["message_metadata"].get("kind") == "skills_created"
            ]
        )
        == 1
    )
    with SessionLocal() as db:
        row = db.get(Prism, uuid.UUID(prism["id"]))
        assert effective_grants(row) == grants_for(row.capabilities, row.logins_policy)
    assert (
        page.request.post(f"/api/v2/prisms/{other['id']}/skills/from-onboarding", data={}).status
        == 422
    )


def test_generation_reuses_chat_answers_without_an_extra_interview(page: Page, monkeypatch):
    from app.services.llm.llm_service import LLMService

    original = LLMService.complete
    calls = []

    def complete(**kwargs):
        calls.append(kwargs)
        if kwargs["feature"] != "prism_onboarding_skills":
            return original(**kwargs)
        return kwargs["output_model"].model_validate(
            {
                "skills": [
                    {
                        "name": name,
                        "description": "Support the agreed sales workflow",
                        "instructions": "Research the agreed accounts, cite evidence and request approval before outreach.",
                        "required_tools": [],
                        "required_connections": [],
                    }
                    for name in ("Account research", "Sales priorities", "Sales reporting")
                ]
            }
        )

    monkeypatch.setattr(LLMService, "complete", staticmethod(complete))
    prism = onboard_prism(page)
    generated = [call for call in calls if call["feature"] == "prism_onboarding_skills"]
    assert len(generated) == 1
    assert "Project Finch" in generated[0]["context"]["onboarding"]["mission"]
    assert any(
        answer["key"] == "restrictions"
        for answer in generated[0]["context"]["onboarding"]["answers"]
    )
    assert not any(
        call["feature"] in {"prism_skill_questions", "prism_skill_suggestions"} for call in calls
    )
    skills = page.request.get(f"/api/v2/prisms/{prism['id']}/skills").json()["skills"]
    assert {skill["name"] for skill in skills} == {
        "Account research",
        "Sales priorities",
        "Sales reporting",
    }
    assert (
        page.request.post(f"/api/v2/prisms/{prism['id']}/skills/from-onboarding", data={}).json()[
            "skills_created"
        ]
        == 0
    )
    assert len([call for call in calls if call["feature"] == "prism_onboarding_skills"]) == 1


def test_model_tailors_questions_then_suggests_only_after_answers(page: Page, monkeypatch):
    from app.services.llm.llm_service import LLMService

    requests = []
    original = LLMService.complete

    def complete(**kwargs):
        if not kwargs["feature"].startswith("prism_skill_"):
            return original(**kwargs)
        requests.append(kwargs)
        data = (
            {
                "tasks": "Which customer segments should I research?",
                "outputs": "Which evidence belongs in the sales brief?",
                "boundaries": "What outreach needs your review?",
                "task_options": ["Research prospects", "Prepare account briefs"],
            }
            if kwargs["feature"] == "prism_skill_questions"
            else {
                "skills": [
                    {
                        "name": "Account research",
                        "description": "Prepare an evidence-backed account brief",
                        "instructions": "Use public sources and show uncertainties. Prepare drafts for approval.",
                        "required_tools": ["browser"],
                        "required_connections": ["computer"],
                    }
                ]
            }
        )
        return kwargs["output_model"].model_validate(data)

    monkeypatch.setattr(LLMService, "complete", staticmethod(complete))
    prism = create_prism(page)
    url = f"/api/v2/prisms/{prism['id']}/skills/interview"
    setup = page.request.post(f"{url}/start", data={}).json()
    assert "customer segments" in setup["questions"][0]["prompt"]
    assert len(requests) == 1
    for key in ("tasks", "outputs", "boundaries"):
        setup = page.request.post(
            f"{url}/answer",
            data={
                "expected_revision": setup["revision"],
                "key": key,
                "answer": f"Manager answer for {key}",
            },
        ).json()
        assert len(requests) == (2 if key == "boundaries" else 1)
    assert setup["suggestions"][0]["name"] == "Account research"
    assert requests[1]["context"]["answers"]["tasks"] == "Manager answer for tasks"
    assert page.request.get("/api/v2/prisms/skills/library").json() == []


def test_skill_migration_roundtrip_preserves_preexisting_prism(e2e_app):
    from sqlalchemy import create_engine, text

    from app.db.session import engine

    schema = f"skill_migration_{uuid.uuid4().hex[:8]}"
    admin = create_engine(engine.url, isolation_level="AUTOCOMMIT")
    url = engine.url.set(query={"options": f"-csearch_path={schema}"})
    base = engine.url.set(query={}).render_as_string(hide_password=False)
    # Alembic ConfigParser needs the same unencoded search_path used by the E2E harness.
    env = {**os.environ, "DATABASE_URL": f"{base}?options=-csearch_path={schema}"}
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        def migrate(*args):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", *args], env=env, capture_output=True, text=True
            )
            assert result.returncode == 0, result.stderr.replace(base, "[database]")

        migrate("upgrade", "20261121_0046")
        scratch = create_engine(url)
        original_id = uuid.uuid4()
        with scratch.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO prisms (id,name,normalized_name,description,template_key,state,lifecycle_version,agreement_revision) VALUES (:id,'Before skills','before skills','Preserve me','blank','DRAFT',1,0)"
                ),
                {"id": original_id},
            )
        migrate("upgrade", "head")
        with scratch.begin() as connection:
            prism_id = connection.scalar(text("SELECT id FROM prisms"))
            assert prism_id == original_id
            assert re.fullmatch(
                r"p[A-Za-z0-9]{5}", connection.scalar(text("SELECT code FROM prisms"))
            )
            assert connection.scalar(text("SELECT legacy_code FROM prisms")) == "PR-1"
            assert connection.scalar(text("SELECT name FROM prisms")) == "Before skills"
            assert connection.scalar(text("SELECT description FROM prisms")) == "Preserve me"
            for name, owner in (("Shared skill", None), ("Private skill", prism_id)):
                connection.execute(
                    text(
                        "INSERT INTO prism_skills (id,name,normalized_name,description,instructions,required_tools,required_connections,revision,archived,owner_prism_id) VALUES (:id,:name,:name,'Description','Instructions','[]','[]',1,false,:owner)"
                    ),
                    {"id": uuid.uuid4(), "name": name, "owner": owner},
                )
        migrate("downgrade", "20261122_0049")
        with scratch.connect() as connection:
            assert connection.scalar(text("SELECT code FROM prisms")) == "PR-1"
            assert connection.scalar(text("SELECT id FROM prisms")) == original_id
        migrate("upgrade", "head")
        with scratch.connect() as connection:
            assert re.fullmatch(
                r"p[A-Za-z0-9]{5}", connection.scalar(text("SELECT code FROM prisms"))
            )
            assert connection.scalar(text("SELECT legacy_code FROM prisms")) == "PR-1"
        migrate("downgrade", "20261121_0047")
        with scratch.connect() as connection:
            assert connection.execute(text("SELECT name FROM prism_skills")).scalars().all() == [
                "Shared skill"
            ]
            assert connection.scalar(text("SELECT description FROM prisms")) == "Preserve me"
        migrate("upgrade", "head")
        with scratch.connect() as connection:
            assert connection.scalar(text("SELECT owner_prism_id FROM prism_skills")) is None
            assert connection.scalar(text("SELECT id FROM prisms")) == original_id
            assert re.fullmatch(
                r"p[A-Za-z0-9]{5}", connection.scalar(text("SELECT code FROM prisms"))
            )
        migrate("downgrade", "20261121_0046")
        with scratch.connect() as connection:
            assert connection.scalar(text("SELECT description FROM prisms")) == "Preserve me"
            assert connection.scalar(text("SELECT to_regclass('prism_skills')")) is None
        migrate("upgrade", "head")
        scratch.dispose()
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
