"""MCP Tools module.

This module contains all Salesforce tool implementations and the registration function.
"""

from mcp.server.fastmcp import FastMCP

from mcp_server.tools.describe_global import register_describe_global_tool
from mcp_server.tools.describe_sobject import register_describe_sobject_tool
from mcp_server.tools.get_record import register_get_record_tool
from mcp_server.tools.get_related_records import register_get_related_records_tool
from mcp_server.tools.get_user_info import register_get_user_info_tool
from mcp_server.tools.soql_query import register_soql_query_tool
from mcp_server.tools.sosl_search import register_sosl_search_tool


def register_tools(mcp: FastMCP) -> None:
    """Register all Salesforce tools with the MCP server."""
    register_soql_query_tool(mcp)
    register_sosl_search_tool(mcp)
    register_describe_global_tool(mcp)
    register_describe_sobject_tool(mcp)
    register_get_record_tool(mcp)
    register_get_related_records_tool(mcp)
    register_get_user_info_tool(mcp)
