# Salesforce MCP Server

A production-ready [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that provides **read-only** access to the Salesforce REST API. Built with per-user OAuth 2.0 authentication and designed for deployment to **AWS Bedrock AgentCore**.

Every user authenticates as themselves — no shared service accounts or central credentials. All Salesforce API calls execute under the authenticated user's own access token, so Salesforce's native RBAC (profiles, permission sets, field-level security, sharing rules) applies automatically to every tool call.

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Salesforce Connected App Setup](#salesforce-connected-app-setup)
- [Local Development](#local-development)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Running the Server](#running-the-server)
  - [Connecting an MCP Client](#connecting-an-mcp-client)
- [AWS Deployment](#aws-deployment)
  - [Infrastructure Overview](#infrastructure-overview)
  - [Step 1: Configure Terraform Variables](#step-1-configure-terraform-variables)
  - [Step 2: Deploy Infrastructure](#step-2-deploy-infrastructure)
  - [Step 3: Build and Push the Container](#step-3-build-and-push-the-container)
  - [Step 4: Verify the Deployment](#step-4-verify-the-deployment)
- [MCP Tools Reference](#mcp-tools-reference)
- [Authentication Deep Dive](#authentication-deep-dive)
  - [OAuth 2.0 Flow](#oauth-20-flow)
  - [Token Lifecycle](#token-lifecycle)
  - [Compound Tokens](#compound-tokens)
  - [Sandbox vs. Production](#sandbox-vs-production)
- [Configuration Reference](#configuration-reference)
  - [Salesforce Settings](#salesforce-settings)
  - [MCP Server Settings](#mcp-server-settings)
- [Testing](#testing)
  - [Unit Tests](#unit-tests)
  - [Integration Tests](#integration-tests)
  - [Deployed Server Tests](#deployed-server-tests)
- [Project Structure](#project-structure)
- [Docker](#docker)
- [Development Guide](#development-guide)
  - [Makefile Commands](#makefile-commands)
  - [Code Quality](#code-quality)
  - [Adding a New Tool](#adding-a-new-tool)
- [Design Decisions](#design-decisions)

---

## Architecture

```
┌─────────────────┐       ┌──────────────────────────────────┐       ┌──────────────────┐
│   MCP Client    │       │     Salesforce MCP Server        │       │   Salesforce      │
│  (Claude, etc.) │       │                                  │       │   REST API        │
│                 │       │  ┌────────────────────────────┐  │       │                   │
│  1. Discover    │──────▶│  │ OAuth Routes (Starlette)   │  │       │  /services/data/  │
│     auth via    │       │  │ /.well-known/*             │  │       │  v66.0/           │
│     RFC 8414    │       │  │ /oauth/authorize           │  │       │                   │
│                 │       │  │ /oauth/callback            │  │       │  - /query         │
│  2. User logs   │──────▶│  │ /oauth/token               │  │       │  - /search        │
│     in via SF   │       │  └────────────────────────────┘  │       │  - /sobjects      │
│                 │       │                                  │       │  - /chatter       │
│  3. Tool calls  │──────▶│  ┌────────────────────────────┐  │──────▶│                   │
│     with Bearer │       │  │ RequireBearerToken (ASGI)  │  │       │                   │
│     token       │       │  │ FastMCP (Streamable HTTP)  │  │       │                   │
│                 │◀──────│  │ 7 Salesforce Tools         │  │◀──────│                   │
└─────────────────┘       │  └────────────────────────────┘  │       └──────────────────┘
                          │                                  │
                          │  Stateless — horizontally        │
                          │  scalable on AgentCore           │
                          └──────────────────────────────────┘
```

The server is a composite **Starlette** application with two layers:

1. **OAuth routes** — standard HTTP endpoints that broker the Salesforce Authorization Code flow on behalf of MCP clients.
2. **FastMCP application** — wrapped in `RequireBearerToken` ASGI middleware that enforces Bearer token presence and expiry before any tool call reaches FastMCP.

At runtime the server is fully **stateless**: no in-memory sessions, no caches, no sticky routing. Each request carries an encrypted compound token containing the user's Salesforce access token. This makes it safe to run behind a load balancer or on AgentCore where any container instance can handle any request.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ (3.13 recommended) | |
| [uv](https://github.com/astral-sh/uv) | latest | Fast Python package manager |
| Salesforce Connected App | — | OAuth 2.0 enabled (see [setup](#salesforce-connected-app-setup)) |
| AWS CLI | v2 | For deployment only |
| Terraform | >= 1.5.0 | For infrastructure provisioning |
| Docker | latest | For container builds |

---

## Salesforce Connected App Setup

Before running the server (locally or deployed), you need a Salesforce Connected App that grants OAuth access.

1. In Salesforce Setup, navigate to **App Manager** and click **New Connected App**.
2. Fill in basic info (name, contact email).
3. Under **API (Enable OAuth Settings)**:
   - Check **Enable OAuth Settings**.
   - **Callback URL**:
     - Local development: `http://localhost:8000/oauth/callback`
     - AWS deployment: `https://<your-agentcore-endpoint>/oauth/callback`
   - **Selected OAuth Scopes**:
     - `Access the identity URL service (id, profile, email, address, phone)` — `api`
     - `Perform requests at any time (refresh_token, offline_access)` — `refresh_token`
   - Optionally add `Access Chatter REST API resources (chatter_api)` for user info.
4. Save and wait for the app to propagate (can take 2-10 minutes).
5. Under **Manage Consumer Details**, note the **Consumer Key** (client ID) and **Consumer Secret** (client secret).

> **Sandbox note:** If you're developing against a sandbox org, create the Connected App in the sandbox directly or ensure it's deployed to the sandbox from production. Sandbox uses `https://test.salesforce.com` as the login URL.

---

## Local Development

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd salesforce-mcp-server

# Copy the local config template
cp .env.local.example .env

# Install all dependencies (including dev tools)
uv sync
```

### Configuration

Edit `.env` with your Salesforce Connected App credentials:

```dotenv
# Salesforce (Connected App — use a sandbox or developer edition)
SALESFORCE_INSTANCE_URL=https://myorg--sandbox.sandbox.my.salesforce.com
SALESFORCE_LOGIN_URL=https://test.salesforce.com
SALESFORCE_CLIENT_ID=<your Connected App consumer key>
SALESFORCE_CLIENT_SECRET=<your Connected App consumer secret>
SALESFORCE_API_VERSION=v66.0
SALESFORCE_ACCESS_TOKEN_TTL=7200

# MCP Server
MCP_SERVER_NAME=salesforce-mcp-server
MCP_SERVER_VERSION=1.0.0
MCP_LOG_LEVEL=DEBUG
MCP_LOG_FORMAT=text
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_PATH=/mcp
MCP_STATELESS=true
MCP_SECRET_PROVIDER=local

# OAuth proxy — server brokers Salesforce login for MCP clients
MCP_BASE_URL=http://localhost:8000
MCP_JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
MCP_AUTH_CODE_TTL=300
```

**Generate your JWT secret:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output into `MCP_JWT_SECRET`. This secret is used to encrypt/decrypt OAuth authorization codes and compound Bearer tokens using Fernet (AES-128-CBC + HMAC-SHA256).

### Running the Server

```bash
# Option 1: Using Make
make dev-server

# Option 2: Direct
uv run python -m mcp_server.server
```

The server starts on `http://localhost:8000` with:
- **MCP endpoint**: `http://localhost:8000/mcp` (Streamable HTTP transport)
- **OAuth discovery**: `http://localhost:8000/.well-known/oauth-authorization-server`
- **OAuth authorize**: `http://localhost:8000/oauth/authorize`
- **OAuth callback**: `http://localhost:8000/oauth/callback`
- **OAuth token**: `http://localhost:8000/oauth/token`

### Connecting an MCP Client

Any MCP-compatible client that supports Streamable HTTP transport and OAuth 2.0 can connect. The client will:

1. Discover auth endpoints via `GET /.well-known/oauth-authorization-server`
2. Optionally register itself via `POST /oauth/register` (RFC 7591 dynamic client registration)
3. Redirect the user to `/oauth/authorize` which redirects to Salesforce login
4. Receive an authorization code at the client's redirect URI
5. Exchange the code for an access token via `POST /oauth/token`
6. Use the access token as a `Bearer` header on all MCP tool calls to `/mcp`

**Example with Claude Desktop:** Configure your `claude_desktop_config.json` to point to `http://localhost:8000/mcp` as a Streamable HTTP MCP server. Claude will handle the OAuth flow automatically.

---

## AWS Deployment

### Infrastructure Overview

The Terraform configuration in `infra/terraform/` provisions three module groups:

| Module | Resources Created |
|---|---|
| **foundation** | ECR repository, Secrets Manager secret, IAM execution role (AgentCore + ECS), IAM CodeBuild role, S3 bucket for CodeBuild sources |
| **agentcore** | CloudWatch log group, Bedrock AgentCore runtime (via AWS CLI `null_resource`), optional CodeBuild project |
| **monitoring** | SNS topic (with optional email subscription), CloudWatch dashboard with log widget |

The AgentCore runtime is managed via `null_resource` provisioners using the AWS CLI because the Terraform AWS provider does not yet have native AgentCore support. The `external` data source queries the runtime status after creation.

### Step 1: Configure Terraform Variables

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
# Required
project_name = "salesforce-mcp-server"

# Optional overrides
# aws_region          = "us-east-2"
# environment         = "dev"
# container_image_tag = "latest"
# alarm_email         = "alerts@example.com"

# Salesforce Connected App credentials (stored in Secrets Manager)
salesforce_instance_url  = "https://myorg.my.salesforce.com"
salesforce_login_url     = "https://login.salesforce.com"
salesforce_client_id     = "<Connected App consumer key>"
salesforce_client_secret = "<Connected App consumer secret>"
# salesforce_api_version      = "v66.0"
# salesforce_access_token_ttl = 7200

# MCP credentials (stored in Secrets Manager)
mcp_jwt_secret = "<generate with: python -c \"import secrets; print(secrets.token_hex(32))\">"
mcp_base_url   = "https://<your-agentcore-endpoint>"

# If you already have an IAM role for AgentCore (e.g., from another deployment)
# execution_role_arn = "arn:aws:iam::123456789012:role/ExistingRole"
```

> **Note:** Sensitive values (`salesforce_client_id`, `salesforce_client_secret`, `mcp_jwt_secret`) are written to AWS Secrets Manager by Terraform and loaded at container startup. They are never baked into the container image.

### Step 2: Deploy Infrastructure

```bash
cd infra/terraform

# Initialize Terraform (downloads providers)
terraform init

# Preview what will be created
terraform plan

# Apply (creates ECR, Secrets Manager, IAM roles, AgentCore runtime, CloudWatch)
terraform apply
```

After `terraform apply` completes, note the outputs:

```
ecr_repository_url          = "<account>.dkr.ecr.us-east-2.amazonaws.com/bedrock-agentcore-salesforce-mcp-server-dev"
agentcore_runtime_id        = "<runtime-id>"
agentcore_runtime_arn       = "arn:aws:bedrock-agentcore:us-east-2:<account>:runtime/<runtime-name>"
agentcore_execution_role_arn = "arn:aws:iam::<account>:role/AgentCoreExecutionRole-..."
secrets_arn                 = "arn:aws:secretsmanager:us-east-2:<account>:secret:mcp/..."
```

### Step 3: Build and Push the Container

```bash
# Authenticate Docker with ECR
aws ecr get-login-password --region us-east-2 | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-2.amazonaws.com

# Build the image
docker build -t <ecr-url>:latest .

# Push to ECR
docker push <ecr-url>:latest
```

Replace `<ecr-url>` with the `ecr_repository_url` output from Terraform.

**Alternative: CodeBuild.** If Terraform created a CodeBuild project (when `execution_role_arn` is empty), you can trigger a build:

```bash
# Zip the source and upload to S3
zip -r source.zip . -x ".git/*" ".terraform/*" "*.tfstate*"
aws s3 cp source.zip s3://<codebuild-source-bucket>/source.zip

# Start the build
aws codebuild start-build --project-name bedrock-agentcore-salesforce-mcp-server-dev-builder
```

### Step 4: Verify the Deployment

The `tests/test_deployed.py` script sends SigV4-signed requests to your AgentCore runtime to verify it's running:

```bash
# Ensure AWS credentials are configured
python tests/test_deployed.py
```

This script tests:
1. `GET /health` — basic reachability
2. `POST` MCP `initialize` — JSON-RPC protocol handshake
3. `POST` with `X-Forwarded-Path` header — path-based routing

> **Important:** Update the `RUNTIME_ARN` constant in the script to match your deployed runtime ARN from the Terraform output.

---

## MCP Tools Reference

All tools call the Salesforce REST API at `/services/data/v66.0/` using the session user's access token. If the user lacks permission for an object or field, the Salesforce error is surfaced as-is to the MCP client.

### `soql_query`

Execute a SOQL query against Salesforce.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | Yes | A valid SOQL query string |

**Salesforce endpoint:** `GET /query?q={query}`

**Returns:** `{ totalSize, done, records[] }`

**Example:**
```
soql_query("SELECT Id, Name, Industry FROM Account WHERE Industry = 'Technology' LIMIT 10")
```

### `sosl_search`

Execute a full-text SOSL search across multiple objects.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | Yes | A valid SOSL search string |

**Salesforce endpoint:** `GET /search?q={query}`

**Returns:** `{ searchRecords[] }`

**Example:**
```
sosl_search("FIND {Acme} IN ALL FIELDS RETURNING Account(Id, Name), Contact(Id, Name)")
```

### `describe_global`

List all Salesforce objects (sobjects) the authenticated user can access.

| Parameter | Type | Required | Description |
|---|---|---|---|
| *(none)* | — | — | — |

**Salesforce endpoint:** `GET /sobjects`

**Returns:** `{ sobjects[] }` — each entry includes `name`, `label`, `queryable`, etc.

### `describe_sobject`

Get detailed metadata for a single Salesforce object including fields, relationships, and record types.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `sobject_name` | `string` | Yes | API name of the sobject (e.g., `"Account"`) |

**Salesforce endpoint:** `GET /sobjects/{name}/describe`

**Returns:** `{ name, fields[], childRelationships[], recordTypeInfos[] }`

### `get_record`

Fetch a single Salesforce record by its ID.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `sobject_name` | `string` | Yes | API name of the sobject |
| `record_id` | `string` | Yes | 15- or 18-character Salesforce record ID |
| `fields` | `list[string]` | No | Specific fields to retrieve (default: all accessible) |

**Salesforce endpoint:** `GET /sobjects/{name}/{id}?fields={fields}`

**Returns:** Record fields the user has field-level security access to.

### `get_related_records`

Fetch child/related records for a given parent record.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `sobject_name` | `string` | Yes | API name of the parent sobject |
| `record_id` | `string` | Yes | Record ID of the parent |
| `relationship_name` | `string` | Yes | Relationship name (e.g., `"Contacts"`, `"Opportunities"`) |
| `fields` | `list[string]` | No | Specific fields to retrieve on related records |

**Salesforce endpoint:** `GET /sobjects/{name}/{id}/{relationship}`

**Returns:** `{ totalSize, done, records[] }`

### `get_user_info`

Get the currently authenticated Salesforce user's profile information.

| Parameter | Type | Required | Description |
|---|---|---|---|
| *(none)* | — | — | — |

**Salesforce endpoint:** `GET /chatter/users/me`

**Returns:** `{ id, name, email, username, ... }`

---

## Authentication Deep Dive

### OAuth 2.0 Flow

The server acts as an **OAuth 2.0 authorization server proxy**. It doesn't store passwords or manage user accounts — it brokers Salesforce's Authorization Code flow:

```
MCP Client                    MCP Server                    Salesforce
    │                              │                              │
    │ 1. GET /.well-known/         │                              │
    │    oauth-authorization-server│                              │
    │─────────────────────────────▶│                              │
    │◀─────────────────────────────│                              │
    │   { authorization_endpoint,  │                              │
    │     token_endpoint, ... }    │                              │
    │                              │                              │
    │ 2. GET /oauth/authorize      │                              │
    │    ?redirect_uri=...&state=..│                              │
    │─────────────────────────────▶│                              │
    │                              │ 3. 302 to Salesforce login   │
    │                              │─────────────────────────────▶│
    │                              │                              │
    │                              │      User logs in to SF      │
    │                              │                              │
    │                              │ 4. SF redirects to           │
    │                              │    /oauth/callback?code=...  │
    │                              │◀─────────────────────────────│
    │                              │                              │
    │                              │ 5. POST SF /oauth2/token     │
    │                              │    (exchange code for token)  │
    │                              │─────────────────────────────▶│
    │                              │◀─────────────────────────────│
    │                              │    { access_token, refresh }  │
    │                              │                              │
    │ 6. Redirect to client with   │                              │
    │    encrypted auth code       │                              │
    │◀─────────────────────────────│                              │
    │                              │                              │
    │ 7. POST /oauth/token         │                              │
    │    { code: <encrypted> }     │                              │
    │─────────────────────────────▶│                              │
    │◀─────────────────────────────│                              │
    │   { access_token: <compound>,│                              │
    │     refresh_token, ... }     │                              │
    │                              │                              │
    │ 8. Tool calls with Bearer    │ 9. Decrypt, forward to SF    │
    │─────────────────────────────▶│─────────────────────────────▶│
    │◀─────────────────────────────│◀─────────────────────────────│
```

### Token Lifecycle

1. **Authorization code** (step 6): The server encrypts the Salesforce token response into a Fernet-encrypted blob with a TTL of `MCP_AUTH_CODE_TTL` seconds (default: 300). This is a one-time-use code handed to the MCP client.

2. **Compound Bearer token** (step 7 onward): When the client exchanges the auth code via `POST /oauth/token`, the server returns an encrypted compound token containing:
   - `access_token` — the real Salesforce access token
   - `refresh_token` — the Salesforce refresh token
   - `instance_url` — the Salesforce instance URL
   - `iat` — issued-at timestamp

3. **Token expiry**: The `RequireBearerToken` middleware checks `iat + SALESFORCE_ACCESS_TOKEN_TTL` against the current time. If expired, it returns HTTP 401 which triggers the client's refresh flow.

4. **Refresh flow**: The client sends `grant_type=refresh_token` to `POST /oauth/token`. The server uses the Salesforce refresh token to get a new access token from Salesforce and returns a fresh compound token.

### Compound Tokens

All tokens are encrypted using **Fernet** (from the `cryptography` library), which provides:
- AES-128-CBC encryption
- HMAC-SHA256 authentication
- The encryption key is derived from `MCP_JWT_SECRET` via SHA-256

This means tokens are opaque to the MCP client and tamper-proof. Even if intercepted, the Salesforce access token cannot be extracted without the server's secret.

### Sandbox vs. Production

Switching between sandbox and production requires updating four environment variables:

| Variable | Production | Sandbox |
|---|---|---|
| `SALESFORCE_INSTANCE_URL` | `https://myorg.my.salesforce.com` | `https://myorg--sandbox.sandbox.my.salesforce.com` |
| `SALESFORCE_LOGIN_URL` | `https://login.salesforce.com` | `https://test.salesforce.com` |
| `SALESFORCE_CLIENT_ID` | Production Connected App key | Sandbox Connected App key |
| `SALESFORCE_CLIENT_SECRET` | Production Connected App secret | Sandbox Connected App secret |

For AWS deployments, update these values in Secrets Manager (or re-run `terraform apply` with updated `terraform.tfvars`).

---

## Configuration Reference

Configuration is managed via [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) which reads from environment variables and `.env` files. Two settings classes are used:

### Salesforce Settings

Environment variable prefix: `SALESFORCE_`

| Variable | Default | Description |
|---|---|---|
| `SALESFORCE_INSTANCE_URL` | *(required)* | Your Salesforce org URL (e.g., `https://myorg.my.salesforce.com`) |
| `SALESFORCE_LOGIN_URL` | `https://login.salesforce.com` | OAuth login endpoint. Use `https://test.salesforce.com` for sandboxes |
| `SALESFORCE_CLIENT_ID` | *(required for OAuth)* | Connected App consumer key |
| `SALESFORCE_CLIENT_SECRET` | *(required for OAuth)* | Connected App consumer secret |
| `SALESFORCE_API_VERSION` | `v66.0` | Salesforce REST API version |
| `SALESFORCE_AUTH_TIMEOUT` | `10` | Timeout in seconds for OAuth HTTP calls to Salesforce |
| `SALESFORCE_ACCESS_TOKEN` | `""` | Direct access token for local dev (bypasses OAuth; used when headers don't contain a Bearer token) |
| `SALESFORCE_ACCESS_TOKEN_TTL` | `7200` | Compound token lifetime in seconds before 401 triggers refresh |

### MCP Server Settings

Environment variable prefix: `MCP_`

| Variable | Default | Description |
|---|---|---|
| `MCP_SERVER_NAME` | `salesforce-mcp-server` | Server name (appears in logs and MCP metadata) |
| `MCP_SERVER_VERSION` | `1.0.0` | Server version |
| `MCP_HOST` | `0.0.0.0` | Bind address |
| `MCP_PORT` | `8000` | Bind port |
| `MCP_PATH` | `/mcp` | Streamable HTTP path for MCP protocol |
| `MCP_STATELESS` | `true` | Stateless mode for horizontal scaling |
| `MCP_LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `MCP_LOG_FORMAT` | `json` | Log format: `json` (structured for CloudWatch) or `text` (human-readable for local dev) |
| `MCP_BASE_URL` | `http://localhost:8000` | Public base URL (used in OAuth metadata and 401 response headers) |
| `MCP_JWT_SECRET` | `""` | Secret key for Fernet encryption of OAuth codes and compound tokens |
| `MCP_AUTH_CODE_TTL` | `300` | Authorization code lifetime in seconds |
| `MCP_SECRET_PROVIDER` | `local` | `local` (reads from `.env`) or `aws` (loads from Secrets Manager at startup) |
| `MCP_AWS_SECRET_NAME` | `mcp/api-keys` | AWS Secrets Manager secret name (only used when `MCP_SECRET_PROVIDER=aws`) |
| `MCP_AWS_SECRET_REGION` | `us-east-2` | AWS region for Secrets Manager |

### Environment File Templates

- **`.env.local.example`** — Template for local development. Uses `MCP_SECRET_PROVIDER=local`, `MCP_LOG_FORMAT=text`, and `MCP_LOG_LEVEL=DEBUG`.
- **`.env.example`** — Template for AWS deployment. Uses `MCP_SECRET_PROVIDER=aws`, `MCP_LOG_FORMAT=json`, and references Secrets Manager for all sensitive values.

---

## Testing

The project uses [pytest](https://docs.pytest.org/) with [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) for async test support and [pytest-cov](https://github.com/pytest-dev/pytest-cov) for coverage reporting.

### Unit Tests

Unit tests mock the Salesforce client and verify each MCP tool calls the correct client method with the correct arguments.

```bash
# Run unit tests
make test-unit

# Or directly
uv run pytest tests/unit -v
```

Unit tests are in `tests/unit/test_tools.py` and cover all seven tools. Shared fixtures (`mock_salesforce_client`, `mock_context`, `patch_get_client`) are defined in `tests/conftest.py`.

### Integration Tests

Integration tests run against a **real Salesforce org**. They require a valid access token.

```bash
# Set your token and Salesforce instance URL
export SALESFORCE_ACCESS_TOKEN=<your-salesforce-access-token>
export SALESFORCE_INSTANCE_URL=https://myorg--sandbox.sandbox.my.salesforce.com

# Run integration tests
make test-int

# Or directly
uv run pytest tests/integration -v
```

Integration tests are automatically **skipped** if `SALESFORCE_ACCESS_TOKEN` is not set.

### Deployed Server Tests

The `tests/test_deployed.py` script validates a deployed AgentCore runtime by sending SigV4-signed HTTP requests:

```bash
# Ensure AWS credentials are configured (aws configure or SSO)
python tests/test_deployed.py
```

Before running, update the `RUNTIME_ARN` constant in the script to match your runtime from the Terraform `agentcore_runtime_arn` output.

### Run All Tests

```bash
# Run everything (unit + integration if token is set)
make test

# Or directly with coverage
uv run pytest
```

Coverage is reported automatically via `pytest-cov` (configured in `pyproject.toml`).

---

## Project Structure

```
salesforce-mcp-server/
├── mcp_server/                    # Python package — the MCP server
│   ├── __init__.py                # Package init (exports __version__)
│   ├── server.py                  # Entry point: Starlette app, FastMCP, middleware, lifespan
│   ├── config/
│   │   ├── __init__.py            # Exports settings singletons
│   │   └── settings.py            # Pydantic Settings classes (SalesforceSettings, MCPSettings)
│   ├── oauth/
│   │   ├── __init__.py
│   │   └── routes.py              # RFC 8414/7591/9470 OAuth endpoints (Starlette Routes)
│   ├── salesforce/
│   │   ├── __init__.py            # Exports SalesforceClient, get_salesforce_client
│   │   ├── auth.py                # Bearer extraction, Fernet token helpers, SF OAuth exchange
│   │   └── client.py              # Async Salesforce REST API client (httpx)
│   └── tools/
│       ├── __init__.py            # register_tools() — registers all 7 tools with FastMCP
│       ├── soql_query.py          # SOQL query execution
│       ├── sosl_search.py         # SOSL full-text search
│       ├── describe_global.py     # List all accessible sobjects
│       ├── describe_sobject.py    # Sobject metadata (fields, relationships, record types)
│       ├── get_record.py          # Single record fetch by ID
│       ├── get_related_records.py # Related/child record fetch
│       └── get_user_info.py       # Authenticated user profile
│
├── tests/                         # Test suite
│   ├── __init__.py
│   ├── conftest.py                # Shared pytest fixtures (mock client, mock context)
│   ├── test_deployed.py           # SigV4-signed smoke test for deployed AgentCore runtime
│   ├── unit/
│   │   ├── __init__.py
│   │   └── test_tools.py          # Unit tests for all 7 MCP tools
│   └── integration/
│       ├── __init__.py
│       └── test_server.py         # Integration tests against a real Salesforce org
│
├── infra/                         # Infrastructure as Code
│   └── terraform/
│       ├── main.tf                # Root module — wires foundation, agentcore, monitoring
│       ├── variables.tf           # Input variables (region, project, SF creds, etc.)
│       ├── outputs.tf             # Outputs (ECR URL, runtime ARN, secrets ARN, next steps)
│       ├── terraform.tfvars.example # Template for variable values
│       └── modules/
│           ├── foundation/        # ECR, Secrets Manager, IAM roles, CodeBuild role, S3
│           │   ├── main.tf
│           │   ├── variables.tf
│           │   └── outputs.tf
│           ├── agentcore/         # AgentCore runtime (AWS CLI), CloudWatch logs, CodeBuild
│           │   ├── main.tf
│           │   ├── variables.tf
│           │   └── outputs.tf
│           └── monitoring/        # SNS alerts, CloudWatch dashboard
│               ├── main.tf
│               ├── variables.tf
│               └── outputs.tf
│
├── .bedrock_agentcore.yaml        # AgentCore deployment configuration
├── .env.example                   # Environment template for AWS deployment
├── .env.local.example             # Environment template for local development
├── .gitignore                     # Git ignore rules
├── Dockerfile                     # Production container (Python 3.13-slim + uv)
├── Makefile                       # Development task runner
├── pyproject.toml                 # Project metadata, dependencies, tool config
└── uv.lock                        # Locked dependency versions
```

---

## Docker

The `Dockerfile` produces a production-ready container based on `python:3.13-slim`:

```bash
# Build
docker build -t salesforce-mcp-server:latest .

# Run locally with your .env file
docker run -p 8000:8000 --env-file .env salesforce-mcp-server:latest
```

Key aspects of the Docker build:
- Uses **multi-stage layer caching**: dependency files (`pyproject.toml`, `uv.lock`) are copied first and installed before application code, so code changes don't invalidate the dependency layer.
- Installs [uv](https://github.com/astral-sh/uv) from the official image (`ghcr.io/astral-sh/uv:latest`) for fast, reproducible installs.
- Sets `MCP_SECRET_PROVIDER=aws` and `MCP_AWS_SECRET_NAME=mcp/salesforce-mcp-server/api-keys` by default — override via environment variables for local Docker runs.
- Health check runs `curl -f http://localhost:8000/health` every 30 seconds.

---

## Development Guide

### Makefile Commands

| Command | Description |
|---|---|
| `make help` | Show all available targets |
| `make install` | Install dependencies with `uv sync` |
| `make dev-server` | Run the MCP server locally |
| `make dev` | Install + run (convenience target) |
| `make test` | Run all tests with coverage |
| `make test-unit` | Run unit tests only |
| `make test-int` | Run integration tests (requires `SALESFORCE_ACCESS_TOKEN`) |
| `make lint` | Run ruff linter |
| `make format` | Auto-fix lint issues and format code |
| `make build` | Build the Docker image |
| `make deploy` | Run `terraform init && terraform apply` in `infra/terraform/` |
| `make clean` | Remove `__pycache__`, `.pytest_cache`, `.ruff_cache` |

### Code Quality

The project uses [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check for issues
make lint

# Auto-fix and format
make format
```

Ruff is configured in `pyproject.toml` with:
- Line length: 100
- Target: Python 3.11
- Rules: `E` (pycodestyle errors), `F` (pyflakes), `I` (isort), `UP` (pyupgrade), `B` (bugbear), `SIM` (simplify)
- Double-quote style

### Adding a New Tool

1. **Create the tool file** in `mcp_server/tools/`:

```python
from mcp.server.fastmcp import Context, FastMCP
from mcp_server.salesforce.auth import get_salesforce_client


def register_my_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    async def my_tool(param: str, ctx: Context) -> dict:
        """Tool description shown to the MCP client.

        Args:
            param: Description of the parameter.

        Returns:
            Description of the return value.
        """
        client = get_salesforce_client(ctx)
        return await client._request("GET", "/some/endpoint")
```

2. **Register it** in `mcp_server/tools/__init__.py`:

```python
from mcp_server.tools.my_tool import register_my_tool

def register_tools(mcp: FastMCP) -> None:
    # ... existing registrations ...
    register_my_tool(mcp)
```

3. **Add unit tests** in `tests/unit/test_tools.py` following the existing pattern.

---

## Design Decisions

### Stateless Architecture

The server runs in **stateless mode** (`MCP_STATELESS=true`) for AgentCore compatibility:
- No in-memory caching or sessions between requests.
- Each request may be handled by a different container instance.
- The Salesforce Bearer token is extracted and decrypted from each request independently.
- This enables horizontal scaling with zero coordination between instances.

### Per-User Authentication

Rather than using a single service account, each user authenticates with their own Salesforce credentials. This means:
- **Salesforce RBAC is enforced natively** — profiles, permission sets, field-level security, and sharing rules all apply automatically.
- **Audit trails** in Salesforce show the actual user who made each API call.
- **No privilege escalation** — users can only access what their Salesforce profile allows.

### Read-Only Access

All tools are read-only by design. The server does not expose any create, update, or delete operations on Salesforce records. This reduces the blast radius of any misconfiguration or security issue.

### DNS Rebinding Protection Disabled

DNS rebinding protection is explicitly disabled in the FastMCP `TransportSecuritySettings`. This is required for AgentCore deployments where internal routing uses hostnames that would be rejected by default Host header validation. Since the server runs behind AWS IAM authentication in production, this is safe.

### Fernet over JWT

The server uses Fernet encryption (AES-128-CBC + HMAC-SHA256) for tokens instead of standard JWTs. This ensures the Salesforce access token is **encrypted** (not just signed) and cannot be read by the MCP client or any intermediary. The `MCP_JWT_SECRET` setting name is a historical artifact — the actual mechanism is symmetric encryption, not JWT signing.
