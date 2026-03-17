#!/usr/bin/env python3
"""Initialize OpenSearch index with proper mappings.

This script creates the OpenSearch index with the correct schema
for storing documents with text content and optional embeddings.

Usage:
    uv run python scripts/init-index.py
"""

import json
import sys

from mcp_server.config import opensearch_settings
from mcp_server.store import OpenSearchStore


def create_index_mapping() -> dict:
    """Create the index mapping for documents."""
    return {
        "settings": {
            "index": {
                "number_of_shards": 2,
                "number_of_replicas": 1,
                "knn": True,  # Enable k-NN for vector search
            }
        },
        "mappings": {
            "properties": {
                "content": {
                    "type": "text",
                    "analyzer": "standard",
                },
                "title": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "embedding": {
                    "type": "knn_vector",
                    "dimension": 1536,  # OpenAI text-embedding-3-small
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                        "parameters": {
                            "ef_construction": 128,
                            "m": 16,
                        },
                    },
                },
                "metadata": {
                    "type": "object",
                    "enabled": True,
                },
                "related_ids": {
                    "type": "keyword",
                },
                "created_at": {
                    "type": "date",
                },
                "updated_at": {
                    "type": "date",
                },
            }
        },
    }


def main():
    """Create the OpenSearch index."""
    print(f"Connecting to OpenSearch at {opensearch_settings.endpoint}...")

    store = OpenSearchStore()
    client = store.client
    index_name = opensearch_settings.index_name

    # Check if index already exists
    if client.indices.exists(index=index_name):
        print(f"Index '{index_name}' already exists.")
        response = input("Delete and recreate? (y/N): ")
        if response.lower() != "y":
            print("Aborted.")
            sys.exit(0)

        print(f"Deleting index '{index_name}'...")
        client.indices.delete(index=index_name)

    # Create the index
    print(f"Creating index '{index_name}'...")
    mapping = create_index_mapping()
    client.indices.create(index=index_name, body=mapping)

    print(f"Index '{index_name}' created successfully!")
    print("\nIndex mapping:")
    print(json.dumps(mapping, indent=2))


if __name__ == "__main__":
    main()
