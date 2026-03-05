"""
Power BI MCP Server
===================

An MCP server that exposes Power BI semantic models as analysis tools.

Authentication
--------------
Uses OAuth 2.0 device code flow (Microsoft Identity Platform).
Run  ``python server.py --login``  once to cache credentials, then start the
server normally.  Tokens are refreshed automatically by MSAL.

Required environment variable
------------------------------
POWERBI_CLIENT_ID  - Azure AD application (client) ID registered for this app.

Tools exposed
-------------
authenticate          - Initiate / refresh OAuth login (device code flow).
list_workspaces       - List Power BI workspaces the user is a member of.
list_datasets         - List datasets in a workspace.
get_dataset_info      - Detailed metadata for a single dataset.
list_tables           - List visible tables in a dataset.
list_measures         - List measures (optionally filtered by table).
list_columns          - List columns / dimensions (optionally filtered by table).
execute_dax           - Execute a DAX query and return the result rows.
"""

from __future__ import annotations

import sys
import textwrap

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from powerbi_mcp.auth import PowerBIAuth
from powerbi_mcp.config import Settings
from powerbi_mcp.tools import register_tools

try:
    settings = Settings()
except ValidationError as e:
    print(
        "Configuration error: POWERBI_CLIENT_ID is not set.\n"
        "Create a .env file or export the variable before starting the server.",
        file=sys.stderr,
    )
    sys.exit(1)

mcp = FastMCP(
    "Power BI",
    instructions=textwrap.dedent(
        """
        This server gives you read-only access to Power BI semantic models
        (datasets) via the Power BI REST API.

        Typical workflow:
        1. Call `authenticate` if this is the first run or the token has expired.
        2. Call `list_workspaces` to find the workspace_id that contains the
           dataset you want to analyse.
        3. Call `list_datasets` with that workspace_id.
        4. Call `list_tables`, `list_measures`, or `list_columns` to explore
           the data model structure.
        5. Call `execute_dax` to retrieve data using a DAX query.

        All dataset operations require BOTH a workspace_id AND a dataset_id
        because datasets always belong to a workspace (group) in Power BI.
        """
    ),
)

register_tools(mcp, settings.client_id, settings.tenant_id)

if __name__ == "__main__":
    if "--login" in sys.argv:
        print("Starting Power BI login (device code flow)…")
        auth = PowerBIAuth(settings.client_id, settings.tenant_id)
        existing = auth.get_token_silent()
        if existing:
            print("Already authenticated. Token is valid.")
            sys.exit(0)
        flow = auth.initiate_device_flow()
        print(flow["message"])
        try:
            auth.complete_device_flow(flow)
            print("Login successful. Token cached.")
        except RuntimeError as e:
            print(f"Login failed: {e}")
            sys.exit(1)
    else:
        mcp.run()
