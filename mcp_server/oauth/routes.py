"""OAuth 2.0 HTTP routes for the MCP server.

The server acts as an authorization-server proxy: MCP clients (mcp-remote,
Claude.ai) discover these endpoints via RFC 8414 metadata, then the server
brokers the full Salesforce Authorization Code flow on the user's behalf.

Design: fully stateless.  Client params are encoded in the Salesforce
``state`` parameter; the Salesforce access token is wrapped in an
HMAC-signed short-lived code returned to the MCP client.
"""

import uuid
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from mcp_server.config import mcp_settings, salesforce_settings
from mcp_server.salesforce.auth import (
    build_authorization_url,
    decode_oauth_state,
    encode_oauth_state,
    exchange_code_for_token,
    issue_auth_code,
    issue_compound_token,
    redeem_auth_code,
    refresh_salesforce_token,
)


async def oauth_protected_resource(request: Request) -> Response:
    """RFC 9470 protected resource metadata.

    Tells the MCP client which authorization server protects this resource.
    """
    base = mcp_settings.base_url.rstrip("/")
    return JSONResponse({
        "resource": base,
        "authorization_servers": [base],
    })


async def oauth_metadata(request: Request) -> Response:
    """RFC 8414 authorization server metadata (discovery endpoint)."""
    base = mcp_settings.base_url.rstrip("/")
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
    })


async def oauth_register(request: Request) -> Response:
    """RFC 7591 Dynamic Client Registration.

    mcp-remote registers itself as a client before starting the OAuth flow.
    Since we proxy to Salesforce (which has its own Connected App), we don't
    need to persist registrations — just acknowledge with a client_id.
    """
    body = await request.json()
    client_id = str(uuid.uuid4())
    return JSONResponse({
        "client_id": client_id,
        "client_name": body.get("client_name", "mcp-client"),
        "redirect_uris": body.get("redirect_uris", []),
        "grant_types": body.get("grant_types", ["authorization_code"]),
        "response_types": body.get("response_types", ["code"]),
        "token_endpoint_auth_method": "none",
    }, status_code=201)


async def oauth_authorize(request: Request) -> Response:
    """Begin the OAuth flow — redirect the user's browser to Salesforce login.

    Expected query params (set by mcp-remote / Claude.ai):
        redirect_uri  – where the MCP client wants the final code delivered
        state         – opaque value the client expects echoed back
        code_challenge – PKCE challenge (mcp-remote → this server leg only)
    """
    redirect_uri = request.query_params.get("redirect_uri", "")
    client_state = request.query_params.get("state", "")
    code_challenge = request.query_params.get("code_challenge", "")

    if not redirect_uri:
        return JSONResponse({"error": "redirect_uri is required"}, status_code=400)

    packed_state = encode_oauth_state(redirect_uri, client_state, code_challenge)

    sf_callback = f"{mcp_settings.base_url.rstrip('/')}/oauth/callback"
    sf_url = build_authorization_url(redirect_uri=sf_callback, state=packed_state)

    return RedirectResponse(sf_url, status_code=302)


async def oauth_callback(request: Request) -> Response:
    """Handle the Salesforce redirect after user login.

    Salesforce sends ``code`` (the SF auth code) and ``state`` (our packed
    blob).  We exchange the code for a real token, wrap it in a signed code,
    and redirect back to the MCP client's ``redirect_uri``.
    """
    sf_code = request.query_params.get("code", "")
    state_param = request.query_params.get("state", "")

    if not sf_code or not state_param:
        return JSONResponse({"error": "Missing code or state from Salesforce"}, status_code=400)

    try:
        client_params = decode_oauth_state(state_param)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    client_redirect = client_params["redirect_uri"]
    client_state = client_params.get("client_state", "")

    sf_callback = f"{mcp_settings.base_url.rstrip('/')}/oauth/callback"

    try:
        sf_tokens = await exchange_code_for_token(code=sf_code, redirect_uri=sf_callback)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    signed_code = issue_auth_code(sf_tokens)

    params = {"code": signed_code}
    if client_state:
        params["state"] = client_state

    separator = "&" if "?" in client_redirect else "?"
    return RedirectResponse(
        f"{client_redirect}{separator}{urlencode(params)}",
        status_code=302,
    )


async def oauth_token(request: Request) -> Response:
    """Exchange a signed auth code or refresh token for a Salesforce access token.

    Supports two grant types:
    - ``authorization_code``: redeems the HMAC-signed code from the callback.
    - ``refresh_token``: exchanges a Salesforce refresh token for a new access
      token, enabling silent token renewal without user interaction.
    """
    form = await request.form()
    grant_type = str(form.get("grant_type", "authorization_code"))

    if grant_type == "refresh_token":
        old_refresh_token = str(form.get("refresh_token", ""))
        if not old_refresh_token:
            return JSONResponse({"error": "refresh_token is required"}, status_code=400)

        try:
            new_sf_tokens = await refresh_salesforce_token(old_refresh_token)
        except ValueError:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Refresh token is invalid or expired"},
                status_code=400,
            )

        return JSONResponse({
            "access_token": issue_compound_token(new_sf_tokens),
            "refresh_token": new_sf_tokens.get("refresh_token", old_refresh_token),
            "token_type": "Bearer",
            "expires_in": salesforce_settings.access_token_ttl,
            "scope": "api",
        })

    code = str(form.get("code", ""))
    if not code:
        return JSONResponse({"error": "code is required"}, status_code=400)

    try:
        token_data = redeem_auth_code(code)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    return JSONResponse({
        "access_token": issue_compound_token(token_data),
        "refresh_token": token_data["refresh_token"],
        "token_type": "Bearer",
        "expires_in": salesforce_settings.access_token_ttl,
        "scope": "api",
    })


oauth_routes = [
    Route("/.well-known/oauth-protected-resource/{path:path}", oauth_protected_resource),
    Route("/.well-known/oauth-protected-resource", oauth_protected_resource),
    Route("/.well-known/oauth-authorization-server", oauth_metadata),
    Route("/oauth/register", oauth_register, methods=["POST"]),
    Route("/oauth/authorize", oauth_authorize),
    Route("/oauth/callback", oauth_callback),
    Route("/oauth/token", oauth_token, methods=["POST"]),
]
