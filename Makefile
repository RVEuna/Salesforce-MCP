.PHONY: help install dev-server dev test test-unit test-int lint format build deploy clean \
       proxy-build proxy-local proxy-deploy

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
	@echo "  OAuth Proxy:"
	@echo "    proxy-build  - Build Lambda zip for OAuth proxy"
	@echo "    proxy-local  - Run OAuth proxy locally (port 9090)"
	@echo "    proxy-deploy - Deploy proxy Lambda (requires FUNCTION_NAME, REGION)"
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

# OAuth Proxy
proxy-build:
	cd oauth_proxy && bash build-lambda.sh

proxy-local:
	uv run python -m oauth_proxy.salesforce_oauth_proxy

proxy-deploy:
	@test -n "$(FUNCTION_NAME)" || (echo "Usage: make proxy-deploy FUNCTION_NAME=<name> REGION=<region>" && exit 1)
	aws lambda update-function-code \
		--function-name $(FUNCTION_NAME) \
		--zip-file fileb://oauth_proxy/lambda.zip \
		--region $(or $(REGION),us-east-2)

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
	rm -rf oauth_proxy/.build oauth_proxy/lambda.zip
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
