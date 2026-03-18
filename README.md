# Salesforce MCP Server

An MCP (Model Context Protocol) server that provides read-only access to the Salesforce REST API with per-user OAuth 2.0 authentication, deployable to AWS Bedrock AgentCore.

Each user authenticates as themselves — no shared service accounts or central credentials. All Salesforce API calls execute under the authenticated user's own access token, so Salesforce's native RBAC (profiles, permission sets, field-level security, sharing rules) applies automatically to every tool call.

## Quick Start

### Prerequisites

- Python 3.11+ (we recommend 3.13)
- [uv](https://github.com/astral-sh/uv) for package management
- A Salesforce Connected App configured for OAuth 2.0
- AWS CLI (for deployment)
- Terraform 1.5+ (for infrastructure)

### Salesforce Connected App Setup

1. In Salesforce Setup, navigate to **App Manager** and create a new Connected App.
2. Enable OAuth Settings:
   - **Callback URL**: `http://localhost:8000/oauth/callback` (local dev)
   - **Selected OAuth Scopes**: `api`, `chatter_api`, `refresh_token`
3. Note the **Consumer Key** (client ID) and **Consumer Secret** (client secret).

### Local Development

1. **Clone and install dependencies:**
   ```bash
   cp .env.local.example .env
   # Edit .env with your Salesforce Connected App credentials
   uv sync
   ```

2. **Run the MCP server:**
   ```bash
   make dev-server
   ```

The server is now running at `http://localhost:8000/mcp`.

### AWS Deployment

1. **Configure Terraform:**
   ```bash
   cd infra/terraform
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your values
   ```

2. **Deploy infrastructure:**
   ```bash
   terraform init
   terraform apply
   ```

3. **Build and push the container:**
   ```bash
   aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-2.amazonaws.com
   docker build -t <ecr-url>:latest .
   docker push <ecr-url>:latest
   ```

4. **Store Salesforce credentials** in AWS Secrets Manager (referenced in `.bedrock_agentcore.yaml`).

## MCP Tools

All tools call the Salesforce REST API at `/services/data/v66.0/` using the session user's token. If the user lacks permission for an object or field, the Salesforce error is surfaced as-is.

| Tool | Input | Salesforce Endpoint |
|------|-------|---------------------|
| `soql_query` | `query: string` | `GET /query?q={query}` |
| `sosl_search` | `query: string` | `GET /search?q={query}` |
| `describe_global` | *(none)* | `GET /sobjects` |
| `describe_sobject` | `sobject_name: string` | `GET /sobjects/{name}/describe` |
| `get_record` | `sobject_name, record_id, fields?` | `GET /sobjects/{name}/{id}` |
| `get_related_records` | `sobject_name, record_id, relationship_name, fields?` | `GET /sobjects/{name}/{id}/{rel}` |
| `get_user_info` | *(none)* | `GET /chatter/users/me` |

## Authentication

The server owns the OAuth 2.0 flow. When an MCP client (e.g. Claude AI) connects:

1. Client discovers auth via `/.well-known/oauth-authorization-server`
2. Server redirects to Salesforce's native login page
3. User logs in and approves access (Salesforce UI — no custom login form)
4. Server exchanges the auth code for an access token
5. All subsequent tool calls use that token against the Salesforce REST API

Switching between sandbox and production requires updating four env vars:

| Variable | Production | Sandbox |
|----------|-----------|---------|
| `SALESFORCE_INSTANCE_URL` | `https://myorg.my.salesforce.com` | `https://myorg--sandbox.sandbox.my.salesforce.com` |
| `SALESFORCE_LOGIN_URL` | `https://login.salesforce.com` | `https://test.salesforce.com` |
| `SALESFORCE_CLIENT_ID` | prod Connected App key | sandbox Connected App key |
| `SALESFORCE_CLIENT_SECRET` | prod Connected App secret | sandbox Connected App secret |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SALESFORCE_INSTANCE_URL` | *(required)* | Salesforce org URL |
| `SALESFORCE_LOGIN_URL` | `https://login.salesforce.com` | OAuth login endpoint |
| `SALESFORCE_CLIENT_ID` | *(required for OAuth)* | Connected App consumer key |
| `SALESFORCE_CLIENT_SECRET` | *(required for OAuth)* | Connected App consumer secret |
| `SALESFORCE_API_VERSION` | `v66.0` | Salesforce REST API version |
| `MCP_SERVER_NAME` | `salesforce-mcp-server` | Server name in logs |
| `MCP_LOG_LEVEL` | `INFO` | Logging verbosity |
| `MCP_LOG_FORMAT` | `json` | `json` or `text` |

See `.env.example` and `.env.local.example` for full configuration templates.

## Project Structure

```
salesforce-mcp-server/
├── mcp_server/
│   ├── server.py              # FastMCP server entry point
│   ├── config/
│   │   └── settings.py        # Pydantic configuration
│   ├── salesforce/
│   │   ├── client.py          # Salesforce REST API client
│   │   └── auth.py            # OAuth flow + token extraction
│   └── tools/
│       ├── soql_query.py      # SOQL query execution
│       ├── sosl_search.py     # SOSL full-text search
│       ├── describe_global.py # List accessible sobjects
│       ├── describe_sobject.py# Sobject metadata/fields
│       ├── get_record.py      # Single record fetch
│       ├── get_related_records.py # Related record fetch
│       └── get_user_info.py   # Current user info
├── infra/
│   └── terraform/
│       ├── main.tf
│       └── modules/
│           ├── foundation/    # IAM, ECR, Secrets
│           ├── agentcore/     # AgentCore runtime
│           └── monitoring/    # CloudWatch
├── tests/
│   ├── unit/
│   └── integration/
├── Dockerfile                 # Production container
├── Makefile                   # Development tasks
└── pyproject.toml             # Dependencies
```

## Testing

```bash
# Run unit tests
make test-unit

# Run integration tests (requires a real Salesforce org)
SALESFORCE_ACCESS_TOKEN=<your-token> make test-int

# Run all tests
make test
```

## Notes

### Stateless Mode

This server runs in **stateless mode** for AgentCore compatibility:
- No in-memory caching between requests
- Each request may hit a different container instance
- The Salesforce Bearer token is extracted from each request independently

### Adding New Tools

1. Create a new file in `mcp_server/tools/`:
   ```python
   from mcp.server.fastmcp import Context, FastMCP
   from mcp_server.salesforce.auth import get_salesforce_client

   def register_my_tool(mcp: FastMCP) -> None:
       @mcp.tool()
       async def my_tool(param: str, ctx: Context) -> dict:
           client = get_salesforce_client(ctx)
           return await client._request("GET", "/some/endpoint")
   ```

2. Register it in `mcp_server/tools/__init__.py`.
3. Add tests in `tests/unit/test_tools.py`.
