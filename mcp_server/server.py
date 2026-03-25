"""FastMCP server for AgentCore deployment.

This module implements the MCP server using FastMCP with stateless HTTP transport,
designed for deployment to AWS Bedrock AgentCore.

Key characteristics:
- Stateless mode for horizontal scaling
- Per-user OAuth 2.0 — each request carries a Salesforce Bearer token
- All Salesforce RBAC enforced by Salesforce itself
- Structured JSON logging for CloudWatch

Usage:
    # Local development
    uv run python -m mcp_server.server

    # Or via the entry point
    uv run mcp-server
"""

import json
import logging
import sys
import time
from contextlib import asynccontextmanager

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_server.config import mcp_settings, salesforce_settings
from mcp_server.oauth.routes import oauth_routes


def _load_aws_secrets() -> None:
    """Load Salesforce and MCP credentials from AWS Secrets Manager.

    Called at server startup when MCP_SECRET_PROVIDER=aws. Mutates the
    module-level settings singletons so all subsequent request handlers
    see the correct values without a process restart.
    """
    import boto3
    import botocore.exceptions

    secret_name = mcp_settings.aws_secret_name
    region = mcp_settings.aws_secret_region
    logger.info(f"Loading secrets from AWS Secrets Manager: {secret_name} ({region})")

    try:
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response["SecretString"])
    except botocore.exceptions.ClientError as exc:
        logger.error(f"Failed to fetch secret {secret_name!r}: {exc}")
        raise RuntimeError(f"Could not load required secrets from AWS: {exc}") from exc
    except (KeyError, json.JSONDecodeError) as exc:
        logger.error(f"Secret {secret_name!r} has unexpected format: {exc}")
        raise RuntimeError(f"Secret {secret_name!r} is not valid JSON") from exc

    # Populate Salesforce settings
    if "SALESFORCE_INSTANCE_URL" in secret:
        salesforce_settings.instance_url = secret["SALESFORCE_INSTANCE_URL"]
    if "SALESFORCE_LOGIN_URL" in secret:
        salesforce_settings.login_url = secret["SALESFORCE_LOGIN_URL"]
    if "SALESFORCE_CLIENT_ID" in secret:
        salesforce_settings.client_id = secret["SALESFORCE_CLIENT_ID"]
    if "SALESFORCE_CLIENT_SECRET" in secret:
        salesforce_settings.client_secret = secret["SALESFORCE_CLIENT_SECRET"]
    if "SALESFORCE_API_VERSION" in secret:
        salesforce_settings.api_version = secret["SALESFORCE_API_VERSION"]
    if "SALESFORCE_ACCESS_TOKEN_TTL" in secret:
        salesforce_settings.access_token_ttl = int(secret["SALESFORCE_ACCESS_TOKEN_TTL"])

    # Optionally override MCP settings stored alongside Salesforce creds
    if "MCP_JWT_SECRET" in secret:
        mcp_settings.jwt_secret = secret["MCP_JWT_SECRET"]
    if "MCP_BASE_URL" in secret:
        mcp_settings.base_url = secret["MCP_BASE_URL"]

    if not salesforce_settings.instance_url:
        raise RuntimeError(
            "SALESFORCE_INSTANCE_URL not found in secret or environment. "
            f"Add it to the Secrets Manager secret: {secret_name}"
        )

    logger.info(f"Secrets loaded. Salesforce instance: {salesforce_settings.instance_url}")

log_format = (
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    if mcp_settings.log_format == "text"
    else '{"time": "%(asctime)s", "name": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}'
)

logging.basicConfig(
    level=getattr(logging, mcp_settings.log_level.upper()),
    format=log_format,
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger(__name__)

# =============================================================================
# FASTMCP SERVER INITIALIZATION
# =============================================================================

# IMPORTANT: DNS rebinding protection must be disabled for AgentCore deployments.
# AgentCore's internal routing uses internal hostnames that would be rejected
# by the default Host header validation. Since we're running behind AWS IAM
# authentication, this is safe.
mcp = FastMCP(
    name=mcp_settings.server_name,
    host=mcp_settings.host,
    port=mcp_settings.port,
    streamable_http_path=mcp_settings.path,
    stateless_http=mcp_settings.stateless,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)

# =============================================================================
# MCP TOOLS
# =============================================================================

from mcp_server.tools import register_tools  # noqa: E402

register_tools(mcp)


# =============================================================================
# AUTH-REQUIRED MIDDLEWARE (wraps the MCP ASGI app)
# =============================================================================


class RequireBearerToken:
    """ASGI middleware that enforces Bearer token presence and expiry.

    Returns 401 in two cases, both triggering Claude's OAuth/refresh flow:
    1. No Authorization: Bearer header present.
    2. Compound token is present but expired (iat + access_token_ttl < now).

    Raw (non-compound) tokens are passed through for local dev compatibility.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()

        if not auth.lower().startswith("bearer "):
            await self._send_401(send, "Bearer token required")
            return

        bearer_token = auth[7:].strip()

        try:
            from mcp_server.salesforce.auth import decode_compound_token
            payload = decode_compound_token(bearer_token)
            iat = payload.get("iat", 0)
            if time.time() > iat + salesforce_settings.access_token_ttl:
                logger.info("Compound token expired, returning 401 to trigger refresh")
                await self._send_401(send, "Token expired")
                return
        except ValueError:
            pass

        await self.app(scope, receive, send)

    async def _send_401(self, send: Send, description: str) -> None:
        base = mcp_settings.base_url.rstrip("/")
        body = json.dumps({"error": "unauthorized", "error_description": description}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                [b"content-type", b"application/json"],
                [b"www-authenticate", b"Bearer"],
                [b"content-length", str(len(body)).encode()],
                [b"resource_metadata", f"{base}/.well-known/oauth-protected-resource".encode()],
            ],
        })
        await send({"type": "http.response.body", "body": body})


# =============================================================================
# COMPOSITE STARLETTE APP (OAuth routes + FastMCP)
# =============================================================================

mcp_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app):
    if mcp_settings.secret_provider == "aws":
        _load_aws_secrets()
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        *oauth_routes,
        Mount("/", app=RequireBearerToken(mcp_app)),
    ],
    lifespan=lifespan,
)

# =============================================================================
# ENTRY POINTS
# =============================================================================


def run_server():
    """Run the composite server (OAuth + MCP) via uvicorn."""
    logger.info("=" * 60)
    logger.info(f"Starting {mcp_settings.server_name} v{mcp_settings.server_version}")
    logger.info("=" * 60)
    logger.info(f"Host: {mcp_settings.host}")
    logger.info(f"Port: {mcp_settings.port}")
    logger.info(f"MCP path: {mcp_settings.path}")
    logger.info(f"Stateless: {mcp_settings.stateless}")
    logger.info(f"Base URL: {mcp_settings.base_url}")
    logger.info(f"Salesforce instance: {salesforce_settings.instance_url}")
    logger.info(f"Salesforce API version: {salesforce_settings.api_version}")
    logger.info("=" * 60)

    try:
        uvicorn.run(
            app,
            host=mcp_settings.host,
            port=mcp_settings.port,
            log_level=mcp_settings.log_level.lower(),
        )
    except Exception as e:
        logger.exception(f"Server failed to start: {e}")
        raise


def main():
    """Main entry point."""
    run_server()


if __name__ == "__main__":
    main()
