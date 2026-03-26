"""Local development helper — opens Salesforce login in the browser and captures an access token.

Starts a temporary local callback server, opens the Salesforce OAuth login page
in your browser, and prints the access token when you complete login.

Usage:
    python scripts/local-dev.py
    make local-token
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
CALLBACK_PORT = 8000
CALLBACK_URL = f"http://localhost:{CALLBACK_PORT}/oauth/callback"


def load_env() -> dict[str, str]:
    """Parse the .env file into a dict."""
    env = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def check_env(env: dict) -> None:
    required = {
        "SALESFORCE_LOGIN_URL": "Salesforce login URL",
        "SALESFORCE_CLIENT_ID": "Connected App client ID",
        "SALESFORCE_CLIENT_SECRET": "Connected App client secret",
    }
    for key, label in required.items():
        val = env.get(key, "")
        if not val or val.startswith("<"):
            print(f"  ERROR: {label} ({key}) is missing in .env")
            sys.exit(1)


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles the OAuth callback from Salesforce."""

    auth_code: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/oauth/callback":
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]

        if code:
            CallbackHandler.auth_code = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""<html><body style="font-family:system-ui;text-align:center;padding:60px">
                <h2>Login successful!</h2>
                <p>You can close this tab and return to your terminal.</p>
            </body></html>""")
        else:
            error = params.get("error_description", params.get("error", ["Unknown error"]))[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"""<html><body style="font-family:system-ui;text-align:center;padding:60px">
                <h2>Login failed</h2><p>{error}</p>
            </body></html>""".encode())

        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format, *args):
        pass  # suppress noisy HTTP logs


def exchange_code(env: dict, code: str) -> dict:
    """Exchange the authorization code for tokens."""
    login_url = env["SALESFORCE_LOGIN_URL"].rstrip("/")
    data = urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": env["SALESFORCE_CLIENT_ID"],
        "client_secret": env["SALESFORCE_CLIENT_SECRET"],
        "redirect_uri": CALLBACK_URL,
    }).encode()

    req = Request(
        f"{login_url}/services/oauth2/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except HTTPError as exc:
        body = exc.read().decode()
        try:
            err = json.loads(body)
            msg = err.get("error_description", body)
        except json.JSONDecodeError:
            msg = body
        print(f"\n  ERROR: Token exchange failed: {msg}")
        sys.exit(1)


def main():
    print("\n  Salesforce MCP — Local Token Helper")
    print("  " + "=" * 40)

    if not ENV_FILE.exists():
        print("  ERROR: .env file not found. Copy .env.example to .env first.")
        sys.exit(1)

    env = load_env()
    check_env(env)

    login_url = env["SALESFORCE_LOGIN_URL"].rstrip("/")
    client_id = env["SALESFORCE_CLIENT_ID"]

    # Start temporary callback server
    server = http.server.HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)

    auth_url = (
        f"{login_url}/services/oauth2/authorize?"
        + urlencode({
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": CALLBACK_URL,
            "scope": "api refresh_token",
        })
    )

    print(f"\n  Opening Salesforce login in your browser...")
    print(f"  (If it doesn't open, visit this URL manually:)")
    print(f"  {auth_url}\n")

    webbrowser.open(auth_url)

    print("  Waiting for login...", end="", flush=True)
    server.serve_forever()

    if not CallbackHandler.auth_code:
        print("\n  ERROR: No authorization code received.")
        sys.exit(1)

    print(" done!")
    print("  Exchanging code for token...", end="", flush=True)

    tokens = exchange_code(env, CallbackHandler.auth_code)
    print(" done!\n")

    access_token = tokens["access_token"]
    instance_url = tokens.get("instance_url", "")

    print("  " + "=" * 40)
    print("  Add this to your .env file:\n")
    print(f"  SALESFORCE_ACCESS_TOKEN={access_token}")
    print(f"\n  Instance: {instance_url}")
    print("  " + "=" * 40)

    # Also check if Connected App callback URL is configured
    print(f"""
  Uses the same callback URL as your Connected App:
    {CALLBACK_URL}
""")


if __name__ == "__main__":
    main()
