"""Get user info tool — retrieve the authenticated user's Salesforce profile."""

from mcp.server.fastmcp import Context, FastMCP

from mcp_server.salesforce.auth import get_salesforce_client


def register_get_user_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_user_info(ctx: Context) -> dict:
        """Get the currently authenticated Salesforce user's information.

        Returns:
            User details including id, name, email, profile, and username.
        """
        client = get_salesforce_client(ctx)
        return await client.get_user_info()
