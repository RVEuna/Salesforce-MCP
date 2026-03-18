"""Get related records tool — fetch child/related records for a parent record."""

from mcp.server.fastmcp import Context, FastMCP

from mcp_server.salesforce.auth import get_salesforce_client


def register_get_related_records_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_related_records(
        sobject_name: str,
        record_id: str,
        relationship_name: str,
        ctx: Context,
        fields: list[str] | None = None,
    ) -> dict:
        """Fetch related records for a given parent Salesforce record.

        Args:
            sobject_name: API name of the parent sobject (e.g. "Account").
            record_id: The 15- or 18-character Salesforce record ID of the parent.
            relationship_name: The relationship name (e.g. "Contacts", "Opportunities").
            fields: Optional list of field API names to retrieve on the related records.

        Returns:
            Related records array from Salesforce.
        """
        client = get_salesforce_client(ctx)
        return await client.get_related_records(sobject_name, record_id, relationship_name, fields)
