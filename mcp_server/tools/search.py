"""Search tool - demonstrates retrieval patterns.

This tool shows:
- Text-based search (keyword/BM25)
- Filtering by metadata fields
- Pagination with limit parameter
- Structured result format
"""

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP


def register_search_tool(
    mcp: FastMCP,
    get_store: Callable,
    execute_tool: Callable,
) -> None:
    """Register the search tool with the MCP server.

    Args:
        mcp: The FastMCP server instance
        get_store: Function to get the OpenSearchStore instance
        execute_tool: Wrapper function for execution with timing/logging
    """

    @mcp.tool()
    def search(
        query: str,
        limit: int = 10,
        filters: str | None = None,
    ) -> dict:
        """Search for documents matching a query.

        Performs a text-based search across documents in the index.
        Supports filtering by metadata fields.

        Args:
            query: The search query string
            limit: Maximum number of results to return (default: 10, max: 100)
            filters: Optional JSON string of filters (e.g., '{"status": "active"}')

        Returns:
            Dictionary containing:
            - results: List of matching documents with id, score, and content
            - total: Number of results returned
            - query: The original query
        """

        def _search():
            store = get_store()

            # Parse filters if provided
            filter_dict = None
            if filters:
                import json

                try:
                    filter_dict = json.loads(filters)
                except json.JSONDecodeError:
                    return {"error": f"Invalid filters JSON: {filters}"}

            # Enforce limit bounds
            effective_limit = min(max(1, limit), 100)

            results = store.search(
                query=query,
                limit=effective_limit,
                filters=filter_dict,
            )

            return {
                "results": results,
                "total": len(results),
                "query": query,
            }

        return execute_tool(
            "search",
            {"query": query, "limit": limit, "filters": filters},
            _search,
        )
