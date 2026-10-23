"""
Unit tests for the MCP server helpers (mcp_server/_helpers.py).

Tests the helpers directly via the project venv, without starting the MCP server; the
mcp_venv is NOT used here. Since 2026-10-23 the server has one tool, submit_research_answer.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# SEC-5 (a)+(b): Bearer token middleware (constant-time, websocket rejection)
# ---------------------------------------------------------------------------

class TestBearerTokenMiddleware:
    def _call(self, scope_type: str, auth_header=None, token: str = "secret"):
        import asyncio
        from mcp_server._helpers import BearerTokenMiddleware

        sent = []
        called = {}

        async def app(scope, receive, send):
            called["app"] = True

        async def receive():
            return {"type": "websocket.connect"}

        async def send(msg):
            sent.append(msg)

        headers = []
        if auth_header is not None:
            headers.append((b"authorization", auth_header))
        scope = {"type": scope_type, "headers": headers}
        asyncio.run(BearerTokenMiddleware(app, token)(scope, receive, send))
        return sent, called

    def test_http_without_token_rejected(self):
        sent, called = self._call("http")
        assert sent[0]["status"] == 401
        assert "app" not in called

    def test_http_with_wrong_token_rejected(self):
        sent, called = self._call("http", auth_header=b"Bearer wrong")
        assert sent[0]["status"] == 401
        assert "app" not in called

    def test_http_with_correct_token_passes(self):
        sent, called = self._call("http", auth_header=b"Bearer secret")
        assert called.get("app") is True
        assert sent == []

    def test_websocket_scope_rejected(self):
        sent, called = self._call("websocket", auth_header=b"Bearer secret")
        assert "app" not in called
        assert any(m.get("type") == "websocket.close" for m in sent)

    def test_lifespan_scope_passes_through(self):
        sent, called = self._call("lifespan")
        assert called.get("app") is True


# ---------------------------------------------------------------------------
# SEC-5 (c): submit_research_answer input validation helper
# ---------------------------------------------------------------------------

class TestValidateAnswerInput:
    def test_empty_answer_rejected(self):
        from mcp_server._helpers import validate_answer_input
        assert "empty" in validate_answer_input("   ", None)

    def test_oversize_answer_rejected(self):
        from mcp_server._helpers import validate_answer_input
        assert "100 KB" in validate_answer_input("x" * 100_001, None)

    def test_overlong_ticker_rejected(self):
        from mcp_server._helpers import validate_answer_input
        assert "ticker" in validate_answer_input("ok", "A" * 21)

    def test_valid_input_passes(self):
        from mcp_server._helpers import validate_answer_input
        assert validate_answer_input("# Analyse\nAlles gut.", "AAPL") is None
