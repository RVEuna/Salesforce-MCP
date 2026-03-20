"""Salesforce OAuth 2.0 authentication for the MCP server.

The server owns the OAuth flow — it acts as an authorization server proxy,
brokering Salesforce login on behalf of MCP clients. Clients discover auth
via /.well-known/oauth-authorization-server per the MCP spec.

Each tool call extracts the Bearer token from the inbound request and creates
a per-request SalesforceClient scoped to that user's access.
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import urlencode

import httpx
from mcp.server.fastmcp import Context

from mcp_server.config import mcp_settings, salesforce_settings
from mcp_server.salesforce.client import SalesforceClient

logger = logging.getLogger(__name__)


def get_salesforce_client(ctx: Context) -> SalesforceClient:
    """Extract the Bearer token from the MCP request and return a SalesforceClient.

    Called at the start of every tool to create a per-request client scoped
    to the authenticated user's Salesforce access token.

    The Bearer token may be a compound token (HMAC-signed envelope with the
    real SF access_token inside) or a raw SF token for local development.
    """
    bearer = _extract_bearer_token(ctx)

    try:
        payload = decode_compound_token(bearer)
        sf_token = payload["access_token"]
        instance_url = payload.get("instance_url", salesforce_settings.instance_url)
        logger.debug("Using access_token from compound token")
    except ValueError:
        sf_token = bearer
        instance_url = salesforce_settings.instance_url
        logger.debug("Using raw bearer token (local dev or legacy)")

    return SalesforceClient(
        access_token=sf_token,
        instance_url=instance_url,
        api_version=salesforce_settings.api_version,
    )


def _extract_bearer_token(ctx: Context) -> str:
    """Pull the Bearer token from request context, trying multiple access patterns.

    The MCP SDK exposes HTTP request info differently across versions:
    1. ctx.request_context.request.headers (fastmcp style)
    2. ctx.request_context.headers (direct headers)
    3. ctx.request_context as a dict with "headers" key

    Falls back to SALESFORCE_ACCESS_TOKEN env var for local development
    where mcp-remote or other bridges may not forward headers.
    """
    token = _try_extract_from_context(ctx)
    if token:
        return token

    if salesforce_settings.access_token:
        logger.debug("Using SALESFORCE_ACCESS_TOKEN from environment")
        return salesforce_settings.access_token

    raise ValueError(
        "No Salesforce access token found. Either pass an Authorization: Bearer header "
        "or set SALESFORCE_ACCESS_TOKEN in your .env file."
    )


def _try_extract_from_context(ctx: Context) -> str | None:
    """Attempt to extract Bearer token from the MCP Context using known patterns."""
    request_context = getattr(ctx, "request_context", None)
    if request_context is None:
        logger.debug("No request_context on Context object")
        return None

    # Pattern 1: request_context.request.headers (Starlette Request object)
    request_obj = getattr(request_context, "request", None)
    if request_obj is not None:
        headers = getattr(request_obj, "headers", None)
        if headers:
            token = _parse_bearer(headers.get("authorization", ""))
            if token:
                logger.debug("Token extracted via request_context.request.headers")
                return token

    # Pattern 2: request_context.headers directly
    headers = getattr(request_context, "headers", None)
    if headers:
        auth = headers.get("authorization", "") if hasattr(headers, "get") else ""
        token = _parse_bearer(auth)
        if token:
            logger.debug("Token extracted via request_context.headers")
            return token

    # Pattern 3: request_context is a dict
    if isinstance(request_context, dict):
        raw_headers = request_context.get("headers", {})
        if isinstance(raw_headers, dict):
            normalized = {k.lower(): v for k, v in raw_headers.items()}
            token = _parse_bearer(normalized.get("authorization", ""))
            if token:
                logger.debug("Token extracted via request_context dict")
                return token

    # Pattern 4: walk all attributes looking for anything with headers
    for attr_name in dir(request_context):
        if attr_name.startswith("_"):
            continue
        try:
            attr = getattr(request_context, attr_name)
            if hasattr(attr, "headers"):
                h = attr.headers
                auth = h.get("authorization", "") if hasattr(h, "get") else ""
                token = _parse_bearer(auth)
                if token:
                    logger.debug(f"Token extracted via request_context.{attr_name}.headers")
                    return token
        except Exception:
            continue

    logger.debug(
        f"Could not extract token from request_context. "
        f"Type: {type(request_context).__name__}, "
        f"Attrs: {[a for a in dir(request_context) if not a.startswith('_')]}"
    )
    return None


def _parse_bearer(auth_header: str) -> str | None:
    """Parse a Bearer token from an Authorization header value."""
    if not auth_header:
        return None
    # Handle both "Bearer <token>" and "Bearer:<token>" (mcp-remote quirk)
    lower = auth_header.lower()
    if lower.startswith("bearer "):
        return auth_header[7:].strip()
    if lower.startswith("bearer:"):
        return auth_header[7:].strip()
    return None


def build_authorization_url(redirect_uri: str, state: str | None = None) -> str:
    """Build the Salesforce OAuth 2.0 authorization URL.

    The MCP client redirects the user's browser here to begin login.
    """
    params = {
        "response_type": "code",
        "client_id": salesforce_settings.client_id,
        "redirect_uri": redirect_uri,
        "scope": "api refresh_token",
    }
    if state:
        params["state"] = state

    base = salesforce_settings.login_url.rstrip("/")
    return f"{base}/services/oauth2/authorize?{urlencode(params)}"


async def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    """Exchange an authorization code for a Salesforce access token.

    POST to Salesforce's token endpoint after the user completes login.
    Returns the full token response (access_token, instance_url, etc.).
    """
    base = salesforce_settings.login_url.rstrip("/")
    token_url = f"{base}/services/oauth2/token"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": salesforce_settings.client_id,
                "client_secret": salesforce_settings.client_secret,
                "redirect_uri": redirect_uri,
            },
            timeout=salesforce_settings.auth_timeout,
        )

    if response.status_code != 200:
        logger.error(f"Token exchange failed: {response.status_code} {response.text}")
        raise ValueError(f"Salesforce token exchange failed: {response.text}")

    return response.json()


async def refresh_salesforce_token(refresh_token: str) -> dict:
    """Exchange a Salesforce refresh token for a new access token.

    Called when the MCP client presents grant_type=refresh_token.
    Returns the new token response from Salesforce.
    Raises ValueError if the refresh token is invalid, expired, or revoked.
    """
    base = salesforce_settings.login_url.rstrip("/")
    token_url = f"{base}/services/oauth2/token"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": salesforce_settings.client_id,
                "client_secret": salesforce_settings.client_secret,
            },
            timeout=salesforce_settings.auth_timeout,
        )

    if response.status_code != 200:
        logger.error(f"Token refresh failed: {response.status_code} {response.text}")
        raise ValueError(f"Salesforce token refresh failed: {response.text}")

    return response.json()


# ---------------------------------------------------------------------------
# Stateless OAuth state / signed-code helpers
# ---------------------------------------------------------------------------

def encode_oauth_state(
    redirect_uri: str,
    client_state: str | None = None,
    code_challenge: str | None = None,
) -> str:
    """Pack the MCP client's OAuth params into a base64 blob for the Salesforce ``state``."""
    payload = {"redirect_uri": redirect_uri}
    if client_state:
        payload["client_state"] = client_state
    if code_challenge:
        payload["code_challenge"] = code_challenge
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_oauth_state(state_param: str) -> dict:
    """Unpack the base64 state blob returned by Salesforce's callback."""
    try:
        return json.loads(base64.urlsafe_b64decode(state_param))
    except Exception as exc:
        raise ValueError(f"Invalid OAuth state parameter: {exc}") from exc


def _hmac_sign(data: bytes) -> str:
    """Produce a hex HMAC-SHA256 signature over *data* using the server secret."""
    return hmac.new(
        mcp_settings.jwt_secret.encode(),
        data,
        hashlib.sha256,
    ).hexdigest()


def issue_auth_code(sf_token_response: dict) -> str:
    """Wrap a Salesforce token response in an HMAC-signed, time-limited code.

    The returned opaque string can be handed to the MCP client as an
    authorization ``code`` and later verified with ``redeem_auth_code``.
    """
    payload = {
        "access_token": sf_token_response["access_token"],
        "refresh_token": sf_token_response.get("refresh_token", ""),
        "instance_url": sf_token_response.get("instance_url", salesforce_settings.instance_url),
        "exp": int(time.time()) + mcp_settings.auth_code_ttl,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = _hmac_sign(payload_b64.encode())
    return f"{payload_b64}.{sig}"


def redeem_auth_code(code: str) -> dict:
    """Verify and unpack a signed auth code, returning the Salesforce token data.

    Raises ``ValueError`` if the signature is invalid or the code has expired.
    """
    parts = code.split(".", 1)
    if len(parts) != 2:
        raise ValueError("Malformed auth code")

    payload_b64, sig = parts
    expected_sig = _hmac_sign(payload_b64.encode())
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Invalid auth code signature")

    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:
        raise ValueError(f"Cannot decode auth code payload: {exc}") from exc

    if time.time() > payload.get("exp", 0):
        raise ValueError("Auth code has expired")

    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", ""),
        "instance_url": payload["instance_url"],
    }


# ---------------------------------------------------------------------------
# Compound token helpers (Bearer token = signed envelope with both tokens)
# ---------------------------------------------------------------------------

def issue_compound_token(sf_token_response: dict) -> str:
    """Wrap Salesforce tokens in an HMAC-signed Bearer token.

    The compound token is an opaque string that Claude stores and sends on
    every MCP request.  The middleware can decode it to check ``iat`` against
    ``access_token_ttl`` and return HTTP 401 when expired, triggering
    Claude's refresh flow.
    """
    payload = {
        "access_token": sf_token_response["access_token"],
        "refresh_token": sf_token_response.get("refresh_token", ""),
        "instance_url": sf_token_response.get("instance_url", salesforce_settings.instance_url),
        "iat": int(time.time()),
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = _hmac_sign(payload_b64.encode())
    return f"{payload_b64}.{sig}"


def decode_compound_token(token: str) -> dict:
    """Verify HMAC signature and return the decoded compound token payload.

    Returns dict with ``access_token``, ``refresh_token``, ``instance_url``,
    and ``iat``.  Raises ``ValueError`` on invalid format or signature.
    Does NOT check expiry — that is the middleware's responsibility.
    """
    parts = token.split(".", 1)
    if len(parts) != 2:
        raise ValueError("Not a compound token")

    payload_b64, sig = parts
    expected_sig = _hmac_sign(payload_b64.encode())
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Invalid compound token signature")

    try:
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:
        raise ValueError(f"Cannot decode compound token payload: {exc}") from exc
