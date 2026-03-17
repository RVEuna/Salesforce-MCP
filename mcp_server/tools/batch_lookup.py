"""Batch lookup tool - demonstrates bulk retrieval patterns.

This tool shows:
- Efficient bulk document fetch (mget)
- Handling partial results (some docs not found)
- Order preservation
- Input validation for lists
"""

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP


def register_batch_lookup_tool(
    mcp: FastMCP,
    get_store: Callable,
    execute_tool: Callable,
) -> None:
    """Register the batch_lookup tool with the MCP server.

    Args:
        mcp: The FastMCP server instance
        get_store: Function to get the OpenSearchStore instance
        execute_tool: Wrapper function for execution with timing/logging
    """

    @mcp.tool()
    def batch_lookup(document_ids: str) -> dict:
        """Look up multiple documents by their IDs in a single request.

        More efficient than multiple individual lookups. Uses OpenSearch's
        mget API for bulk retrieval.

        Args:
            document_ids: Comma-separated list of document IDs
                         (e.g., "doc-1,doc-2,doc-3")

        Returns:
            Dictionary containing:
            - documents: List of found documents
            - found_count: Number of documents found
            - requested_count: Number of IDs requested
            - not_found: List of IDs that were not found
        """

        def _batch_lookup():
            store = get_store()

            # Parse comma-separated IDs
            ids = [id.strip() for id in document_ids.split(",") if id.strip()]

            if not ids:
                return {
                    "error": "No valid document IDs provided",
                    "documents": [],
                    "found_count": 0,
                    "requested_count": 0,
                }

            # Enforce reasonable limit
            if len(ids) > 100:
                return {
                    "error": f"Too many IDs requested ({len(ids)}). Maximum is 100.",
                    "documents": [],
                    "found_count": 0,
                    "requested_count": len(ids),
                }

            documents = store.get_by_ids(ids)

            # Determine which IDs were not found
            found_ids = {doc["id"] for doc in documents}
            not_found = [id for id in ids if id not in found_ids]

            return {
                "documents": documents,
                "found_count": len(documents),
                "requested_count": len(ids),
                "not_found": not_found if not_found else None,
            }

        return execute_tool(
            "batch_lookup",
            {"document_ids": document_ids},
            _batch_lookup,
        )
