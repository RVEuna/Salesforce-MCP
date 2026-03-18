"""Configuration settings for MCP server.

Supports both local development and AWS deployment with Salesforce backend.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class SalesforceSettings(BaseSettings):
    """Salesforce connection settings.

    All SALESFORCE_* env vars are read automatically.

    Production:
        SALESFORCE_INSTANCE_URL=https://myorg.my.salesforce.com
        SALESFORCE_LOGIN_URL=https://login.salesforce.com
        SALESFORCE_CLIENT_ID=<Connected App consumer key>
        SALESFORCE_CLIENT_SECRET=<Connected App consumer secret>

    Sandbox:
        SALESFORCE_INSTANCE_URL=https://myorg--sandbox.sandbox.my.salesforce.com
        SALESFORCE_LOGIN_URL=https://test.salesforce.com
        SALESFORCE_CLIENT_ID=<Sandbox Connected App consumer key>
        SALESFORCE_CLIENT_SECRET=<Sandbox Connected App consumer secret>
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SALESFORCE_",
        extra="ignore",
    )

    instance_url: str
    login_url: str = "https://login.salesforce.com"
    client_id: str = ""
    client_secret: str = ""
    api_version: str = "v66.0"
    auth_timeout: int = 10
    access_token: str = ""


class MCPSettings(BaseSettings):
    """MCP Server configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MCP_",
        extra="ignore",
    )

    server_name: str = "salesforce-mcp-server"
    server_version: str = "1.0.0"

    # Transport (AgentCore uses streamable-http)
    host: str = "0.0.0.0"
    port: int = 8000
    path: str = "/mcp"
    stateless: bool = True

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # OAuth proxy (server acts as authorization server for MCP clients)
    base_url: str = "http://localhost:8000"
    jwt_secret: str = ""
    auth_code_ttl: int = 300

    # Secrets (for API keys in production)
    secret_provider: Literal["aws", "local"] = "local"
    aws_secret_name: str = "mcp/api-keys"
    aws_secret_region: str = "us-east-2"


salesforce_settings = SalesforceSettings()
mcp_settings = MCPSettings()
