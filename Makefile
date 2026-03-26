.PHONY: help install dev-server dev local-dev local-token test test-unit test-int lint format build deploy clean

FUNCTION_NAME ?= salesforce-mcp-oauth-proxy
REGION ?= us-east-2
PROFILE ?= shared-dev

help:
	@echo "Available targets:"
	@echo ""
	@echo "  Development:"
	@echo "    install      - Install dependencies"
	@echo "    dev-server   - Run MCP server locally"
	@echo "    dev          - Install deps and run server"
	@echo "    local-dev    - Get SF token, start server, smoke test (interactive)"
	@echo "    local-token  - Just get a Salesforce access token and print it"
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
	@echo "    build        - Build Lambda deployment zip"
	@echo "    deploy       - Deploy Lambda to AWS (FUNCTION_NAME, REGION, PROFILE)"
	@echo ""
	@echo "  Cleanup:"
	@echo "    clean        - Clean up caches and build artifacts"

# Development
install:
	uv sync

dev-server:
	uv run python -m mcp_server.server

dev: install
	$(MAKE) dev-server

local-dev:
	uv run python scripts/local-dev.py

local-token:
	uv run python scripts/local-dev.py --token-only

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
	bash build-lambda.sh

deploy: build
	aws lambda update-function-code \
		--function-name $(FUNCTION_NAME) \
		--zip-file fileb://lambda.zip \
		--region $(REGION) \
		--profile $(PROFILE)

# Cleanup
clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache
	rm -rf .lambda-build lambda.zip
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
