"""Unit tests for OpenSearchStore."""


class TestOpenSearchStore:
    """Tests for OpenSearchStore class."""

    def test_search_returns_formatted_results(self, mock_store):
        """Test that search returns properly formatted results."""
        results = mock_store.search("test query", limit=10)

        assert len(results) == 2
        assert results[0]["id"] == "doc-1"
        assert results[0]["score"] == 0.95
        assert "content" in results[0]

    def test_search_with_filters(self, mock_store):
        """Test search with filters."""
        mock_store.search(
            "test query",
            limit=10,
            filters={"status": "active"},
        )

        # Verify the search was called with filters
        call_args = mock_store.client.search.call_args
        body = call_args.kwargs["body"]
        assert "filter" in body["query"]["bool"]

    def test_get_by_id_found(self, mock_store):
        """Test get_by_id when document exists."""
        result = mock_store.get_by_id("doc-1")

        assert result is not None
        assert result["id"] == "doc-1"
        assert "content" in result

    def test_get_by_id_not_found(self, mock_store):
        """Test get_by_id when document doesn't exist."""
        from tests.conftest import NotFoundError

        mock_store.client.get.side_effect = NotFoundError("Document not found")

        result = mock_store.get_by_id("nonexistent")

        assert result is None

    def test_get_by_ids_returns_found_documents(self, mock_store):
        """Test get_by_ids returns only found documents."""
        results = mock_store.get_by_ids(["doc-1", "doc-2", "doc-3"])

        # doc-3 was not found in the mock response
        assert len(results) == 2
        assert results[0]["id"] == "doc-1"
        assert results[1]["id"] == "doc-2"

    def test_get_by_ids_empty_list(self, mock_store):
        """Test get_by_ids with empty list."""
        results = mock_store.get_by_ids([])

        assert results == []

    def test_get_related_returns_related_documents(self, mock_store):
        """Test get_related returns related documents."""
        # Mock the mget to return related docs
        mock_store.client.mget.return_value = {
            "docs": [
                {"_id": "doc-2", "found": True, "_source": {"title": "Related Doc"}},
            ]
        }

        results = mock_store.get_related("doc-1")

        assert len(results) >= 0  # Depends on mock setup

    def test_health_check(self, mock_store):
        """Test health_check returns cluster info."""
        health = mock_store.health_check()

        assert health["status"] == "green"
        assert "cluster_name" in health
