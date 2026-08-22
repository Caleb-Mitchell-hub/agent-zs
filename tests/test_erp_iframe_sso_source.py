from pathlib import Path


FRONTEND = Path("app/routers/frontend.py").read_text(encoding="utf-8")
ROUTER_JS_SOURCES = "\n".join(
    path.read_text(encoding="utf-8")
    for path in Path("app/routers").glob("*.py")
)


def test_main_page_reads_erp_url_token_before_redirect():
    assert "new URLSearchParams(window.location.search)" in FRONTEND
    assert "params.get('token')" in FRONTEND or 'params.get("token")' in FRONTEND
    assert "localStorage.setItem('agent_zs_token', incomingToken)" in FRONTEND
    assert "history.replaceState" in FRONTEND


def test_main_page_accepts_erp_post_message_token():
    assert "ERP_AGENT_ZS_SSO_TOKEN" in FRONTEND
    assert "addEventListener('message'" in FRONTEND or 'addEventListener("message"' in FRONTEND
    assert "event.data.token" in FRONTEND
    assert "localStorage.setItem('agent_zs_token', event.data.token)" in FRONTEND


def test_embedded_mode_uses_agent_ai_api_base():
    assert "function resolveApiBase" in FRONTEND
    assert "'/agent-ai-api'" in FRONTEND or '"/agent-ai-api"' in FRONTEND
    assert "const API_QUERY_STREAM = `${API_BASE}/query/stream`;" in FRONTEND
    assert "const API_SESSIONS = `${API_BASE}/sessions`;" in FRONTEND
    assert "const API_TASKS = `${API_BASE}/tasks`;" in FRONTEND


def test_embedded_login_paths_do_not_escape_to_erp_root():
    assert "function resolveAppBase" in FRONTEND
    assert "const LOGIN_PATH = `${APP_BASE}login`;" in FRONTEND
    assert "window.location.href = LOGIN_PATH" in FRONTEND


def test_login_page_uses_embedded_api_base():
    assert "const res = await fetch(`${API_BASE}/auth/login`," in FRONTEND
    assert "if (localStorage.getItem('agent_zs_token')) window.location.href = APP_BASE" in FRONTEND


def test_router_inline_frontends_do_not_use_generic_token_storage_key():
    forbidden_patterns = [
        "localStorage.getItem('token')",
        'localStorage.getItem("token")',
        "localStorage.setItem('token'",
        'localStorage.setItem("token"',
        "localStorage.removeItem('token')",
        'localStorage.removeItem("token")',
    ]
    for pattern in forbidden_patterns:
        assert pattern not in ROUTER_JS_SOURCES


def test_embedded_mode_hides_agent_user_controls():
    assert "window.self !== window.top" in FRONTEND
    assert "embedded-mode" in FRONTEND
    assert ".embedded-mode #userNameDisplay" in FRONTEND
    assert ".embedded-mode #logoutBtn" in FRONTEND