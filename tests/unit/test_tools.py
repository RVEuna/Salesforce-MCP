"""Unit tests for MCP tools."""

from unittest.mock import MagicMock


class TestEchoTool:
    """Tests for echo tool."""

    def test_echo_returns_message(self):
        """Test echo returns the input message."""
        from mcp_server.tools.echo import register_echo_tool

        # Create mock MCP and execute_tool
        mock_mcp = MagicMock()
        captured_tool = None

        def capture_decorator():
            def decorator(func):
                nonlocal captured_tool
                captured_tool = func
                return func

            return decorator

        mock_mcp.tool = capture_decorator

        # Register the tool
        register_echo_tool(mock_mcp, lambda name, args, fn: fn())

        # Call the captured tool
        result = captured_tool("Hello, World!")

        assert result["message"] == "Hello, World!"
        assert result["length"] == 13
        assert result["tool"] == "echo"


class TestSearchTool:
    """Tests for search tool."""

    def test_search_calls_store(self, mock_store):
        """Test search tool calls store.search."""
        from mcp_server.tools.search import register_search_tool

        mock_mcp = MagicMock()
        captured_tool = None

        def capture_decorator():
            def decorator(func):
                nonlocal captured_tool
                captured_tool = func
                return func

            return decorator

        mock_mcp.tool = capture_decorator

        register_search_tool(
            mock_mcp,
            lambda: mock_store,
            lambda name, args, fn: fn(),
        )

        result = captured_tool("test query", limit=5)

        assert "results" in result
        assert "total" in result
        assert result["query"] == "test query"

    def test_search_with_invalid_filters_returns_error(self, mock_store):
        """Test search with invalid JSON filters."""
        from mcp_server.tools.search import register_search_tool

        mock_mcp = MagicMock()
        captured_tool = None

        def capture_decorator():
            def decorator(func):
                nonlocal captured_tool
                captured_tool = func
                return func

            return decorator

        mock_mcp.tool = capture_decorator

        register_search_tool(
            mock_mcp,
            lambda: mock_store,
            lambda name, args, fn: fn(),
        )

        result = captured_tool("test", filters="not valid json")

        assert "error" in result


class TestLookupTool:
    """Tests for lookup tool."""

    def test_lookup_found(self, mock_store):
        """Test lookup returns document when found."""
        from mcp_server.tools.lookup import register_lookup_tool

        mock_mcp = MagicMock()
        captured_tool = None

        def capture_decorator():
            def decorator(func):
                nonlocal captured_tool
                captured_tool = func
                return func

            return decorator

        mock_mcp.tool = capture_decorator

        register_lookup_tool(
            mock_mcp,
            lambda: mock_store,
            lambda name, args, fn: fn(),
        )

        result = captured_tool("doc-1")

        assert result["found"] is True
        assert result["document"] is not None
        assert result["document_id"] == "doc-1"

    def test_lookup_not_found(self, mock_store):
        """Test lookup returns not found message."""
        from mcp_server.tools.lookup import register_lookup_tool

        mock_store.get_by_id = MagicMock(return_value=None)

        mock_mcp = MagicMock()
        captured_tool = None

        def capture_decorator():
            def decorator(func):
                nonlocal captured_tool
                captured_tool = func
                return func

            return decorator

        mock_mcp.tool = capture_decorator

        register_lookup_tool(
            mock_mcp,
            lambda: mock_store,
            lambda name, args, fn: fn(),
        )

        result = captured_tool("nonexistent")

        assert result["found"] is False
        assert result["document"] is None


class TestBatchLookupTool:
    """Tests for batch_lookup tool."""

    def test_batch_lookup_returns_multiple_docs(self, mock_store):
        """Test batch_lookup returns multiple documents."""
        from mcp_server.tools.batch_lookup import register_batch_lookup_tool

        mock_mcp = MagicMock()
        captured_tool = None

        def capture_decorator():
            def decorator(func):
                nonlocal captured_tool
                captured_tool = func
                return func

            return decorator

        mock_mcp.tool = capture_decorator

        register_batch_lookup_tool(
            mock_mcp,
            lambda: mock_store,
            lambda name, args, fn: fn(),
        )

        result = captured_tool("doc-1,doc-2,doc-3")

        assert "documents" in result
        assert result["requested_count"] == 3
        assert result["found_count"] == 2  # doc-3 not found in mock

    def test_batch_lookup_empty_input(self, mock_store):
        """Test batch_lookup with empty input."""
        from mcp_server.tools.batch_lookup import register_batch_lookup_tool

        mock_mcp = MagicMock()
        captured_tool = None

        def capture_decorator():
            def decorator(func):
                nonlocal captured_tool
                captured_tool = func
                return func

            return decorator

        mock_mcp.tool = capture_decorator

        register_batch_lookup_tool(
            mock_mcp,
            lambda: mock_store,
            lambda name, args, fn: fn(),
        )

        result = captured_tool("")

        assert "error" in result
