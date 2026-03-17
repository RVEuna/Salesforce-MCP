#!/usr/bin/env python3
"""Seed OpenSearch with sample documents for testing.

This script loads sample documents into OpenSearch for local development
and testing.

Usage:
    uv run python scripts/seed-data.py
"""

from datetime import datetime

from mcp_server.config import opensearch_settings
from mcp_server.store import OpenSearchStore

SAMPLE_DOCUMENTS = [
    {
        "id": "doc-001",
        "title": "Getting Started Guide",
        "content": """
            Welcome to the platform! This guide will help you get started.

            First, install the CLI tool:
            uv tool install our-cli

            Then authenticate:
            our-cli auth login

            You're now ready to start using the platform.
        """,
        "metadata": {"type": "guide", "category": "onboarding"},
        "related_ids": ["doc-002", "doc-003"],
    },
    {
        "id": "doc-002",
        "title": "API Reference",
        "content": """
            Complete API reference for our REST API.

            Authentication:
            All requests require a Bearer token in the Authorization header.

            Endpoints:
            - GET /api/v1/resources - List all resources
            - POST /api/v1/resources - Create a new resource
            - GET /api/v1/resources/{id} - Get a specific resource
            - PUT /api/v1/resources/{id} - Update a resource
            - DELETE /api/v1/resources/{id} - Delete a resource
        """,
        "metadata": {"type": "reference", "category": "api"},
        "related_ids": ["doc-001"],
    },
    {
        "id": "doc-003",
        "title": "Troubleshooting Common Issues",
        "content": """
            Solutions for common problems you might encounter.

            Issue: Authentication failed
            Solution: Check that your token hasn't expired. Run 'our-cli auth refresh'.

            Issue: Connection timeout
            Solution: Check your network connection and firewall settings.

            Issue: Rate limit exceeded
            Solution: Implement exponential backoff in your requests.
        """,
        "metadata": {"type": "guide", "category": "troubleshooting"},
        "related_ids": ["doc-001", "doc-002"],
    },
    {
        "id": "doc-004",
        "title": "Configuration Options",
        "content": """
            All available configuration options for the platform.

            Environment Variables:
            - API_URL: Base URL for API requests
            - API_KEY: Your API key
            - LOG_LEVEL: Logging verbosity (DEBUG, INFO, WARN, ERROR)
            - TIMEOUT: Request timeout in seconds

            Configuration File:
            Create a config.yaml file in your project root.
        """,
        "metadata": {"type": "reference", "category": "configuration"},
        "related_ids": [],
    },
    {
        "id": "doc-005",
        "title": "Best Practices",
        "content": """
            Recommended patterns and practices for using the platform effectively.

            1. Use environment variables for sensitive configuration
            2. Implement proper error handling with retries
            3. Cache responses where appropriate
            4. Use pagination for large result sets
            5. Monitor your API usage to stay within limits
        """,
        "metadata": {"type": "guide", "category": "best-practices"},
        "related_ids": ["doc-002", "doc-004"],
    },
]


def main():
    """Seed the OpenSearch index with sample documents."""
    print(f"Connecting to OpenSearch at {opensearch_settings.endpoint}...")

    store = OpenSearchStore()
    client = store.client
    index_name = opensearch_settings.index_name

    # Check if index exists
    if not client.indices.exists(index=index_name):
        print(f"Index '{index_name}' does not exist. Run 'make init-index' first.")
        return

    print(f"Seeding {len(SAMPLE_DOCUMENTS)} documents into '{index_name}'...")

    for doc in SAMPLE_DOCUMENTS:
        doc_id = doc.pop("id")
        doc["created_at"] = datetime.utcnow().isoformat()
        doc["updated_at"] = datetime.utcnow().isoformat()

        # Index the document
        client.index(
            index=index_name,
            id=doc_id,
            body=doc,
            refresh=True,  # Make immediately searchable
        )
        print(f"  Indexed: {doc_id} - {doc['title']}")

    print(f"\nSuccessfully seeded {len(SAMPLE_DOCUMENTS)} documents!")
    print("\nYou can now test the MCP server with these documents.")


if __name__ == "__main__":
    main()
