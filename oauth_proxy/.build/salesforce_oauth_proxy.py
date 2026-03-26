"""
Salesforce OAuth Proxy for MCP Clients + AgentCore.

Bridges MCP clients (Claude, Cursor, VS Code) with a Salesforce-backed
MCP server running on AWS Bedrock AgentCore.

The proxy is the public-facing endpoint. It:
- Serves OAuth discovery (PRM, AS metadata) so MCP clients know how to authenticate
- Brokers the Salesforce Authorization Code flow on behalf of the user
- Returns Salesforce JWT access tokens directly to the client
- Forwards authenticated /mcp requests to the AgentCore runtime
- AgentCore validates the Salesforce JWT via customJWTAuthorizer

Requires the Salesforce Connected App setting:
  "Issue JSON Web Token (JWT)-based access tokens for named users" = ENABLED

Works both locally (uvicorn) and on AWS Lambda (via Mangum).

Usage (local):
    SALESFORCE_CLIENT_ID=... SALESFORCE_CLIENT_SECRET=... \\
    SALESFORCE_LOGIN_URL=https://test.salesforce.com \\
    AGENTCORE_URL=http://localhost:8000/mcp \\
    PROXY_SECRET=<random-hex-string> \\
    uv run python -m oauth_proxy.salesforce_oauth_proxy

Usage (Lambda):
    Handler: salesforce_oauth_proxy.handler
    Environment: SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET,
                 SALESFORCE_LOGIN_URL, AGENTCORE_URL, PROXY_SECRET

Environment variables:
    SALESFORCE_CLIENT_ID       Connected App consumer key (required)
    SALESFORCE_CLIENT_SECRET   Connected App consumer secret (required)
    SALESFORCE_LOGIN_URL       OAuth login endpoint (required)
                               Production: https://login.salesforce.com
                               Sandbox:    https://test.salesforce.com
    AGENTCORE_URL              AgentCore runtime invocation URL (required)
                               Local dev:  http://localhost:8000/mcp
    PROXY_SECRET               Secret for encrypting short-lived auth codes (required)
    PROXY_BASE_URL             Override public base URL (optional; derived from request)
    PROXY_PORT                 Local dev port (default: 9090)
    LOG_LEVEL                  Logging level (default: INFO)
    UPSTREAM_TIMEOUT           AgentCore request timeout in seconds (default: 120)
    SF_ACCESS_TOKEN_TTL        expires_in value returned to clients (default: 7200)
    AUTH_CODE_TTL              Auth code lifetime in seconds (default: 300)
"""

import base64
import hashlib
import json
import logging
import os
import time
import uuid
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

logger = logging.getLogger("salesforce_oauth_proxy")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

SF_CLIENT_ID = os.environ.get("SALESFORCE_CLIENT_ID", "")
SF_CLIENT_SECRET = os.environ.get("SALESFORCE_CLIENT_SECRET", "")
SF_LOGIN_URL = os.environ.get("SALESFORCE_LOGIN_URL", "")
AGENTCORE_URL = os.environ.get("AGENTCORE_URL", "")
PROXY_SECRET = os.environ.get("PROXY_SECRET", "")

PROXY_BASE_URL = os.environ.get("PROXY_BASE_URL", "")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "9090"))
UPSTREAM_TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT", "120"))
SF_ACCESS_TOKEN_TTL = int(os.environ.get("SF_ACCESS_TOKEN_TTL", "7200"))
AUTH_CODE_TTL = int(os.environ.get("AUTH_CODE_TTL", "300"))

_missing = [
    name
    for name, val in [
        ("SALESFORCE_CLIENT_ID", SF_CLIENT_ID),
        ("SALESFORCE_CLIENT_SECRET", SF_CLIENT_SECRET),
        ("SALESFORCE_LOGIN_URL", SF_LOGIN_URL),
        ("AGENTCORE_URL", AGENTCORE_URL),
        ("PROXY_SECRET", PROXY_SECRET),
    ]
    if not val
]
if _missing:
    raise RuntimeError(
        f"Missing required environment variable(s): {', '.join(_missing)}"
    )

# ---------------------------------------------------------------------------
# Shared HTTP clients (reuse TCP+TLS connections across Lambda invocations)
# ---------------------------------------------------------------------------

_agentcore_client = httpx.AsyncClient(
    timeout=UPSTREAM_TIMEOUT,
    http2=False,
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
)

_sf_client = httpx.AsyncClient(
    timeout=30.0,
    limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HOP_BY_HOP_HEADERS = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-length",
})


def _get_fernet() -> Fernet:
    """Derive a Fernet key from PROXY_SECRET for encrypting short-lived auth codes."""
    key_bytes = hashlib.sha256(PROXY_SECRET.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def _filter_response_headers(headers: dict) -> dict:
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS}


def _get_proxy_base(request: Request) -> str:
    if PROXY_BASE_URL:
        return PROXY_BASE_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


def _encode_oauth_state(
    redirect_uri: str, client_state: str = "", code_challenge: str = ""
) -> str:
    """Pack MCP client's OAuth params into a base64 blob for Salesforce's state."""
    payload = {"redirect_uri": redirect_uri}
    if client_state:
        payload["client_state"] = client_state
    if code_challenge:
        payload["code_challenge"] = code_challenge
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_oauth_state(state: str) -> dict:
    try:
        return json.loads(base64.urlsafe_b64decode(state))
    except Exception as exc:
        raise ValueError(f"Invalid OAuth state: {exc}") from exc


def _issue_auth_code(sf_tokens: dict) -> str:
    """Encrypt SF tokens into a short-lived auth code for the MCP client."""
    payload = {
        "access_token": sf_tokens["access_token"],
        "refresh_token": sf_tokens.get("refresh_token", ""),
        "instance_url": sf_tokens.get("instance_url", ""),
        "exp": int(time.time()) + AUTH_CODE_TTL,
    }
    return _get_fernet().encrypt(json.dumps(payload).encode()).decode()


def _redeem_auth_code(code: str) -> dict:
    """Decrypt and validate a short-lived auth code."""
    try:
        payload = json.loads(_get_fernet().decrypt(code.encode()))
    except (InvalidToken, Exception) as exc:
        raise ValueError(f"Invalid auth code: {exc}") from exc
    if time.time() > payload.get("exp", 0):
        raise ValueError("Auth code expired")
    return payload


# =============================================================================
# Protected Resource Metadata (RFC 9728)
# =============================================================================


async def oauth_protected_resource(request: Request) -> JSONResponse:
    """Tell MCP clients which authorization server protects this resource."""
    proxy_base = _get_proxy_base(request)
    logger.info("PRM requested, returning auth server: %s", proxy_base)
    return JSONResponse({
        "resource": f"{proxy_base}/mcp",
        "authorization_servers": [proxy_base],
    })


# =============================================================================
# OAuth Authorization Server Metadata (RFC 8414)
# =============================================================================


async def oauth_metadata(request: Request) -> JSONResponse:
    """Discovery endpoint — tells MCP clients where to authorize/token/register."""
    proxy_base = _get_proxy_base(request)
    return JSONResponse({
        "issuer": proxy_base,
        "authorization_endpoint": f"{proxy_base}/oauth/authorize",
        "token_endpoint": f"{proxy_base}/oauth/token",
        "registration_endpoint": f"{proxy_base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
    })


# =============================================================================
# OAuth Endpoints
# =============================================================================


async def oauth_register(request: Request) -> JSONResponse:
    """Mock Dynamic Client Registration (RFC 7591).

    MCP clients like mcp-remote register before starting the OAuth flow.
    Since we proxy to Salesforce (which uses a pre-configured Connected App),
    we just acknowledge with a generated client_id.
    """
    body = await request.json()
    client_id = str(uuid.uuid4())
    logger.info("DCR: client_name=%s", body.get("client_name", "unknown"))
    return JSONResponse({
        "client_id": client_id,
        "client_name": body.get("client_name", "mcp-client"),
        "redirect_uris": body.get("redirect_uris", []),
        "grant_types": body.get("grant_types", ["authorization_code"]),
        "response_types": body.get("response_types", ["code"]),
        "token_endpoint_auth_method": "none",
    }, status_code=201)


async def oauth_authorize(request: Request) -> Response:
    """Begin the OAuth flow — redirect the user's browser to Salesforce login."""
    redirect_uri = request.query_params.get("redirect_uri", "")
    client_state = request.query_params.get("state", "")
    code_challenge = request.query_params.get("code_challenge", "")

    if not redirect_uri:
        return JSONResponse({"error": "redirect_uri is required"}, status_code=400)

    packed_state = _encode_oauth_state(redirect_uri, client_state, code_challenge)
    callback = f"{_get_proxy_base(request)}/oauth/callback"

    params = {
        "response_type": "code",
        "client_id": SF_CLIENT_ID,
        "redirect_uri": callback,
        "scope": "api refresh_token",
        "state": packed_state,
    }
    sf_url = f"{SF_LOGIN_URL.rstrip('/')}/services/oauth2/authorize?{urlencode(params)}"

    logger.info("Redirecting to Salesforce login")
    return RedirectResponse(sf_url, status_code=302)


async def oauth_callback(request: Request) -> Response:
    """Handle Salesforce's redirect after user login.

    Exchanges the Salesforce auth code for tokens, encrypts them into a
    short-lived proxy auth code, and redirects back to the MCP client.
    """
    sf_code = request.query_params.get("code", "")
    state_param = request.query_params.get("state", "")

    if not sf_code or not state_param:
        return JSONResponse({"error": "Missing code or state from Salesforce"}, status_code=400)

    try:
        client_params = _decode_oauth_state(state_param)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    callback = f"{_get_proxy_base(request)}/oauth/callback"
    token_url = f"{SF_LOGIN_URL.rstrip('/')}/services/oauth2/token"

    resp = await _sf_client.post(token_url, data={
        "grant_type": "authorization_code",
        "code": sf_code,
        "client_id": SF_CLIENT_ID,
        "client_secret": SF_CLIENT_SECRET,
        "redirect_uri": callback,
    })

    if resp.status_code != 200:
        logger.error("SF token exchange failed: %d %s", resp.status_code, resp.text[:500])
        return JSONResponse({"error": "Salesforce token exchange failed"}, status_code=502)

    sf_tokens = resp.json()
    signed_code = _issue_auth_code(sf_tokens)

    redirect_uri = client_params["redirect_uri"]
    params = {"code": signed_code}
    if client_params.get("client_state"):
        params["state"] = client_params["client_state"]

    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(
        f"{redirect_uri}{separator}{urlencode(params)}", status_code=302
    )


async def oauth_token(request: Request) -> Response:
    """Exchange an auth code or refresh token for a Salesforce JWT access token.

    - authorization_code: redeems the encrypted proxy auth code, returns the
      raw Salesforce JWT that the client will use as its Bearer token.
    - refresh_token: exchanges the Salesforce refresh token for a new JWT.
    """
    form = await request.form()
    grant_type = str(form.get("grant_type", "authorization_code"))

    if grant_type == "refresh_token":
        refresh_token = str(form.get("refresh_token", ""))
        if not refresh_token:
            return JSONResponse({"error": "refresh_token is required"}, status_code=400)

        token_url = f"{SF_LOGIN_URL.rstrip('/')}/services/oauth2/token"
        resp = await _sf_client.post(token_url, data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": SF_CLIENT_ID,
            "client_secret": SF_CLIENT_SECRET,
        })

        if resp.status_code != 200:
            logger.error("SF refresh failed: %d %s", resp.status_code, resp.text[:500])
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Refresh token invalid or expired"},
                status_code=400,
            )

        sf_tokens = resp.json()
        return JSONResponse({
            "access_token": sf_tokens["access_token"],
            "refresh_token": sf_tokens.get("refresh_token", refresh_token),
            "token_type": "Bearer",
            "expires_in": SF_ACCESS_TOKEN_TTL,
        })

    # authorization_code grant
    code = str(form.get("code", ""))
    if not code:
        return JSONResponse({"error": "code is required"}, status_code=400)

    try:
        token_data = _redeem_auth_code(code)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    return JSONResponse({
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "token_type": "Bearer",
        "expires_in": SF_ACCESS_TOKEN_TTL,
    })


# =============================================================================
# MCP Proxy (forward authenticated requests to AgentCore)
# =============================================================================


async def mcp_proxy(request: Request) -> Response:
    """Forward MCP requests to AgentCore, return 401 with PRM if unauthenticated."""
    auth_header = request.headers.get("authorization", "")

    if not auth_header:
        proxy_base = _get_proxy_base(request)
        prm_url = f"{proxy_base}/.well-known/oauth-protected-resource"
        logger.info("MCP request without auth, returning 401")
        return Response(
            content='{"jsonrpc":"2.0","error":{"code":-32001,"message":"Authentication required"},"id":null}',
            status_code=401,
            headers={
                "Content-Type": "application/json",
                "WWW-Authenticate": f'Bearer resource_metadata="{prm_url}"',
            },
        )

    body = await request.body()
    logger.info("Forwarding MCP %s to AgentCore (%d bytes)", request.method, len(body))

    headers = {
        "Content-Type": request.headers.get("content-type", "application/json"),
        "Accept": request.headers.get("accept", "application/json, text/event-stream"),
        "Authorization": auth_header,
    }
    session_id = request.headers.get("mcp-session-id")
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    resp = await _agentcore_client.request(
        method=request.method,
        url=AGENTCORE_URL,
        content=body,
        headers=headers,
    )

    logger.info("AgentCore response: %d (%dms)", resp.status_code, int(resp.elapsed.total_seconds() * 1000))
    if resp.status_code != 200:
        logger.warning("AgentCore error: %s", resp.text[:500])

    response_headers = _filter_response_headers(dict(resp.headers))
    ac_session = resp.headers.get("mcp-session-id")
    if ac_session:
        response_headers["Mcp-Session-Id"] = ac_session

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=response_headers,
    )


# =============================================================================
# Health
# =============================================================================


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "login_url": SF_LOGIN_URL})


# =============================================================================
# Starlette App
# =============================================================================

routes = [
    Route("/.well-known/oauth-protected-resource", oauth_protected_resource),
    Route("/.well-known/oauth-authorization-server", oauth_metadata),
    Route("/.well-known/openid-configuration", oauth_metadata),
    Route("/oauth/register", oauth_register, methods=["POST"]),
    Route("/oauth/authorize", oauth_authorize),
    Route("/oauth/callback", oauth_callback),
    Route("/oauth/token", oauth_token, methods=["POST"]),
    Route("/mcp", mcp_proxy, methods=["GET", "POST", "DELETE"]),
    Route("/health", health),
]

app = Starlette(routes=routes)

# Lambda handler (Mangum wraps the ASGI app for API Gateway / Function URL)
try:
    from mangum import Mangum
    handler = Mangum(app, lifespan="off")
except ImportError:
    handler = None

# Local development
if __name__ == "__main__":
    import uvicorn

    print("Salesforce OAuth Proxy for AgentCore MCP")
    print(f"  Proxy:      http://localhost:{PROXY_PORT}/mcp")
    print(f"  AgentCore:  {AGENTCORE_URL[:80]}...")
    print(f"  Login URL:  {SF_LOGIN_URL}")
    print()
    uvicorn.run(app, host="127.0.0.1", port=PROXY_PORT)
