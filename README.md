# Salesforce MCP Server

A production-ready [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that provides **read-only** access to the Salesforce REST API. Built with per-user OAuth 2.0 authentication and designed for deployment to **AWS Lambda**.

Every user authenticates as themselves — no shared service accounts or central credentials. All Salesforce API calls execute under the authenticated user's own access token, so Salesforce's native RBAC (profiles, permission sets, field-level security, sharing rules) applies automatically to every tool call.

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Salesforce Connected App Setup](#salesforce-connected-app-setup)
- [Local Development](#local-development)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Getting a Salesforce Access Token](#getting-a-salesforce-access-token)
  - [Running the Server](#running-the-server)
  - [Connecting an MCP Client](#connecting-an-mcp-client)
- [AWS Deployment](#aws-deployment)
  - [Infrastructure Overview](#infrastructure-overview)
  - [Step 1: Build the Lambda Zip](#step-1-build-the-lambda-zip)
  - [Step 2: Configure Terraform Variables](#step-2-configure-terraform-variables)
  - [Step 3: Deploy Infrastructure](#step-3-deploy-infrastructure)
  - [Step 4: Populate Secrets Manager](#step-4-populate-secrets-manager)
  - [Step 5: Update Salesforce Connected App](#step-5-update-salesforce-connected-app)
  - [Step 6: Verify the Deployment](#step-6-verify-the-deployment)
  - [Quick Deploy via CLI (Existing Lambda)](#quick-deploy-via-cli-existing-lambda)
- [MCP Tools Reference](#mcp-tools-reference)
- [Authentication Deep Dive](#authentication-deep-dive)
  - [OAuth 2.0 Flow](#oauth-20-flow)
  - [Token Lifecycle](#token-lifecycle)
  - [Compound Tokens](#compound-tokens)
  - [Sandbox vs. Production](#sandbox-vs-production)
- [Configuration Reference](#configuration-reference)
  - [Secrets Manager Keys (Production)](#secrets-manager-keys-production)
  - [Environment Variables (Local)](#environment-variables-local)
- [Testing](#testing)
  - [Unit Tests](#unit-tests)
  - [Integration Tests](#integration-tests)
- [Project Structure](#project-structure)
- [Development Guide](#development-guide)
  - [Makefile Commands](#makefile-commands)
  - [Code Quality](#code-quality)
  - [Adding a New Tool](#adding-a-new-tool)
- [Design Decisions](#design-decisions)

---

## Architecture

```
┌─────────────────┐       ┌──────────────────────────────────┐       ┌──────────────────┐
│   MCP Client    │       │  AWS Lambda (Function URL)       │       │   Salesforce      │
│  (Claude, etc.) │       │                                  │       │   REST API        │
│                 │       │  ┌────────────────────────────┐  │       │                   │
│  1. Discover    │──────▶│  │ OAuth Routes (Starlette)   │  │       │  /services/data/  │
│     auth via    │       │  │ /.well-known/*             │  │       │  vXX.0/           │
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
                          │  Config: AWS Secrets Manager     │
                          │  Stateless — scales to zero      │
                          └──────────────────────────────────┘
```

The server is a composite **Starlette** ASGI application with two layers, wrapped by **Mangum** for Lambda compatibility:

1. **OAuth routes** — standard HTTP endpoints that broker the Salesforce Authorization Code flow on behalf of MCP clients.
2. **FastMCP application** — wrapped in `RequireBearerToken` ASGI middleware that enforces Bearer token presence and expiry before any tool call reaches FastMCP.

At runtime the server is fully **stateless**: no in-memory sessions, no caches, no sticky routing. Each request carries an encrypted compound token containing the user's Salesforce access token. This enables horizontal scaling with zero coordination — Lambda can invoke as many concurrent instances as needed.

All configuration (including non-sensitive values like API versions) is centralized in **AWS Secrets Manager** and pulled by Lambda at cold start.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ (3.13 recommended) | Lambda runtime uses 3.13 |
| [uv](https://github.com/astral-sh/uv) | latest | Fast Python package manager |
| Salesforce Connected App | — | OAuth 2.0 enabled (see [setup](#salesforce-connected-app-setup)) |
| AWS CLI | v2 | For CLI deployments |
| Terraform | >= 1.5.0 | For infrastructure provisioning |

---

## Salesforce Connected App Setup

Before running the server (locally or deployed), you need a Salesforce Connected App that grants OAuth access.

1. In Salesforce Setup, navigate to **App Manager** and click **New Connected App**.
2. Fill in basic info (name, contact email).
3. Under **API (Enable OAuth Settings)**:
   - Check **Enable OAuth Settings**.
   - **Callback URL**:
     - Local development: `http://localhost:8000/oauth/callback`
     - AWS deployment: `https://<lambda-function-url>/oauth/callback`
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
git clone <repo-url>
cd salesforce-mcp-server

cp .env.example .env

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

### Getting a Salesforce Access Token

For local development you can skip the full OAuth flow by providing a raw Salesforce access token. A helper script automates this — it opens the Salesforce login page in your browser and captures the token:

```bash
# Using Make
make local-token

# Or directly
python scripts/local-dev.py
```

The script will:

1. Read your Connected App credentials from `.env`
2. Start a temporary local server on `http://localhost:8000`
3. Open the Salesforce login page in your browser
4. Wait for you to log in
5. Exchange the callback code for an access token
6. Print the token for you to copy into `.env`

After running, paste the token into your `.env`:

```dotenv
SALESFORCE_ACCESS_TOKEN=00DAu000...
```

> **Note:** Make sure the MCP dev server isn't already running on port 8000 when using this script, since it starts its own temporary server on the same port to match the Connected App callback URL (`http://localhost:8000/oauth/callback`).

With `SALESFORCE_ACCESS_TOKEN` set, the server uses it as a fallback when no Bearer header is present in the request, bypassing the full OAuth flow for local testing.

### Running the Server

```bash
# Option 1: Using Make
make dev-server

# Option 2: Direct
uv run python -m mcp_server.server
```

The server starts on `http://localhost:8000` with:

| Endpoint | Purpose |
|---|---|
| `http://localhost:8000/mcp` | MCP endpoint (Streamable HTTP transport) |
| `http://localhost:8000/health` | Health check |
| `http://localhost:8000/.well-known/oauth-authorization-server` | OAuth discovery (RFC 8414) |
| `http://localhost:8000/.well-known/openid-configuration` | OIDC discovery alias |
| `http://localhost:8000/.well-known/oauth-protected-resource` | Protected resource metadata (RFC 9470) |
| `http://localhost:8000/oauth/authorize` | OAuth authorization |
| `http://localhost:8000/oauth/callback` | Salesforce callback |
| `http://localhost:8000/oauth/token` | Token exchange |
| `http://localhost:8000/oauth/register` | Dynamic client registration (RFC 7591) |

### Connecting an MCP Client

Any MCP-compatible client that supports Streamable HTTP transport and OAuth 2.0 can connect. The client will:

1. Discover auth endpoints via `GET /.well-known/oauth-authorization-server`
2. Optionally register itself via `POST /oauth/register` (RFC 7591 dynamic client registration)
3. Redirect the user to `/oauth/authorize` which redirects to Salesforce login
4. Receive an authorization code at the client's redirect URI
5. Exchange the code for an access token via `POST /oauth/token`
6. Use the access token as a `Bearer` header on all MCP tool calls to `/mcp`

**Claude Desktop / Claude.ai:** Add as a remote MCP connector using the server URL (e.g., `http://localhost:8000/mcp` for local, or the Lambda Function URL for production). Claude handles the OAuth flow automatically.

---

## AWS Deployment

### Infrastructure Overview

The Terraform configuration in `infra/terraform/` provisions everything needed for a self-contained Lambda deployment:

| Module | Resources Created |
|---|---|
| **foundation** | Secrets Manager secret (empty — values managed via Console) |
| **mcp_server** (`modules/oauth_proxy`) | IAM role + policies, Lambda function (ARM64, Python 3.13), Function URL (public), CloudWatch log group |
| **monitoring** | SNS topic (optional email subscription), CloudWatch dashboard |

The Lambda function name is derived from `${project_name}-${environment}` (e.g., `salesforce-mcp-server-prod`). This same pattern applies to the IAM role, log group, and dashboard.

### Step 1: Build the Lambda Zip

```bash
# On macOS/Linux
bash build-lambda.sh

# On Windows (PowerShell)
uv pip install `
  --python-platform manylinux2014_aarch64 `
  --target .lambda-build `
  --python-version 3.13 `
  --only-binary :all: `
  mangum httpx starlette anyio cryptography python-multipart `
  pydantic pydantic-settings python-dotenv boto3 mcp uvicorn

Copy-Item -Recurse -Force mcp_server .lambda-build\mcp_server
Compress-Archive -Path .lambda-build\* -DestinationPath lambda.zip -Force
```

This produces `lambda.zip` (~23 MB) containing all runtime dependencies compiled for Lambda's ARM64 Python 3.13 environment plus the `mcp_server/` package. The Lambda handler is `mcp_server.server.handler`.

### Step 2: Configure Terraform Variables

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
# Required
project_name = "salesforce-mcp-server"

# Optional — customize for your environment
# aws_region      = "us-east-2"
# environment     = "prod"
# alarm_email     = "alerts@example.com"

# Lambda deployment (local zip or S3)
lambda_zip_path = "../../lambda.zip"
# lambda_s3_bucket = "my-deployment-bucket"
# lambda_s3_key    = "salesforce-mcp-server/lambda.zip"
```

For team or production environments, uncomment the **S3 backend** block in `main.tf` to enable remote state with locking:

```hcl
backend "s3" {
  bucket         = "your-terraform-state-bucket"
  key            = "mcp-server/terraform.tfstate"
  region         = "us-east-2"
  dynamodb_table = "terraform-locks"
  encrypt        = true
}
```

### Step 3: Deploy Infrastructure

```bash
cd infra/terraform

terraform init
terraform plan
terraform apply
```

After `terraform apply` completes, note the outputs:

```
function_url    = "https://<id>.lambda-url.<region>.on.aws/"
mcp_server_url  = "https://<id>.lambda-url.<region>.on.aws/mcp"
secrets_arn     = "arn:aws:secretsmanager:<region>:<account>:secret:mcp/..."
lambda_role_arn = "arn:aws:iam::<account>:role/salesforce-mcp-server-prod-role"
function_name   = "salesforce-mcp-server-prod"
```

### Step 4: Populate Secrets Manager

Terraform creates the secret but leaves it **empty**. Go to the AWS Console and add these key/value pairs:

| Key | Value | Required |
|---|---|---|
| `SALESFORCE_INSTANCE_URL` | `https://myorg.my.salesforce.com` | Yes |
| `SALESFORCE_LOGIN_URL` | `https://login.salesforce.com` (or `https://test.salesforce.com` for sandbox) | Yes |
| `SALESFORCE_CLIENT_ID` | Connected App consumer key | Yes |
| `SALESFORCE_CLIENT_SECRET` | Connected App consumer secret | Yes |
| `SALESFORCE_API_VERSION` | `v66.0` | Yes |
| `SALESFORCE_ACCESS_TOKEN_TTL` | `7200` (seconds) | Yes |
| `MCP_JWT_SECRET` | Random hex string (see [Configuration](#configuration)) | Yes |
| `MCP_BASE_URL` | The `function_url` from Terraform output (e.g., `https://<id>.lambda-url.<region>.on.aws/`) | Yes |

> **Important:** After updating secrets, force a Lambda cold start so it picks up the new values. The simplest way is to update the function's description via CLI: `aws lambda update-function-configuration --function-name <name> --description "refreshed secrets"`

### Step 5: Update Salesforce Connected App

Set the callback URL in your Connected App to:

```
https://<lambda-function-url>/oauth/callback
```

Use the `function_url` value from the Terraform output.

### Step 6: Verify the Deployment

```bash
# Health check
curl https://<function-url>/health
# Expected: {"status":"ok","server":"salesforce-mcp-server"}

# OAuth discovery
curl https://<function-url>/.well-known/oauth-authorization-server
# Expected: JSON with authorization_endpoint, token_endpoint, etc.

# Connect in Claude using:
# https://<function-url>/mcp
```

### Quick Deploy via CLI (Existing Lambda)

If the infrastructure already exists and you just need to update the code:

```bash
# Build and deploy in one step
make deploy

# Or manually
bash build-lambda.sh
aws lambda update-function-code \
  --function-name salesforce-mcp-server-prod \
  --zip-file fileb://lambda.zip \
  --region us-east-2 \
  --profile your-profile
```

The Makefile defaults can be overridden: `make deploy FUNCTION_NAME=my-func REGION=us-west-2 PROFILE=prod`.

---

## MCP Tools Reference

All tools call the Salesforce REST API using the session user's access token. If the user lacks permission for an object or field, the Salesforce error is surfaced as-is to the MCP client.

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
MCP Client                    MCP Server (Lambda)               Salesforce
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

Switching between sandbox and production requires updating these values in Secrets Manager (or `.env` for local):

| Key | Production | Sandbox |
|---|---|---|
| `SALESFORCE_INSTANCE_URL` | `https://myorg.my.salesforce.com` | `https://myorg--sandbox.sandbox.my.salesforce.com` |
| `SALESFORCE_LOGIN_URL` | `https://login.salesforce.com` | `https://test.salesforce.com` |
| `SALESFORCE_CLIENT_ID` | Production Connected App key | Sandbox Connected App key |
| `SALESFORCE_CLIENT_SECRET` | Production Connected App secret | Sandbox Connected App secret |

After updating Secrets Manager, force a Lambda cold start so the new values take effect.

---

## Configuration Reference

### Secrets Manager Keys (Production)

On AWS, all configuration is stored in a single Secrets Manager secret and loaded at Lambda cold start. The secret name follows the pattern `mcp/<project-name>/api-keys`.

| Key | Description |
|---|---|
| `SALESFORCE_INSTANCE_URL` | Your Salesforce org URL (e.g., `https://myorg.my.salesforce.com`) |
| `SALESFORCE_LOGIN_URL` | OAuth login endpoint (`https://login.salesforce.com` or `https://test.salesforce.com`) |
| `SALESFORCE_CLIENT_ID` | Connected App consumer key |
| `SALESFORCE_CLIENT_SECRET` | Connected App consumer secret |
| `SALESFORCE_API_VERSION` | Salesforce REST API version (e.g., `v66.0`) |
| `SALESFORCE_ACCESS_TOKEN_TTL` | Compound token lifetime in seconds before 401 triggers refresh |
| `MCP_JWT_SECRET` | Secret key for Fernet encryption of OAuth codes and compound tokens |
| `MCP_BASE_URL` | Public Lambda Function URL (used in OAuth metadata and 401 headers) |

The Lambda function itself has only bootstrap environment variables that tell it where to find the secret:

| Env Var | Value |
|---|---|
| `MCP_SECRET_PROVIDER` | `aws` |
| `MCP_AWS_SECRET_NAME` | `mcp/<project>/api-keys` |
| `MCP_AWS_SECRET_REGION` | AWS region |
| `MCP_LOG_LEVEL` | `INFO` |
| `MCP_LOG_FORMAT` | `json` |
| `MCP_STATELESS` | `true` |

### Environment Variables (Local)

For local development, configuration is read from a `.env` file. Copy `.env.example` to `.env` and fill in values.

| Variable | Default | Description |
|---|---|---|
| `SALESFORCE_INSTANCE_URL` | *(required)* | Your Salesforce org URL |
| `SALESFORCE_LOGIN_URL` | `https://login.salesforce.com` | OAuth login endpoint |
| `SALESFORCE_CLIENT_ID` | *(required for OAuth)* | Connected App consumer key |
| `SALESFORCE_CLIENT_SECRET` | *(required for OAuth)* | Connected App consumer secret |
| `SALESFORCE_API_VERSION` | `v66.0` | Salesforce REST API version |
| `SALESFORCE_ACCESS_TOKEN` | `""` | Direct access token for local dev (bypasses OAuth) |
| `SALESFORCE_ACCESS_TOKEN_TTL` | `7200` | Compound token lifetime in seconds |
| `SALESFORCE_AUTH_TIMEOUT` | `10` | Timeout for OAuth HTTP calls to Salesforce |
| `MCP_SERVER_NAME` | `salesforce-mcp-server` | Server name (appears in logs and MCP metadata) |
| `MCP_SERVER_VERSION` | `1.0.0` | Server version |
| `MCP_HOST` | `0.0.0.0` | Bind address |
| `MCP_PORT` | `8000` | Bind port |
| `MCP_PATH` | `/mcp` | Streamable HTTP path |
| `MCP_STATELESS` | `true` | Stateless mode for horizontal scaling |
| `MCP_LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `MCP_LOG_FORMAT` | `json` | `json` (structured) or `text` (human-readable) |
| `MCP_BASE_URL` | `http://localhost:8000` | Public base URL (used in OAuth metadata) |
| `MCP_JWT_SECRET` | `""` | Fernet encryption key |
| `MCP_AUTH_CODE_TTL` | `300` | Authorization code lifetime in seconds |
| `MCP_SECRET_PROVIDER` | `local` | `local` (reads `.env`) or `aws` (loads from Secrets Manager) |
| `MCP_AWS_SECRET_NAME` | `mcp/api-keys` | Secrets Manager secret name (only when `aws`) |
| `MCP_AWS_SECRET_REGION` | `us-east-2` | AWS region for Secrets Manager |

---

## Testing

The project uses [pytest](https://docs.pytest.org/) with [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) for async test support and [pytest-cov](https://github.com/pytest-dev/pytest-cov) for coverage reporting. The unit test suite contains **63 tests** covering tools, auth, OAuth routes, middleware, and secrets loading.

### Unit Tests

```bash
make test-unit

# Or directly
uv run pytest tests/unit -v
```

Unit tests are organized by module:

| Test File | What It Covers | Tests |
|---|---|---|
| `test_tools.py` | All 7 MCP tools (SOQL, SOSL, describe, get record, etc.) | 8 |
| `test_auth.py` | Fernet token encode/decode, auth codes, OAuth state, Bearer parsing, `get_salesforce_client`, SF token exchange/refresh | 26 |
| `test_oauth_routes.py` | OAuth discovery (RFC 8414/9470), OIDC alias, dynamic registration, authorize redirect, callback, token exchange (auth code + refresh) | 18 |
| `test_server.py` | `/health` endpoint, `RequireBearerToken` middleware (missing/expired/raw tokens, 401 responses), `_load_aws_secrets()` (happy path, ClientError, invalid JSON, missing keys) | 11 |

Shared fixtures (`mock_salesforce_client`, `mock_context`, `patch_get_client`) are defined in `tests/conftest.py`.

### Integration Tests

Integration tests run against a **real Salesforce org**. They require a valid access token.

```bash
export SALESFORCE_ACCESS_TOKEN=<your-salesforce-access-token>
export SALESFORCE_INSTANCE_URL=https://myorg--sandbox.sandbox.my.salesforce.com

make test-int

# Or directly
uv run pytest tests/integration -v
```

Integration tests are automatically **skipped** if `SALESFORCE_ACCESS_TOKEN` is not set.

### Run All Tests

```bash
make test

# Or directly with coverage
uv run pytest
```

Coverage is reported automatically via `pytest-cov` (configured in `pyproject.toml`). Current unit test coverage is approximately **81%**.

---

## Project Structure

```
salesforce-mcp-server/
├── mcp_server/                    # Python package — the MCP server
│   ├── __init__.py                # Package init (exports __version__)
│   ├── server.py                  # Entry point: Starlette app, FastMCP, middleware,
│   │                              #   Mangum Lambda handler, lifespan, /health
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
├── tests/                         # Test suite (63 unit tests, ~81% coverage)
│   ├── __init__.py
│   ├── conftest.py                # Shared pytest fixtures (mock client, mock context)
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_tools.py          # Unit tests for all 7 MCP tools
│   │   ├── test_auth.py           # Fernet tokens, OAuth state, Bearer parsing, SF exchange
│   │   ├── test_oauth_routes.py   # OAuth discovery, authorize, callback, token endpoints
│   │   └── test_server.py         # /health, RequireBearerToken middleware, _load_aws_secrets
│   └── integration/
│       ├── __init__.py
│       └── test_server.py         # Integration tests against a real Salesforce org
│
├── infra/                         # Infrastructure as Code
│   └── terraform/
│       ├── main.tf                # Root module — wires foundation, mcp_server, monitoring
│       ├── variables.tf           # Input variables (region, project name, environment)
│       ├── outputs.tf             # Outputs (function URL, secrets ARN, role ARN)
│       ├── terraform.tfvars.example # Template for variable values
│       └── modules/
│           ├── foundation/        # Secrets Manager secret
│           │   ├── main.tf
│           │   ├── variables.tf
│           │   └── outputs.tf
│           ├── oauth_proxy/       # Lambda function, Function URL, IAM role, log group
│           │   ├── main.tf
│           │   ├── variables.tf
│           │   └── outputs.tf
│           └── monitoring/        # SNS alerts, CloudWatch dashboard
│               ├── main.tf
│               ├── variables.tf
│               └── outputs.tf
│
├── scripts/
│   └── local-dev.py               # Local dev helper — browser-based SF token retrieval
│
├── .env.example                   # Environment template for local development
├── .gitignore                     # Git ignore rules
├── build-lambda.sh                # Build script for Lambda deployment zip (ARM64, Python 3.13)
├── Makefile                       # Development and deployment task runner
├── pyproject.toml                 # Project metadata, dependencies, tool config
└── uv.lock                        # Locked dependency versions
```

---

## Development Guide

### Makefile Commands

| Command | Description |
|---|---|
| `make help` | Show all available targets |
| `make install` | Install dependencies with `uv sync` |
| `make dev-server` | Run the MCP server locally |
| `make dev` | Install + run (convenience target) |
| `make local-dev` | Get a Salesforce token, start server, and smoke test (interactive) |
| `make local-token` | Get a Salesforce access token via browser login and print it |
| `make test` | Run all tests with coverage |
| `make test-unit` | Run unit tests only |
| `make test-int` | Run integration tests (requires `SALESFORCE_ACCESS_TOKEN`) |
| `make lint` | Run ruff linter |
| `make format` | Auto-fix lint issues and format code |
| `make build` | Build Lambda deployment zip via `build-lambda.sh` |
| `make deploy` | Build zip and deploy to Lambda (configurable: `FUNCTION_NAME`, `REGION`, `PROFILE`) |
| `make clean` | Remove caches, build artifacts, and `lambda.zip` |

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

### Lambda over Containers

The server runs as a single AWS Lambda function behind a Function URL rather than a containerized service. This provides:
- **Zero idle cost** — Lambda scales to zero when not in use.
- **No infrastructure management** — no ECS clusters, load balancers, or VPCs to maintain.
- **Sub-second warm invocations** — after the initial cold start (~3-5s), warm requests complete in milliseconds.
- **Automatic scaling** — Lambda handles concurrency natively.

### Stateless Architecture

The server runs in **stateless mode** (`MCP_STATELESS=true`):
- No in-memory caching or sessions between requests.
- Each Lambda invocation handles exactly one request independently.
- The Salesforce Bearer token is extracted and decrypted from each request.
- This enables Lambda to spin up as many concurrent instances as needed with zero coordination.

### Centralized Configuration via Secrets Manager

All configuration — including non-sensitive values like API versions — is stored in a single Secrets Manager secret. This provides:
- **One place to update** — no redeployments needed for config changes (just force a cold start).
- **Audit trail** — Secrets Manager logs all access via CloudTrail.
- **No secrets in code or environment variables** — Lambda env vars only contain bootstrap pointers to the secret.

### Per-User Authentication

Rather than using a single service account, each user authenticates with their own Salesforce credentials. This means:
- **Salesforce RBAC is enforced natively** — profiles, permission sets, field-level security, and sharing rules all apply automatically.
- **Audit trails** in Salesforce show the actual user who made each API call.
- **No privilege escalation** — users can only access what their Salesforce profile allows.

### Read-Only Access

All tools are read-only by design. The server does not expose any create, update, or delete operations on Salesforce records. This reduces the blast radius of any misconfiguration or security issue.

### DNS Rebinding Protection Disabled

DNS rebinding protection is explicitly disabled in the FastMCP `TransportSecuritySettings`. This is required for Lambda Function URLs where internal routing uses hostnames that would be rejected by default Host header validation. Since the server handles its own OAuth authentication at the application layer, this is safe.

### Fernet over JWT

The server uses Fernet encryption (AES-128-CBC + HMAC-SHA256) for tokens instead of standard JWTs. This ensures the Salesforce access token is **encrypted** (not just signed) and cannot be read by the MCP client or any intermediary. The `MCP_JWT_SECRET` setting name is a historical artifact — the actual mechanism is symmetric encryption, not JWT signing.
