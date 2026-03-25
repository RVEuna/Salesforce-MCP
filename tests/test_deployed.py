"""Quick test for the deployed AgentCore MCP server."""

import json

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session
import httpx

REGION = "us-east-2"
RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-2:339712830340:runtime/salesforce_mcp_server_prod-qlCRAm2ryf"

encoded_arn = RUNTIME_ARN.replace(":", "%3A").replace("/", "%2F")
BASE_URL = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"


def signed_request(method, url, body=None, extra_headers=None):
    """Make a SigV4-signed request to AgentCore."""
    data = json.dumps(body) if body else ""
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    aws_request = AWSRequest(method=method, url=url, data=data, headers=headers)
    credentials = Session().get_credentials().get_frozen_credentials()
    SigV4Auth(credentials, "bedrock-agentcore", REGION).add_auth(aws_request)
    return dict(aws_request.headers), data


print("=" * 60)
print("Testing deployed AgentCore MCP server")
print("=" * 60)

client = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))

# Test 1: GET /health
print("\n1. GET /health ...")
headers, _ = signed_request("GET", BASE_URL)
try:
    resp = client.get(BASE_URL, headers=headers)
    print(f"   Status: {resp.status_code}")
    print(f"   Body: {resp.text[:300]}")
except httpx.ReadTimeout:
    print("   TIMEOUT (30s)")

# Test 2: POST to /mcp path
mcp_url = BASE_URL  # AgentCore routes to container
print(f"\n2. POST MCP initialize ...")
payload = {
    "jsonrpc": "2.0",
    "id": 0,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "0.1.0"},
    },
}
headers, data = signed_request("POST", mcp_url, payload, {"Accept": "application/json, text/event-stream"})
try:
    resp = client.post(mcp_url, headers=headers, content=data)
    print(f"   Status: {resp.status_code}")
    print(f"   Content-Type: {resp.headers.get('content-type', 'none')}")
    print(f"   Body: {resp.text[:500]}")
except httpx.ReadTimeout:
    print("   TIMEOUT (30s)")

# Test 3: POST with X-Forwarded-Path header
print(f"\n3. POST with path header /mcp ...")
headers, data = signed_request("POST", mcp_url, payload, {
    "Accept": "application/json, text/event-stream",
    "X-Forwarded-Path": "/mcp",
})
try:
    resp = client.post(mcp_url, headers=headers, content=data)
    print(f"   Status: {resp.status_code}")
    print(f"   Body: {resp.text[:500]}")
except httpx.ReadTimeout:
    print("   TIMEOUT (30s)")

print("\n" + "=" * 60)
print("Done.")
print("=" * 60)
client.close()
