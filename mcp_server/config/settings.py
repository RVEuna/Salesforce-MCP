"""Configuration settings for MCP server.

Supports both local development (Docker OpenSearch) and AWS deployment
(OpenSearch managed domains with IAM authentication).
"""

import os
from typing import Literal

from pydantic import BaseModel, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenSearchSettings(BaseModel):
    """OpenSearch connection settings.

    Supports both local development (Docker) and AWS managed domains.

    Local development:
        OPENSEARCH_ENDPOINT=http://localhost:9200
        OPENSEARCH_AUTH_MODE=none

    AWS managed domain:
        OPENSEARCH_ENDPOINT=https://search-my-domain.us-east-2.es.amazonaws.com
        OPENSEARCH_AUTH_MODE=aws
    """

    endpoint: str = Field(
        default_factory=lambda: os.getenv("OPENSEARCH_ENDPOINT", "http://localhost:9200"),
        description="OpenSearch endpoint URL",
    )
    index_name: str = Field(
        default_factory=lambda: os.getenv("OPENSEARCH_INDEX", "documents"),
        description="Name of the OpenSearch index",
    )
    region: str = Field(
        default_factory=lambda: os.getenv("OPENSEARCH_REGION", "us-east-2"),
        description="AWS region for the OpenSearch domain",
    )

    # "es" for managed domains, "aoss" for serverless (we use managed)
    service: Literal["es", "aoss"] = Field(
        default_factory=lambda: os.getenv("OPENSEARCH_SERVICE", "es"),
        description="AWS service name for SigV4 signing",
    )

    # Authentication mode
    auth_mode: Literal["aws", "basic", "none"] = Field(
        default_factory=lambda: os.getenv("OPENSEARCH_AUTH_MODE", "none"),
        description="'aws' for SigV4, 'basic' for user/pass, 'none' for local dev",
    )

    # Basic auth (for local or managed domain with fine-grained access control)
    username: str | None = Field(
        default_factory=lambda: os.getenv("OPENSEARCH_USERNAME"),
        description="Username for basic auth",
    )
    password: str | None = Field(
        default_factory=lambda: os.getenv("OPENSEARCH_PASSWORD"),
        description="Password for basic auth",
    )

    # Connection tuning
    timeout: int = Field(
        default_factory=lambda: int(os.getenv("OPENSEARCH_TIMEOUT", "30")),
        description="Connection timeout in seconds",
    )
    max_retries: int = Field(
        default_factory=lambda: int(os.getenv("OPENSEARCH_MAX_RETRIES", "3")),
        description="Maximum retry attempts",
    )

    @computed_field
    @property
    def use_ssl(self) -> bool:
        """Auto-detect SSL from endpoint scheme."""
        return self.endpoint.startswith("https://")

    @computed_field
    @property
    def verify_certs(self) -> bool:
        """Verify certs for HTTPS, skip for local HTTP."""
        return self.use_ssl

    def get_hosts(self) -> list[dict]:
        """Get OpenSearch host configuration for opensearch-py client."""
        from urllib.parse import urlparse

        endpoint = self.endpoint.rstrip("/")
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"

        parsed = urlparse(endpoint)
        host = parsed.hostname or "localhost"

        if parsed.port:
            port = parsed.port
        elif parsed.scheme == "http":
            port = 9200
        else:
            port = 443

        return [{"host": host, "port": port}]


class MCPSettings(BaseSettings):
    """MCP Server configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MCP_",
        extra="ignore",
    )

    # Server identity
    server_name: str = "my-mcp-server"
    server_version: str = "1.0.0"

    # Transport (AgentCore uses streamable-http)
    host: str = "0.0.0.0"
    port: int = 8000
    path: str = "/mcp"
    stateless: bool = True

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Secrets (for API keys in production)
    secret_provider: Literal["aws", "local"] = "local"
    aws_secret_name: str = "mcp/api-keys"
    aws_secret_region: str = "us-east-2"


# Singleton instances
opensearch_settings = OpenSearchSettings()
mcp_settings = MCPSettings()
