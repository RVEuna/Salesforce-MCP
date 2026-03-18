"""Describe global tool — list all sobjects the user has access to."""

from mcp.server.fastmcp import Context, FastMCP

from mcp_server.salesforce.auth import get_salesforce_client


def register_describe_global_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    async def describe_global(ctx: Context) -> dict:
        """List all Salesforce objects (sobjects) the authenticated user can access.

        Salesforce automatically filters the list based on the user's profile.

        Returns:
            List of sobjects with metadata (name, label, queryable, etc.).
        """
        client = get_salesforce_client(ctx)
        return await client.describe_global()
