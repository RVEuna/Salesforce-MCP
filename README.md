# MCP Server Template: Python + OpenSearch + AgentCore

A template for building MCP (Model Context Protocol) servers with OpenSearch retrieval, deployable to AWS Bedrock AgentCore.

## Quick Start

### Prerequisites

- Python 3.11+ (we recommend 3.13)
- [uv](https://github.com/astral-sh/uv) for package management
- Docker or Podman
- AWS CLI (for deployment)
- Terraform 1.5+ (for infrastructure)

### Local Development

1. **Clone and install dependencies:**
   ```bash
   cp .env.local.example .env
   uv sync
   ```

2. **Start local OpenSearch:**
   ```bash
   make dev-infra
   ```

3. **Initialize the index and seed data:**
   ```bash
   make init-index
   make seed-data
   ```

4. **Run the MCP server:**
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
   # Get ECR login
   aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-2.amazonaws.com

   # Build and push
   docker build -t <ecr-url>:latest .
   docker push <ecr-url>:latest
   ```

4. **Update your `.env` with AWS values** (from Terraform outputs).

## What's Included

### 5 Example Tools

| Tool | Pattern | Description |
|------|---------|-------------|
| `echo` | Simple I/O | Basic request/response pattern |
| `search` | Retrieval | Text search with filtering and pagination |
| `lookup` | Single fetch | Get document by ID with not-found handling |
| `batch_lookup` | Bulk fetch | Efficient multi-document retrieval (mget) |
| `related_documents` | Relationships | Follow document links to find related items |

### Infrastructure (Terraform)

- **Foundation**: ECR, IAM roles, Secrets Manager
- **OpenSearch**: Managed domain with k-NN enabled
- **AgentCore**: Runtime configuration and CodeBuild
- **Monitoring**: CloudWatch dashboards and alarms

### Local Development

- **docker-compose.yml**: Local OpenSearch + Dashboards
- **scripts/**: Index initialization and data seeding
- **tests/**: Unit and integration test suite

## Customization Guide

### Adding Your Own Tools

1. Create a new file in `mcp_server/tools/`:
   ```python
   # mcp_server/tools/my_tool.py
   from typing import Callable
   from mcp.server.fastmcp import FastMCP

   def register_my_tool(mcp: FastMCP, get_store: Callable, execute_tool: Callable):
       @mcp.tool()
       def my_tool(param: str) -> dict:
           def _execute():
               store = get_store()
               # Your logic here
               return {"result": "..."}

           return execute_tool("my_tool", {"param": param}, _execute)
   ```

2. Register it in `mcp_server/tools/__init__.py`:
   ```python
   from mcp_server.tools.my_tool import register_my_tool

   def register_tools(mcp, get_store, execute_tool):
       # ... existing tools ...
       register_my_tool(mcp, get_store, execute_tool)
   ```

3. Add tests in `tests/unit/test_tools.py`.

### Changing the Index Schema

1. Edit `scripts/init-index.py` to modify the mapping
2. Update field references in your tools
3. Re-run `make init-index` (this will delete existing data!)

### Configuration

All configuration is managed via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENSEARCH_ENDPOINT` | `http://localhost:9200` | OpenSearch URL |
| `OPENSEARCH_INDEX` | `documents` | Index name |
| `OPENSEARCH_AUTH_MODE` | `none` | `none`, `basic`, or `aws` |
| `OPENSEARCH_REGION` | `us-east-2` | AWS region (for auth) |
| `MCP_SERVER_NAME` | `my-mcp-server` | Server name in logs |
| `MCP_LOG_LEVEL` | `INFO` | Logging verbosity |
| `MCP_LOG_FORMAT` | `json` | `json` or `text` |

See `.env.example` and `.env.local.example` for full lists.

## Project Structure

```
python-opensearch-agentcore/
├── mcp_server/
│   ├── server.py              # FastMCP server entry point
│   ├── config/
│   │   └── settings.py        # Pydantic configuration
│   ├── tools/
│   │   ├── echo.py            # Simple I/O pattern
│   │   ├── search.py          # Retrieval pattern
│   │   ├── lookup.py          # Single fetch pattern
│   │   ├── batch_lookup.py    # Bulk fetch pattern
│   │   └── related_documents.py # Relationship pattern
│   └── store/
│       └── opensearch.py      # OpenSearch client
├── infra/
│   └── terraform/
│       ├── main.tf
│       └── modules/
│           ├── foundation/    # IAM, ECR, Secrets
│           ├── opensearch/    # OpenSearch domain
│           ├── agentcore/     # AgentCore runtime
│           └── monitoring/    # CloudWatch
├── tests/
│   ├── unit/
│   └── integration/
├── scripts/
│   ├── init-index.py          # Create OpenSearch index
│   └── seed-data.py           # Load sample documents
├── docker-compose.yml         # Local OpenSearch
├── Dockerfile                 # Production container
├── Makefile                   # Development tasks
└── pyproject.toml             # Dependencies
```

## Testing

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run integration tests (requires local OpenSearch)
make dev-infra
make test-int
```

## Notes

### Stateless Mode

This template runs in **stateless mode** for AgentCore compatibility. This means:
- No in-memory caching between requests
- Each request may hit a different container instance
- Use external caching (Redis, ElastiCache) if you need cross-request caching

### OpenSearch Managed Domains

This template uses **OpenSearch managed domains** (not Serverless collections). The key difference:
- Managed domains use `OPENSEARCH_SERVICE=es`
- Serverless uses `OPENSEARCH_SERVICE=aoss`

The Terraform modules create a managed domain by default.

## Contributing

See [Contributing Guide](../../../docs/contributing.md) for guidelines on adding new templates and examples.
