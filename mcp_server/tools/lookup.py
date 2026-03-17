"""Lookup tool - demonstrates single document retrieval.

This tool shows:
- Direct document fetch by ID
- Not-found handling
- Clean response structure
"""

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP


def register_lookup_tool(
    mcp: FastMCP,
    get_store: Callable,
    execute_tool: Callable,
) -> None:
    """Register the lookup tool with the MCP server.

    Args:
        mcp: The FastMCP server instance
        get_store: Function to get the OpenSearchStore instance
        execute_tool: Wrapper function for execution with timing/logging
    """

    @mcp.tool()
    def lookup(document_id: str) -> dict:
        """Look up a single document by its ID.

        Retrieves a document directly by its unique identifier.
        Returns the full document content if found.

        Args:
            document_id: The unique identifier of the document

        Returns:
            Dictionary containing:
            - found: Whether the document was found
            - document: The document data (if found)
            - document_id: The requested ID
        """

        def _lookup():
            store = get_store()
            document = store.get_by_id(document_id)

            if document:
                return {
                    "found": True,
                    "document": document,
                    "document_id": document_id,
                }
            else:
                return {
                    "found": False,
                    "document": None,
                    "document_id": document_id,
                    "message": f"No document found with ID: {document_id}",
                }

        return execute_tool(
            "lookup",
            {"document_id": document_id},
            _lookup,
        )
