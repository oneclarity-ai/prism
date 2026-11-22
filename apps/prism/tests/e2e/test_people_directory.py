"""The Teams > People page: who you are, who you chat with, and how they report."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from playwright.sync_api import Page, expect

from tests.e2e.test_prism_directory import open_sidebar_if_narrow


def seed_org() -> None:
    from app.db.session import SessionLocal
    from app.models.people.employee import Employee
    from app.models.teams.microsoft_connection import MicrosoftConnection

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(
            MicrosoftConnection(
                tenant_id="tenant-e2e",
                microsoft_user_id="me-e2e",
                user_principal_name="yash@example.com",
                display_name="Yash Mandi",
                encrypted_access_token="x",
                encrypted_refresh_token="x",
                access_token_expires_at=now + timedelta(hours=1),
                granted_scopes="User.Read",
            )
        )
        boss = Employee(
            name="Bela Boss", email="bela@example.com", role="Team member", title="VP Engineering"
        )
        db.add(boss)
        db.flush()
        me = Employee(
            name="Yash Mandi",
            email="yash@example.com",
            role="Team member",
            title="Engineering Manager",
            department="Engineering",
            teams_user_id="me-e2e",
            manager_id=boss.id,
        )
        db.add(me)
        db.flush()
        db.add(
            Employee(
                name="Asha Rao",
                email="asha@example.com",
                role="Team member",
                title="Backend Engineer",
                department="Engineering",
                teams_user_id="asha-e2e",
                manager_id=me.id,
                in_chats=True,
                last_chat_at=now,
            )
        )
        db.commit()


def open_people(page: Page) -> None:
    open_sidebar_if_narrow(page)
    page.locator("#nav-settings").click()
    page.get_by_role("tab", name="People").click()


def test_people_page_shows_me_the_team_and_keeps_edits(page: Page, e2e_app) -> None:
    seed_org()
    page.reload()
    open_people(page)

    me = page.locator("#people-me")
    expect(me).to_contain_text("Yash Mandi")
    expect(me).to_contain_text("Engineering Manager · Engineering")
    expect(me).to_contain_text("Reports to Bela Boss")
    expect(me).to_contain_text("1 direct report")

    expect(page.locator(".people-group-title", has_text="Your manager")).to_be_visible()
    expect(page.locator(".people-group-title", has_text="Reports to you")).to_be_visible()
    expect(page.locator(".person-row", has_text="Asha Rao")).to_contain_text(
        "Reports to Yash Mandi"
    )
    # Bela is only there so the tree connects.
    expect(page.locator(".person-row", has_text="Bela Boss")).to_contain_text("Org link")

    # Tell Prism what I do; it is saved against me.
    page.get_by_role("button", name="Edit about me").click()
    page.locator("#person-edit-responsibilities").fill("I run engineering delivery.")
    page.get_by_role("button", name="Save").click()
    expect(page.locator("#people-me")).to_contain_text("I run engineering delivery.")

    # Edit Asha: a hand-set title is marked as edited and survives a reload.
    page.locator(".person-row", has_text="Asha Rao").click()
    page.locator("#person-edit-title").fill("Tech Lead")
    page.get_by_role("button", name="Save").click()
    expect(page.locator(".person-row", has_text="Asha Rao")).to_contain_text("Tech Lead")
    expect(page.locator(".person-row", has_text="Asha Rao")).to_contain_text("Edited")
    page.reload()
    open_people(page)
    expect(page.locator(".person-row", has_text="Asha Rao")).to_contain_text("Tech Lead")

    # The org chart nests people under their manager.
    page.locator("[data-people-view='tree']").click()
    expect(
        page.locator(".org-tree .org-tree .org-tree .person-row", has_text="Asha Rao")
    ).to_be_visible()
    page.locator("#people-search").fill("zzz")
    expect(page.locator("#people-list")).to_contain_text("Nobody matches")
