"""Unit tests for mcp_server/server.py.

Covers the RequireBearerToken middleware, the /health endpoint,
and the _load_aws_secrets() function.
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures — lightweight app for middleware / health testing
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """Return the composite Starlette app from server.py.

    Patches are applied to avoid triggering module-level AWS secrets loading.
    """
    with (
        patch.dict("os.environ", {"AWS_LAMBDA_FUNCTION_NAME": ""}, clear=False),
        patch("mcp_server.server.mcp_settings") as mock_mcp,
        patch("mcp_server.server.salesforce_settings") as mock_sf,
    ):
        mock_mcp.server_name = "test-server"
        mock_mcp.host = "0.0.0.0"
        mock_mcp.port = 8000
        mock_mcp.path = "/mcp"
        mock_mcp.stateless = True
        mock_mcp.log_level = "INFO"
        mock_mcp.log_format = "text"
        mock_mcp.base_url = "http://localhost:8000"
        mock_mcp.jwt_secret = "test-secret-key-for-fernet-1234"
        mock_mcp.auth_code_ttl = 300
        mock_mcp.secret_provider = "local"

        mock_sf.access_token_ttl = 7200
        mock_sf.instance_url = "https://test.salesforce.com"

        from mcp_server.server import app as starlette_app
        yield starlette_app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# /health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_returns_200_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "server" in body


# ---------------------------------------------------------------------------
# RequireBearerToken middleware
# ---------------------------------------------------------------------------


class TestRequireBearerToken:
    """Tests for the ASGI middleware that guards the MCP endpoint."""

    def test_missing_bearer_returns_401(self, client):
        resp = client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"] == "unauthorized"
        assert "Bearer token required" in body["error_description"]

    def test_non_bearer_auth_returns_401(self, client):
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1},
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 401

    @patch("mcp_server.server.salesforce_settings")
    def test_expired_compound_token_returns_401(self, mock_sf, client):
        mock_sf.access_token_ttl = 7200

        from mcp_server.salesforce.auth import _get_fernet
        payload = {
            "access_token": "sf_tok",
            "refresh_token": "sf_ref",
            "instance_url": "https://sf.com",
            "iat": int(time.time()) - 99999,
        }
        expired_token = _get_fernet().encrypt(json.dumps(payload).encode()).decode()

        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1},
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["error_description"].lower()

    def test_raw_token_passes_through(self, client):
        """A raw (non-compound) Bearer token should pass the middleware.

        The actual MCP request will likely fail downstream but the middleware
        should NOT reject it — this enables local dev with raw SF tokens.
        """
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1},
            headers={"Authorization": "Bearer some_raw_sf_token"},
        )
        # Not 401 — the middleware let it through (downstream may error differently)
        assert resp.status_code != 401

    def test_401_includes_resource_metadata_header(self, client):
        resp = client.post("/mcp", json={})
        assert resp.status_code == 401
        assert b"resource_metadata" in b"".join(
            v for pair in resp.headers.raw for v in pair
        ) or "resource_metadata" in str(resp.headers)


# ---------------------------------------------------------------------------
# _load_aws_secrets
# ---------------------------------------------------------------------------


class TestLoadAwsSecrets:
    @patch("mcp_server.server.salesforce_settings")
    @patch("mcp_server.server.mcp_settings")
    def test_populates_settings_from_secret(self, mock_mcp, mock_sf):
        mock_mcp.aws_secret_name = "mcp/test/api-keys"
        mock_mcp.aws_secret_region = "us-east-2"
        mock_sf.instance_url = ""

        secret_data = {
            "SALESFORCE_INSTANCE_URL": "https://loaded.salesforce.com",
            "SALESFORCE_LOGIN_URL": "https://test.salesforce.com",
            "SALESFORCE_CLIENT_ID": "loaded_cid",
            "SALESFORCE_CLIENT_SECRET": "loaded_csecret",
            "SALESFORCE_API_VERSION": "v62.0",
            "SALESFORCE_ACCESS_TOKEN_TTL": "3600",
            "MCP_JWT_SECRET": "loaded_jwt",
            "MCP_BASE_URL": "https://loaded.lambda-url.on.aws/",
        }

        mock_boto_client = MagicMock()
        mock_boto_client.get_secret_value.return_value = {
            "SecretString": json.dumps(secret_data),
        }

        with patch("boto3.client", return_value=mock_boto_client):
            from mcp_server.server import _load_aws_secrets
            _load_aws_secrets()

        assert mock_sf.instance_url == "https://loaded.salesforce.com"
        assert mock_sf.login_url == "https://test.salesforce.com"
        assert mock_sf.client_id == "loaded_cid"
        assert mock_mcp.jwt_secret == "loaded_jwt"
        assert mock_mcp.base_url == "https://loaded.lambda-url.on.aws/"

    @patch("mcp_server.server.salesforce_settings")
    @patch("mcp_server.server.mcp_settings")
    def test_client_error_raises_runtime_error(self, mock_mcp, mock_sf):
        mock_mcp.aws_secret_name = "mcp/test/api-keys"
        mock_mcp.aws_secret_region = "us-east-2"

        import botocore.exceptions
        mock_boto_client = MagicMock()
        mock_boto_client.get_secret_value.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Secret not found"}},
            "GetSecretValue",
        )

        with patch("boto3.client", return_value=mock_boto_client):
            from mcp_server.server import _load_aws_secrets
            with pytest.raises(RuntimeError, match="Could not load required secrets"):
                _load_aws_secrets()

    @patch("mcp_server.server.salesforce_settings")
    @patch("mcp_server.server.mcp_settings")
    def test_invalid_json_raises_runtime_error(self, mock_mcp, mock_sf):
        mock_mcp.aws_secret_name = "mcp/test/api-keys"
        mock_mcp.aws_secret_region = "us-east-2"

        mock_boto_client = MagicMock()
        mock_boto_client.get_secret_value.return_value = {
            "SecretString": "not-valid-json{{{",
        }

        with patch("boto3.client", return_value=mock_boto_client):
            from mcp_server.server import _load_aws_secrets
            with pytest.raises(RuntimeError, match="not valid JSON"):
                _load_aws_secrets()

    @patch("mcp_server.server.salesforce_settings")
    @patch("mcp_server.server.mcp_settings")
    def test_missing_instance_url_raises(self, mock_mcp, mock_sf):
        mock_mcp.aws_secret_name = "mcp/test/api-keys"
        mock_mcp.aws_secret_region = "us-east-2"
        mock_sf.instance_url = ""

        mock_boto_client = MagicMock()
        mock_boto_client.get_secret_value.return_value = {
            "SecretString": json.dumps({"MCP_JWT_SECRET": "s"}),
        }

        with patch("boto3.client", return_value=mock_boto_client):
            from mcp_server.server import _load_aws_secrets
            with pytest.raises(RuntimeError, match="SALESFORCE_INSTANCE_URL not found"):
                _load_aws_secrets()

    @patch("mcp_server.server.salesforce_settings")
    @patch("mcp_server.server.mcp_settings")
    def test_partial_secrets_only_sets_present_keys(self, mock_mcp, mock_sf):
        mock_mcp.aws_secret_name = "mcp/test/api-keys"
        mock_mcp.aws_secret_region = "us-east-2"
        mock_sf.instance_url = "https://pre-existing.salesforce.com"

        mock_boto_client = MagicMock()
        mock_boto_client.get_secret_value.return_value = {
            "SecretString": json.dumps({
                "SALESFORCE_API_VERSION": "v61.0",
            }),
        }

        with patch("boto3.client", return_value=mock_boto_client):
            from mcp_server.server import _load_aws_secrets
            _load_aws_secrets()

        assert mock_sf.instance_url == "https://pre-existing.salesforce.com"
