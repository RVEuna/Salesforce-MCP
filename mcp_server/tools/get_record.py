"""Get record tool — fetch a single Salesforce record by ID."""

from mcp.server.fastmcp import Context, FastMCP

from mcp_server.salesforce.auth import get_salesforce_client


def register_get_record_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_record(
        sobject_name: str,
        record_id: str,
        ctx: Context,
        fields: list[str] | None = None,
    ) -> dict:
        """Fetch a single Salesforce record by its ID.

        Args:
            sobject_name: API name of the sobject (e.g. "Account").
            record_id: The 15- or 18-character Salesforce record ID.
            fields: Optional list of field API names to retrieve.
                    If omitted, Salesforce returns all fields the user can see.

        Returns:
            Record fields the user has field-level security access to.
        """
        client = get_salesforce_client(ctx)
        return await client.get_record(sobject_name, record_id, fields)
