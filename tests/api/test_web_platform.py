from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from api.security import create_session_token, decode_session_token
from main import app


def test_session_token_roundtrip():
    token = create_session_token(123456)
    assert decode_session_token(token)["tg_id"] == 123456


def test_tampered_session_token_is_rejected():
    token = create_session_token(123456)
    with pytest.raises(Exception) as exc_info:
        decode_session_token(token + "broken")
    assert exc_info.value.status_code == 401


def test_frontend_pages_and_assets_are_served():
    client = TestClient(app)
    for path in (
        "/auth.html",
        "/student.html",
        "/parent.html",
        "/admin.html",
        "/static/css/app.css",
        "/static/js/app.js",
        "/static/js/chat.js",
    ):
        assert client.get(path).status_code == 200


@pytest.mark.asyncio
async def test_v1_browser_login_returns_signed_session(api_client, mock_db):
    mock_db.mock_conn.fetchrow = AsyncMock(return_value={
        "tg_id": 777,
        "username": "student",
        "role": "student",
        "parent_id": 1,
    })
    response = await api_client.post("/api/v1/auth/browser-login", json={"tg_id": 777})
    assert response.status_code == 200
    assert decode_session_token(response.json()["session_token"])["tg_id"] == 777


@pytest.mark.asyncio
async def test_v1_dashboard_requires_authorization(api_client):
    response = await api_client.get("/api/v1/student/dashboard")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tutor_sessions_and_legacy_chat_require_authorization(api_client):
    sessions = await api_client.get("/api/v1/tutor/sessions")
    legacy = await api_client.get("/api/chats/history/777")

    assert sessions.status_code == 401
    assert legacy.status_code == 401


def test_auth_page_contains_interactive_telegram_entry():
    response = TestClient(app).get("/auth.html")

    assert response.status_code == 200
    assert 'id="telegram-login"' in response.text
    assert "telegram-web-app.js" in response.text
