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
from contextlib import asynccontextmanager

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_server.config import mcp_settings, salesforce_settings
from mcp_server.oauth.routes import oauth_routes

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
    """ASGI middleware that returns 401 if no Authorization: Bearer header is present.

    This triggers mcp-remote / Claude.ai to start the OAuth flow instead of
    connecting unauthenticated.
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
            base = mcp_settings.base_url.rstrip("/")
            body = json.dumps({"error": "unauthorized", "error_description": "Bearer token required"}).encode()
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
            return

        await self.app(scope, receive, send)


# =============================================================================
# COMPOSITE STARLETTE APP (OAuth routes + FastMCP)
# =============================================================================

mcp_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app):
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
