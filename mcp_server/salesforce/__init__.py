"""Salesforce client module."""

from mcp_server.salesforce.auth import get_salesforce_client
from mcp_server.salesforce.client import SalesforceClient

__all__ = ["SalesforceClient", "get_salesforce_client"]
