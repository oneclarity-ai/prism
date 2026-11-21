from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_is_served() -> None:
    response = TestClient(app).get("/dashboard/")

    assert response.status_code == 200
    assert "Prism" in response.text
    assert "Today's AI cost" in response.text
    assert "/dashboard/styles.css" in response.text
    assert "fonts.googleapis.com" not in response.text
    assert "Connect Microsoft account" in response.text
    assert "Refresh from Teams" in response.text
    assert 'id="people-me"' in response.text
    assert 'id="person-edit-dialog"' in response.text
    assert 'data-drawer-panel="people"' in response.text
    # The Teams page is the connection and the people; activity and delivery lists are gone.
    for removed in ("teams-activity-list", "Agent delivery health", "Retry failed replies"):
        assert removed not in response.text
    # The Teams page no longer offers the daily check-in automation.
    for removed in ("Teams automation", "Start automation", "Run daily cycle", "Send digest"):
        assert removed not in response.text
    assert 'data-subtab-target="automation"' not in response.text
    assert "toggle-automation-button" not in response.text
    assert "Daily manager review" in response.text
    assert "Blocker journeys" in response.text
    assert "Preview dummy flow" in response.text
    assert "Organisational memory" in response.text
    assert "Update memory" in response.text
    assert "Needs your attention" in response.text
    assert "Daily management brief" in response.text
    assert "Ask about the team" in response.text
    # The sidebar holds only Home, the Prism list, and Settings (Teams is a Settings section).
    sidebar = response.text[
        response.text.index('<aside class="sidebar"') : response.text.index("</aside>")
    ]
    for legacy in ("ask", "management", "journey", "memory", "knowledge", "teams"):
        assert f'data-tab-target="{legacy}"' not in sidebar
    assert 'data-tab-target="overview"' in sidebar
    assert 'data-tab-target="settings"' in sidebar
    assert 'data-subtab-target="teams"' in response.text
    assert 'data-tab="teams"' not in response.text
    assert 'data-tab="management"' in response.text
    assert 'data-tab="knowledge"' in response.text
    assert 'data-tab="memory"' in response.text
    assert 'data-tab="ask"' in response.text
    assert response.text.count("data-v21-legacy") >= 5
    assert 'data-tab-target="agent"' in response.text
    assert 'id="prism-create-button"' in response.text
    assert 'id="prism-directory-list"' in response.text
    assert 'data-tab="prisms"' in response.text
    assert "Create Prism" in response.text
    assert "prism-template" not in response.text
    assert "Ask Prism" in response.text
    assert 'id="prism-source-button"' in response.text
    assert 'id="prism-source-dialog"' in response.text
    assert 'id="prism-policy-button"' in response.text
    assert 'id="prism-policy-dialog"' in response.text
    assert 'id="prism-sync-button"' in response.text
    assert 'id="prism-trigger-button"' in response.text
    assert 'id="prism-trigger-dialog"' in response.text
    assert 'id="prism-notify-dialog"' in response.text
    assert "/dashboard/js/prism-updates.js" in response.text
    assert "/dashboard/js/agent-chat.js" in response.text
    assert "/dashboard/js/prism-directory.js" in response.text
    assert "/dashboard/app.js" in response.text
    assert 'data-subtabs="teams"' not in response.text
    assert 'data-subtabs="settings"' in response.text
    assert 'id="agent-composer"' in response.text
    assert response.text.count("data-connect-microsoft") >= 1
    assert '<p class="nav-label">Chats</p>' not in response.text
    assert "one conversation with Prism" in response.text
    # Directory import lives with the people it affects, in the Teams section of Settings.
    assert response.text.index('id="settings-dialog"') < response.text.index(
        'id="people-sync-button"'
    )


def test_dashboard_static_assets_are_served() -> None:
    client = TestClient(app)

    assert client.get("/dashboard/styles.css").status_code == 200
    script = client.get("/dashboard/app.js")
    assert script.status_code == 200
    assert "distribute-deployment-list" in script.text
    assert "Distribute list" in script.text
    assert "function applyV21Mode(enabled)" in script.text
    assert "legacyV21Tabs.has(state.activeTab)" in script.text

    agent_script = client.get("/dashboard/js/agent-chat.js")
    assert agent_script.status_code == 200
    assert "Approve and send" in agent_script.text
    assert "/execution" in agent_script.text
    assert "appendEvidence" in agent_script.text
    assert "Audit trail" in agent_script.text
    assert "Reject this draft?" in agent_script.text
    assert "/api/v2/agent/conversation" in agent_script.text
    assert "Why these sources" in agent_script.text
    assert "Load earlier messages" in agent_script.text
    assert "microsoft_reconnect_required" in agent_script.text
    assert "if (!list) return;" in agent_script.text
    assert 'title: "Draft a follow-up"' in agent_script.text
    assert 'confirmLabel: "Create draft"' in agent_script.text
    assert "pendingSubmission" in agent_script.text
    assert "typingBubble(pending.label)" in agent_script.text
    assert "Auto-selecting the relevant Teams chats" in agent_script.text
    assert "/sources/teams/resolve" not in agent_script.text

    prism_script = client.get("/dashboard/js/prism-directory.js")
    assert prism_script.status_code == 200
    assert "/api/v2/prisms" in prism_script.text
    assert "Create prism" in prism_script.text
    assert "Archive Prism" in prism_script.text
    assert "choose up to five" in prism_script.text
    assert "requestSubmit" in prism_script.text
    assert "/teams-policy" in prism_script.text
    assert "/trigger-policy" in prism_script.text
    assert "/runs/manual" in prism_script.text
    assert "/observations" in prism_script.text
    assert "prism:updates" in prism_script.text

    updates_script = client.get("/dashboard/js/prism-updates.js")
    assert updates_script.status_code == 200
    assert "/api/v2/prisms/notifications/claim" in updates_script.text
    assert "Notification.requestPermission" in updates_script.text
    assert "/notification-settings" in updates_script.text
    assert "renderUpdate" in agent_script.text
    assert "This is a different incident" in agent_script.text
    assert "Prepare a Teams draft" in agent_script.text
    assert "Was this useful?" in agent_script.text
    people_script = client.get("/dashboard/js/people-directory.js")
    assert people_script.status_code == 200
    assert "/api/v1/people/sync" in people_script.text
    assert "/api/v2/prisms/${detail.prismId}/people" in people_script.text
    health_script = client.get("/dashboard/js/prism-health.js")
    assert health_script.status_code == 200
    assert "/tuning/signals/" in health_script.text
    assert "/drafts`" in agent_script.text
