# =============================================================================
# MCP Server Dockerfile for AWS Bedrock AgentCore
# =============================================================================
#
# Build: docker build -t salesforce-mcp-server:latest .
# Run locally: docker run -p 8000:8000 --env-file .env salesforce-mcp-server:latest

FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (for layer caching)
COPY pyproject.toml ./

# Install dependencies
RUN uv sync --no-dev --frozen

# Copy application code
COPY mcp_server/ ./mcp_server/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port for MCP server
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the MCP server
CMD ["uv", "run", "python", "-m", "mcp_server.server"]
