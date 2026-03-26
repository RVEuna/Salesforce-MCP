#!/usr/bin/env bash
# Build a Lambda deployment zip for the Salesforce OAuth Proxy.
#
# The zip contains the proxy module and all runtime dependencies
# compiled for Lambda's ARM64 Python 3.13 environment.
#
# Usage:
#   cd oauth_proxy && bash build-lambda.sh
#
# Output: oauth_proxy/lambda.zip (~2-3 MB)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/.build"
ZIP_FILE="$SCRIPT_DIR/lambda.zip"

echo "=== Building Salesforce OAuth Proxy Lambda zip ==="

rm -rf "$BUILD_DIR" "$ZIP_FILE"
mkdir -p "$BUILD_DIR"

echo "Installing dependencies for ARM64 Lambda..."
pip install \
  --platform manylinux2014_aarch64 \
  --target "$BUILD_DIR" \
  --implementation cp \
  --python-version 3.13 \
  --only-binary=:all: \
  mangum httpx starlette anyio cryptography python-multipart

echo "Copying proxy module..."
cp "$SCRIPT_DIR/salesforce_oauth_proxy.py" "$BUILD_DIR/"

echo "Creating zip..."
cd "$BUILD_DIR"
zip -r "$ZIP_FILE" . -x '*.pyc' '__pycache__/*' '*.dist-info/*'

rm -rf "$BUILD_DIR"

SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo "=== Built: $ZIP_FILE ($SIZE) ==="
