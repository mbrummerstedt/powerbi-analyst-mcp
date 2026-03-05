"""
MCP tools for Power BI operations.

All MCP tool registrations for interacting with Power BI workspaces,
datasets, and executing DAX queries.
"""

from __future__ import annotations

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from .auth import PowerBIAuth
from .client import PowerBIClient, PowerBIError


def register_tools(mcp: FastMCP, client_id: str, tenant_id: str = "organizations") -> None:
    """
    Register all Power BI tools with the MCP server.

    Parameters
    ----------
    mcp:
        The FastMCP server instance.
    client_id:
        Azure AD application (client) ID for authentication.
    tenant_id:
        Azure AD tenant ID or "organizations" (default).
    """
    _auth = PowerBIAuth(client_id, tenant_id)

    def _get_client() -> PowerBIClient:
        """Return an authenticated API client, raising if no token is available."""
        token = _auth.get_token_silent()
        if token is None:
            raise RuntimeError(
                "Not authenticated. Call the `authenticate` tool first, then retry."
            )
        return PowerBIClient(token)

    def _fmt_json(obj: object) -> str:
        return json.dumps(obj, indent=2, ensure_ascii=False, default=str)

    @mcp.tool()
    async def authenticate() -> str:
        """
        Authenticate with Power BI using the OAuth 2.0 device code flow.

        Call this tool first if you have never logged in, or if a previous call
        returned "Not authenticated".

        The tool will return a short URL and a one-time code.  Open the URL in a
        browser (on any device), enter the code, and sign in with your
        Microsoft / Power BI account.  The tool waits for you to finish and then
        confirms success.  Your credentials are cached locally so you will not
        need to repeat this step until the refresh token expires (~90 days).
        """
        token = _auth.get_token_silent()
        if token:
            return "Already authenticated. No action needed."

        flow = _auth.initiate_device_flow()
        instructions = flow["message"]

        try:
            _auth.complete_device_flow(flow)
        except RuntimeError as exc:
            return f"Authentication failed: {exc}"

        return (
            f"{instructions}\n\n"
            "Authentication successful! You can now use all Power BI tools."
        )

    @mcp.tool()
    async def list_workspaces() -> str:
        """
        List all Power BI workspaces (groups) the authenticated user is a member of.

        Returns workspace id, name, type, and capacity information.
        Use the `id` field as `workspace_id` in subsequent tools.
        """
        client = _get_client()
        try:
            workspaces = await client.list_workspaces()
        except PowerBIError as exc:
            return f"Error listing workspaces: {exc}"

        if not workspaces:
            return "No workspaces found. The user may not be a member of any workspace."

        summary = [
            {
                "id": ws.id,
                "name": ws.name,
                "type": ws.type,
                "state": ws.state,
                "isOnDedicatedCapacity": ws.is_on_dedicated_capacity,
            }
            for ws in workspaces
        ]

        return _fmt_json(summary)

    @mcp.tool()
    async def list_datasets(
        workspace_id: Annotated[
            str,
            "The GUID of the Power BI workspace (group) to list datasets from. "
            "Obtain this from `list_workspaces`.",
        ],
    ) -> str:
        """
        List all datasets (semantic models) in a Power BI workspace.

        Returns dataset id, name, configured-by, web URL, is-refreshable flag,
        and the target storage mode (Import / DirectQuery / etc.).
        Use the `id` field as `dataset_id` in subsequent tools.
        """
        client = _get_client()
        try:
            datasets = await client.list_datasets(workspace_id)
        except PowerBIError as exc:
            return f"Error listing datasets: {exc}"

        if not datasets:
            return f"No datasets found in workspace {workspace_id!r}."

        summary = [
            {
                "id": ds.id,
                "name": ds.name,
                "configuredBy": ds.configured_by,
                "targetStorageMode": ds.target_storage_mode,
                "isRefreshable": ds.is_refreshable,
                "createdDate": ds.created_date,
                "webUrl": ds.web_url,
            }
            for ds in datasets
        ]

        return _fmt_json(summary)

    @mcp.tool()
    async def get_dataset_info(
        workspace_id: Annotated[
            str, "GUID of the workspace that contains the dataset."
        ],
        dataset_id: Annotated[str, "GUID of the dataset to inspect."],
    ) -> str:
        """
        Return detailed metadata for a single Power BI dataset.

        Includes name, owner, refresh schedule, storage mode, web URL, and more.
        Also returns the last 5 refresh history entries so you can see data freshness.
        """
        client = _get_client()
        try:
            info = await client.get_dataset(workspace_id, dataset_id)
            history = await client.get_dataset_refresh_history(
                workspace_id, dataset_id, top=5
            )
        except PowerBIError as exc:
            return f"Error retrieving dataset info: {exc}"

        output = {
            "dataset": {
                "id": info.id,
                "name": info.name,
                "description": info.description,
                "configuredBy": info.configured_by,
                "targetStorageMode": info.target_storage_mode,
                "isRefreshable": info.is_refreshable,
                "isEffectiveIdentityRequired": info.is_effective_identity_required,
                "isOnPremGatewayRequired": info.is_on_prem_gateway_required,
                "createdDate": info.created_date,
                "webUrl": info.web_url,
            },
            "recentRefreshes": [
                {
                    "requestId": r.request_id,
                    "status": r.status,
                    "startTime": r.start_time,
                    "endTime": r.end_time,
                    "refreshType": r.refresh_type,
                }
                for r in history
            ],
        }
        return _fmt_json(output)

    @mcp.tool()
    async def list_tables(
        workspace_id: Annotated[
            str, "GUID of the workspace that contains the dataset."
        ],
        dataset_id: Annotated[str, "GUID of the dataset to inspect."],
    ) -> str:
        """
        List all visible tables in a Power BI dataset.

        Hidden tables and internal Power BI system tables (names starting with '$')
        are excluded.  Use the returned table names in `list_measures`,
        `list_columns`, and DAX queries.
        """
        client = _get_client()
        try:
            tables = await client.list_tables(workspace_id, dataset_id)
        except PowerBIError as exc:
            return (
                f"Error listing tables: {exc}\n\n"
                "Note: listing tables requires the dataset to support DAX "
                "INFO.VIEW functions (available on Import / DirectQuery models "
                "with XMLA read access enabled)."
            )

        if not tables:
            return "No visible tables found in this dataset."

        summary = [
            {
                "name": t.name,
                "description": t.description,
                "isHidden": t.is_hidden,
            }
            for t in tables
        ]

        return _fmt_json(summary)

    @mcp.tool()
    async def list_measures(
        workspace_id: Annotated[
            str, "GUID of the workspace that contains the dataset."
        ],
        dataset_id: Annotated[str, "GUID of the dataset to inspect."],
        table_name: Annotated[
            str | None,
            "Optional: restrict results to measures in this table. "
            "Leave blank to return all measures.",
        ] = None,
    ) -> str:
        """
        List measures defined in a Power BI dataset.

        Returns each measure's name, parent table, description, format string,
        and DAX expression.  Optionally filter by table name.
        """
        client = _get_client()
        try:
            measures = await client.list_measures(workspace_id, dataset_id, table_name)
        except PowerBIError as exc:
            return f"Error listing measures: {exc}"

        if not measures:
            filter_note = f" in table {table_name!r}" if table_name else ""
            return f"No visible measures found{filter_note}."

        summary = [
            {
                "name": m.name,
                "tableName": m.table_name,
                "description": m.description,
                "formatString": m.format_string,
                "expression": m.expression,
            }
            for m in measures
        ]

        return _fmt_json(summary)

    @mcp.tool()
    async def list_columns(
        workspace_id: Annotated[
            str, "GUID of the workspace that contains the dataset."
        ],
        dataset_id: Annotated[str, "GUID of the dataset to inspect."],
        table_name: Annotated[
            str | None,
            "Optional: restrict results to columns in this table. "
            "Leave blank to return columns from all tables.",
        ] = None,
    ) -> str:
        """
        List columns (dimensions) in a Power BI dataset.

        Returns each column's name, parent table, description, data type, and
        whether it is a key column.  Optionally filter by table name.
        """
        client = _get_client()
        try:
            columns = await client.list_columns(workspace_id, dataset_id, table_name)
        except PowerBIError as exc:
            return f"Error listing columns: {exc}"

        if not columns:
            filter_note = f" in table {table_name!r}" if table_name else ""
            return f"No visible columns found{filter_note}."

        summary = [
            {
                "name": c.name,
                "tableName": c.table_name,
                "description": c.description,
                "dataType": c.data_type,
                "isKey": c.is_key,
            }
            for c in columns
        ]

        return _fmt_json(summary)

    @mcp.tool()
    async def execute_dax(
        workspace_id: Annotated[
            str, "GUID of the workspace that contains the dataset."
        ],
        dataset_id: Annotated[str, "GUID of the dataset to query."],
        dax_query: Annotated[
            str,
            "A valid DAX query. Must start with EVALUATE. "
            'Example: "EVALUATE SUMMARIZECOLUMNS(\'Date\'[Year], \\"Sales\\", [Total Sales])"',
        ],
    ) -> str:
        """
        Execute a DAX query against a Power BI dataset and return the result rows.

        The query must start with EVALUATE (standard DAX query syntax).
        Results are returned as a JSON array of objects, with column names as keys.

        Limitations imposed by the Power BI API:
        - Maximum 1,000,000 values or 100,000 rows per query.
        - Rate limit: 120 requests per minute per user.
        - Only DAX is supported; MDX and DMV queries are not.
        - The tenant setting "Dataset Execute Queries REST API" must be enabled.

        Tips:
        - Use TOPN or FILTER to limit large result sets.
        - Use SUMMARIZECOLUMNS for aggregated queries.
        - Use CALCULATETABLE for filtered table expressions.
        """
        client = _get_client()
        try:
            raw = await client.execute_dax(workspace_id, dataset_id, dax_query)
        except PowerBIError as exc:
            return f"DAX query error: {exc}"

        from .client import _parse_dax_rows

        rows = _parse_dax_rows(raw)

        if not rows:
            return "Query executed successfully but returned no rows."

        result = {
            "rowCount": len(rows),
            "rows": rows,
        }
        return _fmt_json(result)
