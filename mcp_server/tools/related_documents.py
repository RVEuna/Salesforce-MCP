"""Related documents tool - demonstrates relationship traversal patterns.

This tool shows:
- Following document relationships
- Two-step retrieval (source doc → related docs)
- Relationship type filtering
- Handling documents with no relationships
"""

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP


def register_related_documents_tool(
    mcp: FastMCP,
    get_store: Callable,
    execute_tool: Callable,
) -> None:
    """Register the related_documents tool with the MCP server.

    Args:
        mcp: The FastMCP server instance
        get_store: Function to get the OpenSearchStore instance
        execute_tool: Wrapper function for execution with timing/logging
    """

    @mcp.tool()
    def related_documents(
        document_id: str,
        relationship_type: str | None = None,
    ) -> dict:
        """Find documents related to a given document.

        Looks up a document and retrieves all documents linked to it via
        the relationship field. Useful for exploring document graphs.

        The source document must have a 'related_ids' field containing
        either a list of IDs or a list of objects with 'id' and 'type' fields.

        Args:
            document_id: The ID of the source document
            relationship_type: Optional filter for relationship type
                              (e.g., "references", "parent", "child")

        Returns:
            Dictionary containing:
            - source_id: The source document ID
            - related: List of related documents
            - count: Number of related documents found
            - relationship_type: The filter applied (if any)
        """

        def _get_related():
            store = get_store()

            # First check if source document exists
            source_doc = store.get_by_id(document_id)
            if not source_doc:
                return {
                    "source_id": document_id,
                    "related": [],
                    "count": 0,
                    "error": f"Source document not found: {document_id}",
                }

            # Get related documents
            related = store.get_related(
                document_id=document_id,
                relationship_field="related_ids",
                relationship_type=relationship_type,
            )

            return {
                "source_id": document_id,
                "source_title": source_doc.get("title", source_doc.get("id")),
                "related": related,
                "count": len(related),
                "relationship_type": relationship_type,
            }

        return execute_tool(
            "related_documents",
            {"document_id": document_id, "relationship_type": relationship_type},
            _get_related,
        )
