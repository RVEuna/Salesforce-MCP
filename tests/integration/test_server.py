"""Integration tests for Salesforce MCP server.

These tests require a valid Salesforce access token.
Run with: SALESFORCE_ACCESS_TOKEN=<token> make test-int
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("SALESFORCE_ACCESS_TOKEN"),
    reason="Integration tests require SALESFORCE_ACCESS_TOKEN env var",
)


class TestSalesforceIntegration:
    """Integration tests against a real Salesforce org."""

    @pytest.fixture
    def client(self):
        from mcp_server.config import salesforce_settings
        from mcp_server.salesforce.client import SalesforceClient

        return SalesforceClient(
            access_token=os.environ["SALESFORCE_ACCESS_TOKEN"],
            instance_url=salesforce_settings.instance_url,
            api_version=salesforce_settings.api_version,
        )

    @pytest.mark.asyncio
    async def test_get_user_info(self, client):
        """Test that we can fetch the authenticated user's info."""
        result = await client.get_user_info()
        assert "id" in result
        assert "name" in result

    @pytest.mark.asyncio
    async def test_describe_global(self, client):
        """Test that we can list available sobjects."""
        result = await client.describe_global()
        assert "sobjects" in result
        assert len(result["sobjects"]) > 0

    @pytest.mark.asyncio
    async def test_soql_query(self, client):
        """Test that a basic SOQL query works."""
        result = await client.query("SELECT Id, Name FROM Account LIMIT 1")
        assert "totalSize" in result
        assert "records" in result
        assert result["done"] is True


class TestMCPServerIntegration:
    """Integration tests for the full MCP server."""

    pass
