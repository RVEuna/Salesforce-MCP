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

import logging
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mcp_server.config import mcp_settings, salesforce_settings

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
# ENTRY POINTS
# =============================================================================


def run_server():
    """Run the FastMCP server."""
    logger.info("=" * 60)
    logger.info(f"Starting {mcp_settings.server_name} v{mcp_settings.server_version}")
    logger.info("=" * 60)
    logger.info(f"Host: {mcp_settings.host}")
    logger.info(f"Port: {mcp_settings.port}")
    logger.info(f"Path: {mcp_settings.path}")
    logger.info(f"Stateless: {mcp_settings.stateless}")
    logger.info(f"Salesforce instance: {salesforce_settings.instance_url}")
    logger.info(f"Salesforce API version: {salesforce_settings.api_version}")
    logger.info("=" * 60)

    try:
        mcp.run(transport="streamable-http")
    except Exception as e:
        logger.exception(f"Server failed to start: {e}")
        raise


def main():
    """Main entry point."""
    run_server()


if __name__ == "__main__":
    main()
