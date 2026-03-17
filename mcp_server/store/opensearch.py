"""OpenSearch client with support for local and AWS authentication.

This module provides a unified interface for connecting to OpenSearch,
whether running locally in Docker or as an AWS managed domain.

Usage:
    from mcp_server.store import OpenSearchStore

    store = OpenSearchStore()
    results = store.search("my query", limit=10)
    doc = store.get_by_id("doc-123")
    docs = store.get_by_ids(["doc-1", "doc-2", "doc-3"])
"""

import logging
from typing import Any

from opensearchpy import OpenSearch, RequestsHttpConnection

from mcp_server.config import opensearch_settings

logger = logging.getLogger(__name__)


class OpenSearchStore:
    """OpenSearch client wrapper with local and AWS auth support."""

    def __init__(self, settings: Any | None = None):
        """Initialize the OpenSearch client.

        Args:
            settings: Optional OpenSearchSettings instance. Uses global settings if not provided.
        """
        self.settings = settings or opensearch_settings
        self._client: OpenSearch | None = None

    @property
    def client(self) -> OpenSearch:
        """Lazily initialize and return the OpenSearch client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> OpenSearch:
        """Create an OpenSearch client based on auth mode."""
        hosts = self.settings.get_hosts()

        client_kwargs = {
            "hosts": hosts,
            "use_ssl": self.settings.use_ssl,
            "verify_certs": self.settings.verify_certs,
            "connection_class": RequestsHttpConnection,
            "timeout": self.settings.timeout,
            "max_retries": self.settings.max_retries,
            "retry_on_timeout": True,
        }

        if self.settings.auth_mode == "aws":
            # AWS SigV4 authentication for managed domains
            import boto3
            from requests_aws4auth import AWS4Auth

            credentials = boto3.Session().get_credentials()
            auth = AWS4Auth(
                credentials.access_key,
                credentials.secret_key,
                self.settings.region,
                self.settings.service,
                session_token=credentials.token,
            )
            client_kwargs["http_auth"] = auth

        elif self.settings.auth_mode == "basic":
            # Basic authentication
            if self.settings.username and self.settings.password:
                client_kwargs["http_auth"] = (
                    self.settings.username,
                    self.settings.password,
                )

        # auth_mode == "none" requires no additional config

        logger.info(
            f"Connecting to OpenSearch: {hosts[0]['host']}:{hosts[0]['port']} "
            f"(auth={self.settings.auth_mode}, ssl={self.settings.use_ssl})"
        )

        return OpenSearch(**client_kwargs)

    def search(
        self,
        query: str,
        limit: int = 10,
        filters: dict | None = None,
        fields: list[str] | None = None,
    ) -> list[dict]:
        """Search documents using a text query.

        This performs a simple match query. For vector search, use search_vector().

        Args:
            query: The search query string
            limit: Maximum number of results
            filters: Optional filters to apply (e.g., {"status": "active"})
            fields: Fields to search in (defaults to ["content"])

        Returns:
            List of matching documents with _id, _score, and _source
        """
        search_fields = fields or ["content"]

        body: dict[str, Any] = {
            "size": limit,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": search_fields,
                            }
                        }
                    ]
                }
            },
        }

        # Add filters if provided
        if filters:
            filter_clauses = [{"term": {k: v}} for k, v in filters.items()]
            body["query"]["bool"]["filter"] = filter_clauses

        response = self.client.search(index=self.settings.index_name, body=body)

        return [
            {
                "id": hit["_id"],
                "score": hit["_score"],
                **hit["_source"],
            }
            for hit in response["hits"]["hits"]
        ]

    def search_vector(
        self,
        vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[dict]:
        """Search documents using a vector (k-NN search).

        Args:
            vector: The query vector (must match index dimension)
            limit: Maximum number of results
            filters: Optional filters to apply

        Returns:
            List of matching documents with _id, _score, and _source
        """
        body: dict[str, Any] = {
            "size": limit,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": vector,
                        "k": limit,
                    }
                }
            },
        }

        # Add filters if provided
        if filters:
            body["query"] = {
                "bool": {
                    "must": [body["query"]],
                    "filter": [{"term": {k: v}} for k, v in filters.items()],
                }
            }

        response = self.client.search(index=self.settings.index_name, body=body)

        return [
            {
                "id": hit["_id"],
                "score": hit["_score"],
                **hit["_source"],
            }
            for hit in response["hits"]["hits"]
        ]

    def get_by_id(self, document_id: str) -> dict | None:
        """Get a single document by ID.

        Args:
            document_id: The document ID

        Returns:
            Document dict with id and source fields, or None if not found
        """
        try:
            response = self.client.get(index=self.settings.index_name, id=document_id)
            return {
                "id": response["_id"],
                **response["_source"],
            }
        except Exception as e:
            if "NotFoundError" in type(e).__name__ or "not_found" in str(e).lower():
                return None
            raise

    def get_by_ids(self, document_ids: list[str]) -> list[dict]:
        """Get multiple documents by IDs (bulk mget).

        Args:
            document_ids: List of document IDs

        Returns:
            List of documents (preserves order, skips not found)
        """
        if not document_ids:
            return []

        body = {"ids": document_ids}
        response = self.client.mget(index=self.settings.index_name, body=body)

        results = []
        for doc in response["docs"]:
            if doc.get("found"):
                results.append(
                    {
                        "id": doc["_id"],
                        **doc["_source"],
                    }
                )

        return results

    def get_related(
        self,
        document_id: str,
        relationship_field: str = "related_ids",
        relationship_type: str | None = None,
    ) -> list[dict]:
        """Get documents related to a given document.

        This assumes documents have a field containing IDs of related documents.

        Args:
            document_id: The source document ID
            relationship_field: Field containing related document IDs
            relationship_type: Optional type filter for relationships

        Returns:
            List of related documents
        """
        # First, get the source document
        source_doc = self.get_by_id(document_id)
        if not source_doc:
            return []

        # Extract related IDs from the source document
        related_ids = source_doc.get(relationship_field, [])

        # If relationship_type is specified, filter by type
        # Assumes related_ids is a list of dicts with "id" and "type" fields
        if (
            relationship_type
            and isinstance(related_ids, list)
            and related_ids
            and isinstance(related_ids[0], dict)
        ):
            related_ids = [r["id"] for r in related_ids if r.get("type") == relationship_type]

        # Handle case where related_ids might be a simple list of strings
        if related_ids and isinstance(related_ids[0], dict):
            related_ids = [r.get("id", r) for r in related_ids]

        if not related_ids:
            return []

        return self.get_by_ids(related_ids)

    def health_check(self) -> dict:
        """Check OpenSearch cluster health.

        Returns:
            Health status dict with cluster_name, status, etc.
        """
        return self.client.cluster.health()
