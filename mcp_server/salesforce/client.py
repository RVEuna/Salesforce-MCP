"""Salesforce REST API client.

Instantiated per-request with the authenticated user's Bearer token.
All Salesforce RBAC (profiles, permission sets, FLS, sharing rules) is
enforced by Salesforce itself — this client just forwards the token.
"""

import logging
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class SalesforceError(Exception):
    """Raised when Salesforce returns a non-2xx response."""

    def __init__(self, status_code: int, error_code: str, message: str):
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(f"[{status_code}] {error_code}: {message}")


class SalesforceClient:
    """Async client for the Salesforce REST API.

    Each instance is scoped to a single user's access token and should
    not be reused across requests.
    """

    def __init__(self, access_token: str, instance_url: str, api_version: str = "v66.0"):
        self._base_url = f"{instance_url.rstrip('/')}/services/data/{api_version}"
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Execute an HTTP request against the Salesforce REST API.

        Surfaces Salesforce error responses directly so the MCP client
        sees the real permission/validation error from Salesforce.
        """
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method, url, headers=self._headers, timeout=30.0, **kwargs
            )

        if response.status_code >= 400:
            try:
                errors = response.json()
                if isinstance(errors, list) and errors:
                    err = errors[0]
                    raise SalesforceError(
                        response.status_code,
                        err.get("errorCode", "UNKNOWN"),
                        err.get("message", response.text),
                    )
                raise SalesforceError(
                    response.status_code,
                    "UNKNOWN",
                    str(errors),
                )
            except (ValueError, KeyError):
                raise SalesforceError(response.status_code, "UNKNOWN", response.text)

        if response.status_code == 204:
            return {}
        return response.json()

    async def query(self, soql: str) -> dict:
        """Execute a SOQL query.

        GET /query?q={soql}
        Returns: records array + totalSize + done
        """
        return await self._request("GET", "/query", params={"q": soql})

    async def search(self, sosl: str) -> dict:
        """Execute a SOSL search.

        GET /search?q={sosl}
        Returns: searchRecords array
        """
        return await self._request("GET", "/search", params={"q": sosl})

    async def describe_global(self) -> dict:
        """List all sobjects the user has access to.

        GET /sobjects
        """
        return await self._request("GET", "/sobjects")

    async def describe_sobject(self, sobject_name: str) -> dict:
        """Describe a single sobject (fields, relationships, record types).

        GET /sobjects/{sobject_name}/describe
        Salesforce returns 404 if the user's profile lacks access.
        """
        return await self._request("GET", f"/sobjects/{quote(sobject_name, safe='')}/describe")

    async def get_record(
        self, sobject_name: str, record_id: str, fields: list[str] | None = None
    ) -> dict:
        """Fetch a single record by ID.

        GET /sobjects/{sobject_name}/{record_id}?fields={comma-separated}
        Returns only fields the user has FLS access to.
        """
        params = {}
        if fields:
            params["fields"] = ",".join(fields)
        return await self._request(
            "GET",
            f"/sobjects/{quote(sobject_name, safe='')}/{quote(record_id, safe='')}",
            params=params or None,
        )

    async def get_related_records(
        self,
        sobject_name: str,
        record_id: str,
        relationship_name: str,
        fields: list[str] | None = None,
    ) -> dict:
        """Fetch related records for a given parent record.

        GET /sobjects/{sobject_name}/{record_id}/{relationship_name}
        """
        params = {}
        if fields:
            params["fields"] = ",".join(fields)
        safe = ""
        path = (
            f"/sobjects/{quote(sobject_name, safe=safe)}"
            f"/{quote(record_id, safe=safe)}"
            f"/{quote(relationship_name, safe=safe)}"
        )
        return await self._request("GET", path, params=params or None)

    async def get_user_info(self) -> dict:
        """Get the authenticated user's info.

        GET /chatter/users/me
        Returns: id, name, email, profile, username, etc.
        """
        return await self._request("GET", "/chatter/users/me")
