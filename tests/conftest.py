"""Pytest fixtures for MCP server tests."""

from unittest.mock import MagicMock, patch

import pytest


class NotFoundError(Exception):
    """Mock NotFoundError for testing."""

    pass


@pytest.fixture
def mock_opensearch_client():
    """Mock OpenSearch client for unit tests."""
    client = MagicMock()

    # Mock search response
    client.search.return_value = {
        "hits": {
            "total": {"value": 2},
            "hits": [
                {
                    "_id": "doc-1",
                    "_score": 0.95,
                    "_source": {
                        "content": "Test document 1",
                        "title": "Document 1",
                    },
                },
                {
                    "_id": "doc-2",
                    "_score": 0.85,
                    "_source": {
                        "content": "Test document 2",
                        "title": "Document 2",
                    },
                },
            ],
        }
    }

    # Mock get response
    client.get.return_value = {
        "_id": "doc-1",
        "_source": {
            "content": "Test document 1",
            "title": "Document 1",
            "related_ids": ["doc-2", "doc-3"],
        },
    }

    # Mock mget response
    client.mget.return_value = {
        "docs": [
            {
                "_id": "doc-1",
                "found": True,
                "_source": {"content": "Document 1", "title": "Title 1"},
            },
            {
                "_id": "doc-2",
                "found": True,
                "_source": {"content": "Document 2", "title": "Title 2"},
            },
            {
                "_id": "doc-3",
                "found": False,
            },
        ]
    }

    # Mock cluster health
    client.cluster.health.return_value = {
        "cluster_name": "test-cluster",
        "status": "green",
        "number_of_nodes": 2,
    }

    return client


@pytest.fixture
def mock_store(mock_opensearch_client):
    """Mock OpenSearchStore for unit tests."""
    with patch("mcp_server.store.opensearch.OpenSearch") as mock_class:
        mock_class.return_value = mock_opensearch_client
        from mcp_server.store import OpenSearchStore

        store = OpenSearchStore()
        store._client = mock_opensearch_client
        yield store


@pytest.fixture
def sample_documents():
    """Sample documents for testing."""
    return [
        {
            "id": "doc-1",
            "title": "Getting Started Guide",
            "content": "This guide helps you get started with the platform.",
            "related_ids": ["doc-2"],
        },
        {
            "id": "doc-2",
            "title": "API Reference",
            "content": "Complete API reference documentation.",
            "related_ids": ["doc-1", "doc-3"],
        },
        {
            "id": "doc-3",
            "title": "Troubleshooting",
            "content": "Common issues and how to resolve them.",
            "related_ids": [],
        },
    ]
