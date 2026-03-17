"""FastMCP server for AgentCore deployment.

This module implements the MCP server using FastMCP with stateless HTTP transport,
designed for deployment to AWS Bedrock AgentCore.

Key characteristics:
- Stateless mode for horizontal scaling
- No in-memory caching (use external cache if needed)
- Lazy initialization of OpenSearch connection
- Structured JSON logging for CloudWatch

Usage:
    # Local development
    uv run python -m mcp_server.server

    # Or via the entry point
    uv run mcp-server
"""

import logging
import sys
import threading
import time
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mcp_server.config import mcp_settings, opensearch_settings
from mcp_server.store import OpenSearchStore

# Configure logging
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

# Create FastMCP server with stateless HTTP mode for AgentCore
#
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
    json_response=True,  # Recommended for AgentCore
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)

# =============================================================================
# LAZY-INITIALIZED COMPONENTS
# =============================================================================

_store_lock = threading.Lock()
_store: OpenSearchStore | None = None


def _get_store() -> OpenSearchStore:
    """Get or create OpenSearchStore instance (thread-safe lazy initialization)."""
    global _store

    if _store is not None:
        return _store

    with _store_lock:
        if _store is None:
            logger.info("Initializing OpenSearch store...")
            logger.info(f"Endpoint: {opensearch_settings.endpoint}")
            logger.info(f"Index: {opensearch_settings.index_name}")
            logger.info(f"Auth mode: {opensearch_settings.auth_mode}")
            _store = OpenSearchStore()
            logger.info("OpenSearch store initialized")

    return _store


# =============================================================================
# TOOL EXECUTION WRAPPER
# =============================================================================


def _execute_tool(tool_name: str, arguments: dict[str, Any], tool_fn) -> dict:
    """Execute a tool with timing and error handling.

    Args:
        tool_name: Name of the tool for logging
        arguments: Arguments passed to the tool
        tool_fn: Function to execute

    Returns:
        Tool result dictionary
    """
    start_time = time.time()
    try:
        result = tool_fn()
        execution_time_ms = int((time.time() - start_time) * 1000)

        # Log successful execution
        logger.info(f"Tool executed: {tool_name} | args={arguments} | time_ms={execution_time_ms}")
        return result

    except Exception as e:
        execution_time_ms = int((time.time() - start_time) * 1000)
        logger.error(
            f"Tool failed: {tool_name} | "
            f"args={arguments} | "
            f"time_ms={execution_time_ms} | "
            f"error={str(e)}"
        )
        return {"error": f"Failed to execute {tool_name}: {str(e)}"}


# =============================================================================
# MCP TOOLS
# =============================================================================

# Import and register tools (must be after mcp is defined)
from mcp_server.tools import register_tools  # noqa: E402

register_tools(mcp, _get_store, _execute_tool)


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
    logger.info(f"OpenSearch endpoint: {opensearch_settings.endpoint}")
    logger.info(f"OpenSearch auth: {opensearch_settings.auth_mode}")
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
