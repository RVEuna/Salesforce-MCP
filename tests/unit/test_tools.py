"""Unit tests for Salesforce MCP tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mcp_and_capture():
    """Create a mock MCP server and capture the registered tool function."""
    mock_mcp = MagicMock()
    captured = {}

    def capture_decorator():
        def decorator(func):
            captured["tool"] = func
            return func
        return decorator

    mock_mcp.tool = capture_decorator
    return mock_mcp, captured


class TestSoqlQueryTool:
    @pytest.mark.asyncio
    async def test_soql_query_calls_client(self, mock_salesforce_client, mock_context):
        mock_mcp, captured = _make_mcp_and_capture()

        with patch(
            "mcp_server.tools.soql_query.get_salesforce_client",
            return_value=mock_salesforce_client,
        ):
            from mcp_server.tools.soql_query import register_soql_query_tool

            register_soql_query_tool(mock_mcp)
            result = await captured["tool"]("SELECT Id FROM Account", ctx=mock_context)

        assert result["totalSize"] == 2
        assert len(result["records"]) == 2
        mock_salesforce_client.query.assert_awaited_once_with("SELECT Id FROM Account")


class TestSoslSearchTool:
    @pytest.mark.asyncio
    async def test_sosl_search_calls_client(self, mock_salesforce_client, mock_context):
        mock_mcp, captured = _make_mcp_and_capture()

        with patch(
            "mcp_server.tools.sosl_search.get_salesforce_client",
            return_value=mock_salesforce_client,
        ):
            from mcp_server.tools.sosl_search import register_sosl_search_tool

            register_sosl_search_tool(mock_mcp)
            result = await captured["tool"]("FIND {Acme}", ctx=mock_context)

        assert "searchRecords" in result
        mock_salesforce_client.search.assert_awaited_once_with("FIND {Acme}")


class TestDescribeGlobalTool:
    @pytest.mark.asyncio
    async def test_describe_global_calls_client(self, mock_salesforce_client, mock_context):
        mock_mcp, captured = _make_mcp_and_capture()

        with patch(
            "mcp_server.tools.describe_global.get_salesforce_client",
            return_value=mock_salesforce_client,
        ):
            from mcp_server.tools.describe_global import register_describe_global_tool

            register_describe_global_tool(mock_mcp)
            result = await captured["tool"](ctx=mock_context)

        assert "sobjects" in result
        assert len(result["sobjects"]) == 2
        mock_salesforce_client.describe_global.assert_awaited_once()


class TestDescribeSobjectTool:
    @pytest.mark.asyncio
    async def test_describe_sobject_calls_client(self, mock_salesforce_client, mock_context):
        mock_mcp, captured = _make_mcp_and_capture()

        with patch(
            "mcp_server.tools.describe_sobject.get_salesforce_client",
            return_value=mock_salesforce_client,
        ):
            from mcp_server.tools.describe_sobject import register_describe_sobject_tool

            register_describe_sobject_tool(mock_mcp)
            result = await captured["tool"]("Account", ctx=mock_context)

        assert result["name"] == "Account"
        assert "fields" in result
        mock_salesforce_client.describe_sobject.assert_awaited_once_with("Account")


class TestGetRecordTool:
    @pytest.mark.asyncio
    async def test_get_record_calls_client(self, mock_salesforce_client, mock_context):
        mock_mcp, captured = _make_mcp_and_capture()

        with patch(
            "mcp_server.tools.get_record.get_salesforce_client",
            return_value=mock_salesforce_client,
        ):
            from mcp_server.tools.get_record import register_get_record_tool

            register_get_record_tool(mock_mcp)
            result = await captured["tool"](
                "Account", "001xx000003DGbYAAW", ctx=mock_context
            )

        assert result["Id"] == "001xx000003DGbYAAW"
        assert result["Name"] == "Acme Corp"
        mock_salesforce_client.get_record.assert_awaited_once_with(
            "Account", "001xx000003DGbYAAW", None
        )

    @pytest.mark.asyncio
    async def test_get_record_with_fields(self, mock_salesforce_client, mock_context):
        mock_mcp, captured = _make_mcp_and_capture()

        with patch(
            "mcp_server.tools.get_record.get_salesforce_client",
            return_value=mock_salesforce_client,
        ):
            from mcp_server.tools.get_record import register_get_record_tool

            register_get_record_tool(mock_mcp)
            result = await captured["tool"](
                "Account", "001xx000003DGbYAAW", ctx=mock_context, fields=["Id", "Name"]
            )

        mock_salesforce_client.get_record.assert_awaited_once_with(
            "Account", "001xx000003DGbYAAW", ["Id", "Name"]
        )


class TestGetRelatedRecordsTool:
    @pytest.mark.asyncio
    async def test_get_related_records_calls_client(self, mock_salesforce_client, mock_context):
        mock_mcp, captured = _make_mcp_and_capture()

        with patch(
            "mcp_server.tools.get_related_records.get_salesforce_client",
            return_value=mock_salesforce_client,
        ):
            from mcp_server.tools.get_related_records import register_get_related_records_tool

            register_get_related_records_tool(mock_mcp)
            result = await captured["tool"](
                "Account", "001xx000003DGbYAAW", "Contacts", ctx=mock_context
            )

        assert result["totalSize"] == 1
        mock_salesforce_client.get_related_records.assert_awaited_once_with(
            "Account", "001xx000003DGbYAAW", "Contacts", None
        )


class TestGetUserInfoTool:
    @pytest.mark.asyncio
    async def test_get_user_info_calls_client(self, mock_salesforce_client, mock_context):
        mock_mcp, captured = _make_mcp_and_capture()

        with patch(
            "mcp_server.tools.get_user_info.get_salesforce_client",
            return_value=mock_salesforce_client,
        ):
            from mcp_server.tools.get_user_info import register_get_user_info_tool

            register_get_user_info_tool(mock_mcp)
            result = await captured["tool"](ctx=mock_context)

        assert result["name"] == "Test User"
        assert result["email"] == "test@example.com"
        mock_salesforce_client.get_user_info.assert_awaited_once()
