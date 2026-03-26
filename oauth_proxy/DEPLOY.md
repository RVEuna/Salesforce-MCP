# OAuth Proxy — AWS CLI Deployment

Deploy the Salesforce OAuth proxy Lambda using direct AWS CLI commands.
For Terraform, see the `infra/terraform/modules/oauth_proxy/` module.

## Prerequisites

1. **Salesforce Connected App**: Enable "Issue JSON Web Token (JWT)-based access tokens for named users" in Setup > App Manager > your Connected App > Edit.

2. **AgentCore runtime** already deployed with your MCP server container.

3. **AWS CLI v2** configured with appropriate permissions.

## Step 1: Build the Lambda zip

```bash
cd oauth_proxy && bash build-lambda.sh
```

This creates `oauth_proxy/lambda.zip` (~2-3 MB).

## Step 2: Create IAM role for the Lambda

```bash
# Create the execution role
aws iam create-role \
  --role-name salesforce-mcp-oauth-proxy-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach basic Lambda execution policy (CloudWatch Logs)
aws iam attach-role-policy \
  --role-name salesforce-mcp-oauth-proxy-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Wait for IAM propagation
sleep 10
```

## Step 3: Create the Lambda function

Replace the placeholder values below with your actual configuration.

```bash
REGION=us-east-2
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws lambda create-function \
  --function-name salesforce-mcp-oauth-proxy \
  --region $REGION \
  --runtime python3.13 \
  --architectures arm64 \
  --handler salesforce_oauth_proxy.handler \
  --role "arn:aws:iam::${ACCOUNT_ID}:role/salesforce-mcp-oauth-proxy-role" \
  --zip-file fileb://oauth_proxy/lambda.zip \
  --timeout 300 \
  --memory-size 256 \
  --environment "Variables={
    SALESFORCE_CLIENT_ID=<your-connected-app-consumer-key>,
    SALESFORCE_CLIENT_SECRET=<your-connected-app-consumer-secret>,
    SALESFORCE_LOGIN_URL=https://test.salesforce.com,
    AGENTCORE_URL=<your-agentcore-invocation-url>/mcp,
    PROXY_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))'),
    LOG_LEVEL=INFO
  }"
```

## Step 4: Create a public Function URL

```bash
aws lambda create-function-url-config \
  --function-name salesforce-mcp-oauth-proxy \
  --region $REGION \
  --auth-type NONE \
  --cors '{
    "AllowOrigins": ["*"],
    "AllowMethods": ["GET", "POST"],
    "AllowHeaders": ["authorization", "content-type", "accept"]
  }'

# Allow public invocation
aws lambda add-permission \
  --function-name salesforce-mcp-oauth-proxy \
  --region $REGION \
  --statement-id FunctionURLAllowPublicAccess \
  --action lambda:InvokeFunctionUrl \
  --principal "*" \
  --function-url-auth-type NONE
```

Note the `FunctionUrl` in the output — this is your proxy's public URL.

## Step 5: Set PROXY_BASE_URL

Once you have the Function URL, update the Lambda environment to include it
so OAuth redirects use the correct public URL:

```bash
FUNCTION_URL=<the-function-url-from-step-4>

aws lambda update-function-configuration \
  --function-name salesforce-mcp-oauth-proxy \
  --region $REGION \
  --environment "Variables={
    SALESFORCE_CLIENT_ID=<same-as-step-3>,
    SALESFORCE_CLIENT_SECRET=<same-as-step-3>,
    SALESFORCE_LOGIN_URL=https://test.salesforce.com,
    AGENTCORE_URL=<same-as-step-3>,
    PROXY_SECRET=<same-as-step-3>,
    PROXY_BASE_URL=${FUNCTION_URL},
    LOG_LEVEL=INFO
  }"
```

> **Note:** `update-function-configuration` replaces ALL environment variables.
> Include every variable, not just the new one.

## Step 6: Configure AgentCore with customJWTAuthorizer

This tells AgentCore to validate Salesforce JWT access tokens instead of
requiring SigV4 (IAM) authentication.

```bash
RUNTIME_ID=<your-agentcore-runtime-id>

# IMPORTANT: The discoveryUrl must match the issuer (iss) claim in your
# Salesforce JWT tokens. This is typically your Salesforce INSTANCE URL
# (not the login URL). Verify by decoding a token at jwt.io.
#
# Sandbox example:
#   https://myorg--sandbox.sandbox.my.salesforce.com/.well-known/openid-configuration
# Production example:
#   https://myorg.my.salesforce.com/.well-known/openid-configuration

SF_DISCOVERY_URL=https://<your-sf-instance>.my.salesforce.com/.well-known/openid-configuration
SF_CLIENT_ID=<your-connected-app-consumer-key>

aws bedrock-agentcore-control update-agent-runtime \
  --region $REGION \
  --agent-runtime-id $RUNTIME_ID \
  --authorizer-configuration "{
    \"customJWTAuthorizer\": {
      \"discoveryUrl\": \"${SF_DISCOVERY_URL}\",
      \"allowedAudience\": [\"${SF_CLIENT_ID}\"]
    }
  }"
```

> **Verify the discovery URL first:**
> ```bash
> curl -s https://<your-sf-instance>.my.salesforce.com/.well-known/openid-configuration | python -m json.tool
> ```
> Confirm it returns a valid JSON with `jwks_uri` and `issuer` fields.

## Step 7: Test

```bash
# Health check
curl https://<function-url>/health

# Should return 401 with WWW-Authenticate header pointing to PRM
curl -X POST https://<function-url>/mcp
```

## Step 8: Connect your MCP client

**Claude Code / Cursor:**
```json
{
  "mcpServers": {
    "salesforce": {
      "type": "http",
      "url": "https://<function-url>/mcp"
    }
  }
}
```

The MCP client will discover the OAuth endpoints automatically,
redirect you to Salesforce login, and obtain a JWT access token.

## Updating the Lambda code

After making changes to `salesforce_oauth_proxy.py`:

```bash
cd oauth_proxy && bash build-lambda.sh
aws lambda update-function-code \
  --function-name salesforce-mcp-oauth-proxy \
  --region $REGION \
  --zip-file fileb://lambda.zip
```

Or use the Makefile:
```bash
make proxy-build
make proxy-deploy FUNCTION_NAME=salesforce-mcp-oauth-proxy REGION=us-east-2
```

## Local development (dual-process)

**Terminal 1 — MCP server (tools only):**
```bash
make dev-server
```

**Terminal 2 — OAuth proxy (pointed at local MCP server):**
```bash
# Set env vars (or copy oauth_proxy/.env.example to .env.proxy and source it)
export SALESFORCE_CLIENT_ID=<your-key>
export SALESFORCE_CLIENT_SECRET=<your-secret>
export SALESFORCE_LOGIN_URL=https://test.salesforce.com
export AGENTCORE_URL=http://localhost:8000/mcp
export PROXY_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")

make proxy-local
# Proxy runs on http://localhost:9090/mcp
```

**MCP client config for local dev:**
```json
{
  "mcpServers": {
    "salesforce-local": {
      "type": "http",
      "url": "http://localhost:9090/mcp"
    }
  }
}
```
