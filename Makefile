.PHONY: help install dev-infra dev-server dev init-index seed-data test test-unit test-int lint format build deploy clean

help:
	@echo "Available targets:"
	@echo ""
	@echo "  Development:"
	@echo "    install      - Install dependencies"
	@echo "    dev-infra    - Start local OpenSearch (Docker)"
	@echo "    dev-server   - Run MCP server locally"
	@echo "    dev          - Start infra, init index, run server"
	@echo "    init-index   - Create OpenSearch index with mappings"
	@echo "    seed-data    - Load sample documents"
	@echo ""
	@echo "  Testing:"
	@echo "    test         - Run all tests"
	@echo "    test-unit    - Run unit tests only"
	@echo "    test-int     - Run integration tests"
	@echo ""
	@echo "  Code Quality:"
	@echo "    lint         - Run linter"
	@echo "    format       - Format code"
	@echo ""
	@echo "  Deployment:"
	@echo "    build        - Build Docker image"
	@echo "    deploy       - Deploy to AgentCore"
	@echo ""
	@echo "  Cleanup:"
	@echo "    clean        - Stop containers and clean up"

# Development
install:
	uv sync

dev-infra:
	docker compose up -d
	@echo "Waiting for OpenSearch to be healthy..."
	@until curl -s http://localhost:9200/_cluster/health | grep -q '"status"'; do sleep 2; done
	@echo "OpenSearch is ready!"

dev-server:
	uv run python -m mcp_server.server

dev: dev-infra init-index
	$(MAKE) dev-server

init-index:
	uv run python scripts/init-index.py

seed-data:
	uv run python scripts/seed-data.py

# Testing
test:
	uv run pytest

test-unit:
	uv run pytest tests/unit -v

test-int:
	uv run pytest tests/integration -v

# Code Quality
lint:
	uv run ruff check .

format:
	uv run ruff check --fix .
	uv run ruff format .

# Deployment
build:
	docker build -t my-mcp-server:latest .

deploy:
	@echo "Deploying to AgentCore..."
	@echo "1. Ensure AWS credentials are configured"
	@echo "2. Run: cd infra/terraform && terraform apply"
	cd infra/terraform && terraform init && terraform apply

# Cleanup
clean:
	docker compose down -v
	rm -rf __pycache__ .pytest_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
