"""Pytest fixtures for Salesforce MCP server tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_salesforce_client():
    """Mock SalesforceClient for unit tests."""
    client = AsyncMock()

    client.query.return_value = {
        "totalSize": 2,
        "done": True,
        "records": [
            {"Id": "001xx000003DGbYAAW", "Name": "Acme Corp", "attributes": {"type": "Account"}},
            {"Id": "001xx000003DGbZAAW", "Name": "Global Inc", "attributes": {"type": "Account"}},
        ],
    }

    client.search.return_value = {
        "searchRecords": [
            {"Id": "001xx000003DGbYAAW", "Name": "Acme Corp", "attributes": {"type": "Account"}},
        ]
    }

    client.describe_global.return_value = {
        "sobjects": [
            {"name": "Account", "label": "Account", "queryable": True},
            {"name": "Contact", "label": "Contact", "queryable": True},
        ]
    }

    client.describe_sobject.return_value = {
        "name": "Account",
        "fields": [
            {"name": "Id", "type": "id", "label": "Account ID"},
            {"name": "Name", "type": "string", "label": "Account Name"},
        ],
        "childRelationships": [],
        "recordTypeInfos": [],
    }

    client.get_record.return_value = {
        "Id": "001xx000003DGbYAAW",
        "Name": "Acme Corp",
        "attributes": {"type": "Account"},
    }

    client.get_related_records.return_value = {
        "totalSize": 1,
        "done": True,
        "records": [
            {"Id": "003xx000004TmiQAAS", "Name": "John Doe", "attributes": {"type": "Contact"}},
        ],
    }

    client.get_user_info.return_value = {
        "id": "005xx000001X8zZAAS",
        "name": "Test User",
        "email": "test@example.com",
        "username": "test@example.com.sandbox",
    }

    return client


@pytest.fixture
def mock_context():
    """Mock FastMCP Context with a Bearer token in request headers."""
    ctx = MagicMock()
    ctx.request_context = MagicMock()
    ctx.request_context.headers = {"authorization": "Bearer test_access_token_abc123"}
    return ctx


@pytest.fixture
def patch_get_client(mock_salesforce_client):
    """Patch get_salesforce_client to return the mock client."""
    with patch(
        "mcp_server.salesforce.auth.get_salesforce_client",
        return_value=mock_salesforce_client,
    ) as patched:
        yield patched
