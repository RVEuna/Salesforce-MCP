"""Integration tests for MCP server.

These tests require a running OpenSearch instance.
Run with: make test-int (after make dev-infra)
"""

import os

import pytest

# Skip all tests in this module if OpenSearch is not available
pytestmark = pytest.mark.skipif(
    os.getenv("OPENSEARCH_ENDPOINT", "").startswith("http://localhost") is False
    and os.getenv("RUN_INTEGRATION_TESTS") != "true",
    reason="Integration tests require local OpenSearch or RUN_INTEGRATION_TESTS=true",
)


class TestOpenSearchIntegration:
    """Integration tests for OpenSearch connectivity."""

    @pytest.fixture
    def store(self):
        """Get a real OpenSearchStore instance."""
        from mcp_server.store import OpenSearchStore

        return OpenSearchStore()

    def test_health_check(self, store):
        """Test we can connect to OpenSearch."""
        health = store.health_check()

        assert "status" in health
        assert health["status"] in ["green", "yellow", "red"]

    def test_search_empty_index(self, store):
        """Test search on an empty or non-existent index."""
        # This should not raise an error, just return empty results
        results = store.search("test query", limit=10)

        assert isinstance(results, list)

    def test_get_by_id_not_found(self, store):
        """Test get_by_id for non-existent document."""
        result = store.get_by_id("definitely-does-not-exist-12345")

        assert result is None


class TestMCPServerIntegration:
    """Integration tests for the full MCP server."""

    # Add more integration tests as needed
    pass
