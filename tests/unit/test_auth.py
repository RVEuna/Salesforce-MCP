"""Unit tests for mcp_server/salesforce/auth.py.

Covers Fernet token helpers, OAuth state encoding/decoding,
Bearer extraction patterns, and Salesforce token exchange functions.
"""

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_server.salesforce.auth import (
    _parse_bearer,
    build_authorization_url,
    decode_compound_token,
    decode_oauth_state,
    encode_oauth_state,
    exchange_code_for_token,
    get_salesforce_client,
    issue_auth_code,
    issue_compound_token,
    redeem_auth_code,
    refresh_salesforce_token,
)


# ---------------------------------------------------------------------------
# Fernet compound token round-trip
# ---------------------------------------------------------------------------


class TestCompoundTokens:
    @patch("mcp_server.salesforce.auth.mcp_settings")
    def test_roundtrip(self, mock_mcp):
        mock_mcp.jwt_secret = "test-secret-key-for-fernet-123456"

        sf_response = {
            "access_token": "sf_tok_abc",
            "refresh_token": "sf_ref_xyz",
            "instance_url": "https://example.my.salesforce.com",
        }

        token = issue_compound_token(sf_response)
        assert isinstance(token, str)
        assert len(token) > 0

        payload = decode_compound_token(token)
        assert payload["access_token"] == "sf_tok_abc"
        assert payload["refresh_token"] == "sf_ref_xyz"
        assert payload["instance_url"] == "https://example.my.salesforce.com"
        assert "iat" in payload
        assert isinstance(payload["iat"], int)

    @patch("mcp_server.salesforce.auth.mcp_settings")
    def test_decode_with_wrong_secret_raises(self, mock_mcp):
        mock_mcp.jwt_secret = "correct-secret"
        token = issue_compound_token({"access_token": "tok", "instance_url": "https://sf.com"})

        mock_mcp.jwt_secret = "wrong-secret"
        with pytest.raises(ValueError, match="Invalid compound token"):
            decode_compound_token(token)

    @patch("mcp_server.salesforce.auth.mcp_settings")
    def test_decode_garbage_raises(self, mock_mcp):
        mock_mcp.jwt_secret = "any-secret"
        with pytest.raises(ValueError, match="Invalid compound token"):
            decode_compound_token("not-a-real-token")

    @patch("mcp_server.salesforce.auth.mcp_settings")
    @patch("mcp_server.salesforce.auth.salesforce_settings")
    def test_missing_refresh_token_defaults_empty(self, mock_sf, mock_mcp):
        mock_mcp.jwt_secret = "test-secret"
        mock_sf.instance_url = "https://fallback.salesforce.com"

        token = issue_compound_token({"access_token": "tok"})
        payload = decode_compound_token(token)
        assert payload["refresh_token"] == ""


# ---------------------------------------------------------------------------
# Auth code (time-limited encrypted code)
# ---------------------------------------------------------------------------


class TestAuthCode:
    @patch("mcp_server.salesforce.auth.mcp_settings")
    @patch("mcp_server.salesforce.auth.salesforce_settings")
    def test_issue_and_redeem(self, mock_sf, mock_mcp):
        mock_mcp.jwt_secret = "code-test-secret"
        mock_mcp.auth_code_ttl = 300
        mock_sf.instance_url = "https://example.my.salesforce.com"

        sf_response = {
            "access_token": "sf_access",
            "refresh_token": "sf_refresh",
            "instance_url": "https://example.my.salesforce.com",
        }

        code = issue_auth_code(sf_response)
        result = redeem_auth_code(code)

        assert result["access_token"] == "sf_access"
        assert result["refresh_token"] == "sf_refresh"
        assert result["instance_url"] == "https://example.my.salesforce.com"

    @patch("mcp_server.salesforce.auth.mcp_settings")
    @patch("mcp_server.salesforce.auth.salesforce_settings")
    def test_expired_code_raises(self, mock_sf, mock_mcp):
        mock_mcp.jwt_secret = "code-test-secret"
        mock_mcp.auth_code_ttl = -1  # already expired
        mock_sf.instance_url = "https://sf.com"

        code = issue_auth_code({"access_token": "tok", "instance_url": "https://sf.com"})

        with pytest.raises(ValueError, match="expired"):
            redeem_auth_code(code)

    @patch("mcp_server.salesforce.auth.mcp_settings")
    def test_invalid_code_raises(self, mock_mcp):
        mock_mcp.jwt_secret = "code-test-secret"

        with pytest.raises(ValueError, match="Invalid auth code"):
            redeem_auth_code("garbage-code")


# ---------------------------------------------------------------------------
# OAuth state (base64 encoded JSON)
# ---------------------------------------------------------------------------


class TestOAuthState:
    def test_roundtrip_full(self):
        state = encode_oauth_state(
            redirect_uri="https://claude.ai/callback",
            client_state="abc123",
            code_challenge="sha256challenge",
        )
        decoded = decode_oauth_state(state)

        assert decoded["redirect_uri"] == "https://claude.ai/callback"
        assert decoded["client_state"] == "abc123"
        assert decoded["code_challenge"] == "sha256challenge"

    def test_roundtrip_minimal(self):
        state = encode_oauth_state(redirect_uri="https://example.com/cb")
        decoded = decode_oauth_state(state)

        assert decoded["redirect_uri"] == "https://example.com/cb"
        assert "client_state" not in decoded

    def test_invalid_state_raises(self):
        with pytest.raises(ValueError, match="Invalid OAuth state"):
            decode_oauth_state("!!!not-base64!!!")


# ---------------------------------------------------------------------------
# Bearer token parsing
# ---------------------------------------------------------------------------


class TestParseBearerToken:
    def test_standard_bearer(self):
        assert _parse_bearer("Bearer abc123") == "abc123"

    def test_bearer_with_extra_spaces(self):
        assert _parse_bearer("Bearer   spaced_token  ") == "spaced_token"

    def test_bearer_colon_variant(self):
        assert _parse_bearer("Bearer:colon_token") == "colon_token"

    def test_case_insensitive(self):
        assert _parse_bearer("BEARER UPPER") == "UPPER"
        assert _parse_bearer("bearer lower") == "lower"

    def test_no_bearer_prefix(self):
        assert _parse_bearer("Basic abc123") is None

    def test_empty_string(self):
        assert _parse_bearer("") is None


# ---------------------------------------------------------------------------
# build_authorization_url
# ---------------------------------------------------------------------------


class TestBuildAuthorizationUrl:
    @patch("mcp_server.salesforce.auth.salesforce_settings")
    def test_builds_url_with_state(self, mock_sf):
        mock_sf.login_url = "https://test.salesforce.com"
        mock_sf.client_id = "my_client_id"

        url = build_authorization_url(
            redirect_uri="https://example.com/callback",
            state="packed_state_blob",
        )

        assert url.startswith("https://test.salesforce.com/services/oauth2/authorize?")
        assert "client_id=my_client_id" in url
        assert "redirect_uri=https" in url
        assert "state=packed_state_blob" in url
        assert "response_type=code" in url
        assert "scope=api+refresh_token" in url

    @patch("mcp_server.salesforce.auth.salesforce_settings")
    def test_builds_url_without_state(self, mock_sf):
        mock_sf.login_url = "https://login.salesforce.com"
        mock_sf.client_id = "cid"

        url = build_authorization_url(redirect_uri="https://cb.example.com")
        assert "state=" not in url


# ---------------------------------------------------------------------------
# get_salesforce_client
# ---------------------------------------------------------------------------


class TestGetSalesforceClient:
    @staticmethod
    def _make_ctx(auth_header: str) -> MagicMock:
        """Build a mock Context whose request_context.headers dict works
        with the multi-pattern extraction in _try_extract_from_context."""
        ctx = MagicMock()
        # Disable Pattern 1 (request_context.request) so Pattern 2 is used
        ctx.request_context.request = None
        ctx.request_context.headers = {"authorization": auth_header}
        return ctx

    @patch("mcp_server.salesforce.auth.mcp_settings")
    @patch("mcp_server.salesforce.auth.salesforce_settings")
    def test_with_compound_token(self, mock_sf, mock_mcp):
        mock_mcp.jwt_secret = "client-test-secret"
        mock_sf.instance_url = "https://fallback.salesforce.com"
        mock_sf.api_version = "v66.0"

        compound = issue_compound_token({
            "access_token": "real_sf_token",
            "instance_url": "https://actual.salesforce.com",
        })

        ctx = self._make_ctx(f"Bearer {compound}")
        client = get_salesforce_client(ctx)
        assert client._headers["Authorization"] == "Bearer real_sf_token"
        assert "actual.salesforce.com" in client._base_url

    @patch("mcp_server.salesforce.auth.salesforce_settings")
    def test_with_raw_token_fallback(self, mock_sf):
        mock_sf.instance_url = "https://my.salesforce.com"
        mock_sf.api_version = "v66.0"

        ctx = self._make_ctx("Bearer raw_sf_access_token")
        client = get_salesforce_client(ctx)
        assert client._headers["Authorization"] == "Bearer raw_sf_access_token"

    @patch("mcp_server.salesforce.auth.salesforce_settings")
    def test_env_fallback(self, mock_sf):
        mock_sf.access_token = "env_token"
        mock_sf.instance_url = "https://env.salesforce.com"
        mock_sf.api_version = "v66.0"

        ctx = MagicMock()
        ctx.request_context = None

        client = get_salesforce_client(ctx)
        assert client._headers["Authorization"] == "Bearer env_token"

    @patch("mcp_server.salesforce.auth.salesforce_settings")
    def test_no_token_raises(self, mock_sf):
        mock_sf.access_token = ""

        ctx = MagicMock()
        ctx.request_context = None

        with pytest.raises(ValueError, match="No Salesforce access token found"):
            get_salesforce_client(ctx)


# ---------------------------------------------------------------------------
# exchange_code_for_token (mocked HTTP)
# ---------------------------------------------------------------------------


class TestExchangeCodeForToken:
    @pytest.mark.asyncio
    @patch("mcp_server.salesforce.auth.salesforce_settings")
    async def test_success(self, mock_sf):
        mock_sf.login_url = "https://test.salesforce.com"
        mock_sf.client_id = "cid"
        mock_sf.client_secret = "csecret"
        mock_sf.auth_timeout = 10

        mock_response = httpx.Response(
            200,
            json={"access_token": "new_tok", "instance_url": "https://sf.com"},
        )

        with patch("mcp_server.salesforce.auth.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await exchange_code_for_token("sf_code", "https://cb.example.com")

        assert result["access_token"] == "new_tok"

    @pytest.mark.asyncio
    @patch("mcp_server.salesforce.auth.salesforce_settings")
    async def test_failure_raises(self, mock_sf):
        mock_sf.login_url = "https://test.salesforce.com"
        mock_sf.client_id = "cid"
        mock_sf.client_secret = "csecret"
        mock_sf.auth_timeout = 10

        mock_response = httpx.Response(400, text="invalid_grant")

        with patch("mcp_server.salesforce.auth.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(ValueError, match="token exchange failed"):
                await exchange_code_for_token("bad_code", "https://cb.example.com")


# ---------------------------------------------------------------------------
# refresh_salesforce_token (mocked HTTP)
# ---------------------------------------------------------------------------


class TestRefreshSalesforceToken:
    @pytest.mark.asyncio
    @patch("mcp_server.salesforce.auth.salesforce_settings")
    async def test_success(self, mock_sf):
        mock_sf.login_url = "https://test.salesforce.com"
        mock_sf.client_id = "cid"
        mock_sf.client_secret = "csecret"
        mock_sf.auth_timeout = 10

        mock_response = httpx.Response(
            200,
            json={"access_token": "refreshed_tok", "instance_url": "https://sf.com"},
        )

        with patch("mcp_server.salesforce.auth.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await refresh_salesforce_token("old_refresh_tok")

        assert result["access_token"] == "refreshed_tok"

    @pytest.mark.asyncio
    @patch("mcp_server.salesforce.auth.salesforce_settings")
    async def test_failure_raises(self, mock_sf):
        mock_sf.login_url = "https://test.salesforce.com"
        mock_sf.client_id = "cid"
        mock_sf.client_secret = "csecret"
        mock_sf.auth_timeout = 10

        mock_response = httpx.Response(400, text="expired refresh token")

        with patch("mcp_server.salesforce.auth.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(ValueError, match="token refresh failed"):
                await refresh_salesforce_token("bad_refresh_tok")
