"""SOQL query tool — execute arbitrary SOQL against the user's Salesforce org."""

from mcp.server.fastmcp import Context, FastMCP

from mcp_server.salesforce.auth import get_salesforce_client


def register_soql_query_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    async def soql_query(query: str, ctx: Context) -> dict:
        """Execute a SOQL query against Salesforce.

        Args:
            query: A valid SOQL query string (e.g. "SELECT Id, Name FROM Account LIMIT 10").

        Returns:
            records array, totalSize, and done flag from Salesforce.
            If the user lacks permission for an object or field, the
            Salesforce error is returned as-is.
        """
        client = get_salesforce_client(ctx)
        return await client.query(query)
