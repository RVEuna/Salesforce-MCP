"""Unit tests for mcp_server/oauth/routes.py.

Uses Starlette's TestClient to exercise every OAuth endpoint without
starting a real server. All Salesforce HTTP calls are mocked.
"""

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route

from mcp_server.oauth.routes import (
    oauth_authorize,
    oauth_callback,
    oauth_metadata,
    oauth_protected_resource,
    oauth_register,
    oauth_token,
)


@pytest.fixture
def oauth_app():
    """Minimal Starlette app with just OAuth routes for isolated testing."""
    return Starlette(routes=[
        Route("/.well-known/oauth-protected-resource", oauth_protected_resource),
        Route("/.well-known/oauth-authorization-server", oauth_metadata),
        Route("/.well-known/openid-configuration", oauth_metadata),
        Route("/oauth/register", oauth_register, methods=["POST"]),
        Route("/oauth/authorize", oauth_authorize),
        Route("/oauth/callback", oauth_callback),
        Route("/oauth/token", oauth_token, methods=["POST"]),
    ])


@pytest.fixture
def client(oauth_app):
    return TestClient(oauth_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Discovery endpoints
# ---------------------------------------------------------------------------


class TestProtectedResource:
    @patch("mcp_server.oauth.routes.mcp_settings")
    def test_returns_resource_and_auth_server(self, mock_mcp, client):
        mock_mcp.base_url = "https://my-lambda.lambda-url.us-east-2.on.aws/"

        resp = client.get("/.well-known/oauth-protected-resource")
        assert resp.status_code == 200
        body = resp.json()
        assert body["resource"] == "https://my-lambda.lambda-url.us-east-2.on.aws"
        assert body["authorization_servers"] == ["https://my-lambda.lambda-url.us-east-2.on.aws"]


class TestOAuthMetadata:
    @patch("mcp_server.oauth.routes.mcp_settings")
    def test_returns_rfc8414_fields(self, mock_mcp, client):
        mock_mcp.base_url = "https://example.com"

        resp = client.get("/.well-known/oauth-authorization-server")
        assert resp.status_code == 200
        body = resp.json()

        assert body["issuer"] == "https://example.com"
        assert body["authorization_endpoint"] == "https://example.com/oauth/authorize"
        assert body["token_endpoint"] == "https://example.com/oauth/token"
        assert body["registration_endpoint"] == "https://example.com/oauth/register"
        assert "code" in body["response_types_supported"]
        assert "authorization_code" in body["grant_types_supported"]
        assert "refresh_token" in body["grant_types_supported"]
        assert "S256" in body["code_challenge_methods_supported"]

    @patch("mcp_server.oauth.routes.mcp_settings")
    def test_openid_configuration_alias(self, mock_mcp, client):
        mock_mcp.base_url = "https://example.com"

        resp = client.get("/.well-known/openid-configuration")
        assert resp.status_code == 200
        assert resp.json()["issuer"] == "https://example.com"


# ---------------------------------------------------------------------------
# Dynamic client registration
# ---------------------------------------------------------------------------


class TestOAuthRegister:
    def test_register_returns_201_with_client_id(self, client):
        resp = client.post("/oauth/register", json={
            "client_name": "my-mcp-client",
            "redirect_uris": ["https://claude.ai/callback"],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
        })

        assert resp.status_code == 201
        body = resp.json()
        assert "client_id" in body
        assert body["client_name"] == "my-mcp-client"
        assert body["redirect_uris"] == ["https://claude.ai/callback"]
        assert body["token_endpoint_auth_method"] == "none"

    def test_register_uses_defaults(self, client):
        resp = client.post("/oauth/register", json={})
        assert resp.status_code == 201
        body = resp.json()
        assert body["client_name"] == "mcp-client"
        assert body["grant_types"] == ["authorization_code"]


# ---------------------------------------------------------------------------
# Authorize redirect
# ---------------------------------------------------------------------------


class TestOAuthAuthorize:
    @patch("mcp_server.oauth.routes.mcp_settings")
    @patch("mcp_server.salesforce.auth.salesforce_settings")
    def test_redirects_to_salesforce(self, mock_sf_auth, mock_mcp, client):
        mock_mcp.base_url = "https://lambda.example.com"
        mock_sf_auth.login_url = "https://test.salesforce.com"
        mock_sf_auth.client_id = "test_client_id"

        resp = client.get(
            "/oauth/authorize",
            params={
                "redirect_uri": "https://claude.ai/callback",
                "state": "client_state_abc",
                "code_challenge": "sha256hash",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert location.startswith("https://test.salesforce.com/services/oauth2/authorize")
        assert "client_id=test_client_id" in location
        assert "redirect_uri=" in location
        assert "response_type=code" in location

    def test_missing_redirect_uri_returns_400(self, client):
        resp = client.get("/oauth/authorize")
        assert resp.status_code == 400
        assert "redirect_uri" in resp.json()["error"]


# ---------------------------------------------------------------------------
# Callback (Salesforce redirects back here)
# ---------------------------------------------------------------------------


class TestOAuthCallback:
    @patch("mcp_server.oauth.routes.exchange_code_for_token", new_callable=AsyncMock)
    @patch("mcp_server.oauth.routes.mcp_settings")
    def test_success_redirects_to_client(self, mock_mcp, mock_exchange, client):
        mock_mcp.base_url = "https://lambda.example.com"
        mock_exchange.return_value = {
            "access_token": "sf_tok",
            "refresh_token": "sf_ref",
            "instance_url": "https://sf.com",
        }

        from mcp_server.salesforce.auth import encode_oauth_state
        state = encode_oauth_state(
            redirect_uri="https://claude.ai/callback",
            client_state="cs_abc",
        )

        resp = client.get(
            "/oauth/callback",
            params={"code": "sf_auth_code", "state": state},
            follow_redirects=False,
        )

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert location.startswith("https://claude.ai/callback?")
        assert "code=" in location
        assert "state=cs_abc" in location

    def test_missing_code_returns_400(self, client):
        resp = client.get("/oauth/callback", params={"state": "abc"})
        assert resp.status_code == 400

    def test_missing_state_returns_400(self, client):
        resp = client.get("/oauth/callback", params={"code": "abc"})
        assert resp.status_code == 400

    def test_invalid_state_returns_400(self, client):
        resp = client.get("/oauth/callback", params={"code": "abc", "state": "!!!bad!!!"})
        assert resp.status_code == 400

    @patch("mcp_server.oauth.routes.exchange_code_for_token", new_callable=AsyncMock)
    @patch("mcp_server.oauth.routes.mcp_settings")
    def test_salesforce_exchange_failure_returns_502(self, mock_mcp, mock_exchange, client):
        mock_mcp.base_url = "https://lambda.example.com"
        mock_exchange.side_effect = ValueError("Salesforce token exchange failed")

        from mcp_server.salesforce.auth import encode_oauth_state
        state = encode_oauth_state(redirect_uri="https://claude.ai/callback")

        resp = client.get(
            "/oauth/callback",
            params={"code": "sf_code", "state": state},
            follow_redirects=False,
        )
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------


class TestOAuthToken:
    @patch("mcp_server.oauth.routes.redeem_auth_code")
    @patch("mcp_server.oauth.routes.issue_compound_token")
    @patch("mcp_server.oauth.routes.salesforce_settings")
    def test_authorization_code_grant(self, mock_sf, mock_issue, mock_redeem, client):
        mock_sf.access_token_ttl = 7200
        mock_redeem.return_value = {
            "access_token": "sf_tok",
            "refresh_token": "sf_ref",
            "instance_url": "https://sf.com",
        }
        mock_issue.return_value = "compound_bearer_token"

        resp = client.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": "encrypted_auth_code",
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "compound_bearer_token"
        assert body["refresh_token"] == "sf_ref"
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == 7200

    def test_missing_code_returns_400(self, client):
        resp = client.post("/oauth/token", data={"grant_type": "authorization_code"})
        assert resp.status_code == 400
        assert "code" in resp.json()["error"]

    @patch("mcp_server.oauth.routes.redeem_auth_code")
    def test_invalid_code_returns_400(self, mock_redeem, client):
        mock_redeem.side_effect = ValueError("Invalid auth code")
        resp = client.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": "bad-code",
        })
        assert resp.status_code == 400

    @patch("mcp_server.oauth.routes.refresh_salesforce_token", new_callable=AsyncMock)
    @patch("mcp_server.oauth.routes.issue_compound_token")
    @patch("mcp_server.oauth.routes.salesforce_settings")
    def test_refresh_token_grant(self, mock_sf, mock_issue, mock_refresh, client):
        mock_sf.access_token_ttl = 7200
        mock_refresh.return_value = {
            "access_token": "new_sf_tok",
            "refresh_token": "new_sf_ref",
            "instance_url": "https://sf.com",
        }
        mock_issue.return_value = "new_compound_token"

        resp = client.post("/oauth/token", data={
            "grant_type": "refresh_token",
            "refresh_token": "old_refresh_tok",
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "new_compound_token"
        assert body["refresh_token"] == "new_sf_ref"

    def test_refresh_missing_token_returns_400(self, client):
        resp = client.post("/oauth/token", data={"grant_type": "refresh_token"})
        assert resp.status_code == 400
        assert "refresh_token" in resp.json()["error"]

    @patch("mcp_server.oauth.routes.refresh_salesforce_token", new_callable=AsyncMock)
    def test_refresh_invalid_token_returns_400(self, mock_refresh, client):
        mock_refresh.side_effect = ValueError("invalid or expired")

        resp = client.post("/oauth/token", data={
            "grant_type": "refresh_token",
            "refresh_token": "expired_tok",
        })
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_grant"
