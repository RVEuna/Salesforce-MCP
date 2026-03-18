.PHONY: help install dev-server dev test test-unit test-int lint format build deploy clean

help:
	@echo "Available targets:"
	@echo ""
	@echo "  Development:"
	@echo "    install      - Install dependencies"
	@echo "    dev-server   - Run MCP server locally"
	@echo "    dev          - Install deps and run server"
	@echo ""
	@echo "  Testing:"
	@echo "    test         - Run all tests"
	@echo "    test-unit    - Run unit tests only"
	@echo "    test-int     - Run integration tests (needs SALESFORCE_ACCESS_TOKEN)"
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
	@echo "    clean        - Clean up caches"

# Development
install:
	uv sync

dev-server:
	uv run python -m mcp_server.server

dev: install
	$(MAKE) dev-server

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
	docker build -t salesforce-mcp-server:latest .

deploy:
	@echo "Deploying to AgentCore..."
	@echo "1. Ensure AWS credentials are configured"
	@echo "2. Run: cd infra/terraform && terraform apply"
	cd infra/terraform && terraform init && terraform apply

# Cleanup
clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
