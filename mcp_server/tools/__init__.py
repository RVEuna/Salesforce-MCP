"""MCP Tools module.

This module contains all tool implementations and the registration function.
"""

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from mcp_server.tools.batch_lookup import register_batch_lookup_tool
from mcp_server.tools.echo import register_echo_tool
from mcp_server.tools.lookup import register_lookup_tool
from mcp_server.tools.related_documents import register_related_documents_tool
from mcp_server.tools.search import register_search_tool


def register_tools(
    mcp: FastMCP,
    get_store: Callable,
    execute_tool: Callable,
) -> None:
    """Register all tools with the MCP server.

    Args:
        mcp: The FastMCP server instance
        get_store: Function to get the OpenSearchStore instance
        execute_tool: Wrapper function for tool execution with timing/logging
    """
    register_echo_tool(mcp, execute_tool)
    register_search_tool(mcp, get_store, execute_tool)
    register_lookup_tool(mcp, get_store, execute_tool)
    register_batch_lookup_tool(mcp, get_store, execute_tool)
    register_related_documents_tool(mcp, get_store, execute_tool)
