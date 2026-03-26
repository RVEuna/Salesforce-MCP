#!/usr/bin/env bash
# Build a Lambda deployment zip for the Salesforce MCP server.
#
# The zip contains the mcp_server package and all runtime dependencies
# compiled for Lambda's ARM64 Python 3.13 environment.
#
# Usage:
#   bash build-lambda.sh
#
# Output: lambda.zip (~8-12 MB)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/.lambda-build"
ZIP_FILE="$SCRIPT_DIR/lambda.zip"

echo "=== Building Salesforce MCP Server Lambda zip ==="

rm -rf "$BUILD_DIR" "$ZIP_FILE"
mkdir -p "$BUILD_DIR"

echo "Installing dependencies for ARM64 Lambda..."
uv pip install \
  --python-platform manylinux2014_aarch64 \
  --target "$BUILD_DIR" \
  --python-version 3.13 \
  --only-binary :all: \
  mangum httpx starlette anyio cryptography python-multipart \
  pydantic pydantic-settings python-dotenv boto3 mcp uvicorn

echo "Copying mcp_server package..."
cp -r "$SCRIPT_DIR/mcp_server" "$BUILD_DIR/mcp_server"

echo "Creating zip..."
cd "$BUILD_DIR"
zip -r "$ZIP_FILE" . -x '*.pyc' '__pycache__/*' '*.dist-info/*'

rm -rf "$BUILD_DIR"

SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo "=== Built: $ZIP_FILE ($SIZE) ==="
echo "Lambda handler: mcp_server.server.handler"
