"""Describe sobject tool — get field/relationship metadata for a single object."""

from mcp.server.fastmcp import Context, FastMCP

from mcp_server.salesforce.auth import get_salesforce_client


def register_describe_sobject_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    async def describe_sobject(sobject_name: str, ctx: Context) -> dict:
        """Describe a Salesforce object — fields, relationships, record type info.

        Args:
            sobject_name: API name of the sobject (e.g. "Account", "Contact", "Opportunity").

        Returns:
            Full describe result including fields, childRelationships,
            and recordTypeInfos. Salesforce returns 404 if the user's
            profile lacks access to this object.
        """
        client = get_salesforce_client(ctx)
        return await client.describe_sobject(sobject_name)
