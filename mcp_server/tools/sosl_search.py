"""SOSL search tool — full-text search across the user's Salesforce org."""

from mcp.server.fastmcp import Context, FastMCP

from mcp_server.salesforce.auth import get_salesforce_client


def register_sosl_search_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    async def sosl_search(query: str, ctx: Context) -> dict:
        """Execute a SOSL search against Salesforce.

        Args:
            query: A valid SOSL search string
                   (e.g. "FIND {Acme} IN ALL FIELDS RETURNING Account(Id, Name)").

        Returns:
            searchRecords array from Salesforce.
        """
        client = get_salesforce_client(ctx)
        return await client.search(query)
