"""
Async Power BI REST API client.

Dataset discovery uses the org-level reports endpoint to avoid the workspace
membership requirement of the direct groups/datasets endpoint:

  GET /v1.0/myorg/reports
    → all user-visible reports with populated datasetId + datasetWorkspaceId
    → filter by datasetWorkspaceId == workspace_id to scope to the right app workspace

  GET /v1.0/myorg/datasets/{dataset_id}
    → dataset metadata (org-level; requires only Build permission)

This avoids the 2-hop path (app reports → workspace reports) that fails with
401 for App (Build) users who have no direct workspace membership.

DAX execution uses the org-level endpoint which requires only Build permission
and works for app-granted access without direct workspace membership:
  POST /v1.0/myorg/datasets/{dataset_id}/executeQueries

Reference: https://learn.microsoft.com/en-us/rest/api/power-bi/
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from .models import (
    App,
    AppReport,
    Column,
    Dataset,
    Measure,
    RefreshEntry,
    Table,
    UserReport,
    Workspace,
)

BASE_URL = "https://api.powerbi.com/v1.0/myorg"
DEFAULT_TIMEOUT = 120


class PowerBIError(Exception):
    """Raised when the Power BI API returns an error response."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Power BI API error {status_code}: {message}")


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_error:
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except Exception:
            detail = response.text
        raise PowerBIError(response.status_code, detail)


class PowerBIClient:
    """
    Thin async wrapper around the Power BI REST API.

    Parameters
    ----------
    token:
        A valid Bearer access token obtained from MSAL.
    """

    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def list_apps(self) -> list[App]:
        """Return all installed Power BI apps for the authenticated user."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(f"{BASE_URL}/apps", headers=self._headers)
            _raise_for_status(resp)
            data = resp.json().get("value", [])
            return [App.model_validate(app) for app in data]

    async def list_workspaces(self) -> list[Workspace]:
        """Return all workspaces the authenticated user is a member of."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(f"{BASE_URL}/groups", headers=self._headers)
            _raise_for_status(resp)
            data = resp.json().get("value", [])
            return [Workspace.model_validate(ws) for ws in data]

    async def list_app_reports(self, app_id: str) -> list[AppReport]:
        """
        Return all reports in a Power BI app.

        Note: ``datasetId`` in the returned reports is deliberately empty —
        the app endpoint detaches reports from datasets.  Use
        ``list_datasets`` which resolves the real datasetId via
        ``originalReportObjectId``.
        """
        url = f"{BASE_URL}/apps/{app_id}/reports"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=self._headers)
            _raise_for_status(resp)
            data = resp.json().get("value", [])
            return [AppReport.model_validate(r) for r in data]

    async def list_user_reports(self) -> list[UserReport]:
        """Return all reports visible to the authenticated user (org-level)."""
        url = f"{BASE_URL}/reports"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=self._headers)
            _raise_for_status(resp)
            data = resp.json().get("value", [])
            return [UserReport.model_validate(r) for r in data]

    async def list_datasets(
        self, app_id: str, workspace_id: str
    ) -> list[tuple[Dataset, str]]:
        """
        Discover datasets accessible through a Power BI app.

        Returns a list of ``(Dataset, workspace_id)`` tuples where
        ``workspace_id`` is the workspace that owns the dataset (use this in
        ``list_tables``, ``list_measures``, ``execute_dax``, etc.).

        Discovery path (avoids the workspace-membership requirement of the
        direct ``/groups/{ws}/datasets`` endpoint, and the 401 failure of the
        2-hop app-reports → workspace-reports path for App-only users):

        1. ``GET /myorg/reports``
           → all user-visible reports with populated ``datasetId`` and
           ``datasetWorkspaceId``.  Filter to those whose
           ``datasetWorkspaceId`` matches the app's ``workspace_id``.
        2. Deduplicate by ``datasetId``.
        3. ``GET /datasets/{datasetId}`` (org-level, Build permission only)
           → dataset metadata, resolved in parallel.

        Parameters
        ----------
        app_id:
            The ``id`` field from ``list_apps``.  Not used directly in the
            new discovery path but kept for API symmetry and future use.
        workspace_id:
            The ``workspaceId`` field from the same app in ``list_apps``.
            Used to filter org-level reports to only those belonging to this
            app's workspace.
        """
        import asyncio

        user_reports = await self.list_user_reports()

        # Filter to reports whose dataset lives in the target workspace,
        # and that actually have a dataset_id populated.
        seen: dict[str, str] = {}  # dataset_id → workspace_id
        for report in user_reports:
            if not report.dataset_id or not report.dataset_workspace_id:
                continue
            if report.dataset_workspace_id != workspace_id:
                continue
            if report.dataset_id not in seen:
                seen[report.dataset_id] = report.dataset_workspace_id

        if not seen:
            return []

        async def _safe_get_dataset(
            ds_id: str, ws_id: str
        ) -> tuple[Dataset | None, str]:
            try:
                ds = await self.get_dataset_org(ds_id)
                return ds, ws_id
            except PowerBIError:
                return None, ws_id

        dataset_results = await asyncio.gather(
            *[_safe_get_dataset(ds_id, ws_id) for ds_id, ws_id in seen.items()]
        )

        return [(ds, ws_id) for ds, ws_id in dataset_results if ds is not None]

    async def get_dataset_org(self, dataset_id: str) -> Dataset:
        """
        Return dataset metadata using the org-level endpoint.

        Does not require direct workspace membership — works with Build
        permission granted via a Power BI app.
        """
        url = f"{BASE_URL}/datasets/{dataset_id}"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=self._headers)
            _raise_for_status(resp)
            return Dataset.model_validate(resp.json())

    async def get_dataset(self, workspace_id: str, dataset_id: str) -> Dataset:
        """Return metadata for a single dataset."""
        url = f"{BASE_URL}/groups/{workspace_id}/datasets/{dataset_id}"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=self._headers)
            _raise_for_status(resp)
            return Dataset.model_validate(resp.json())

    async def get_dataset_refresh_history(
        self, workspace_id: str, dataset_id: str, top: int = 10
    ) -> list[RefreshEntry]:
        """Return recent refresh history for a dataset."""
        url = (
            f"{BASE_URL}/groups/{workspace_id}/datasets/{dataset_id}"
            f"/refreshes?$top={top}"
        )
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=self._headers)
            _raise_for_status(resp)
            data = resp.json().get("value", [])
            return [RefreshEntry.model_validate(entry) for entry in data]

    async def execute_dax(
        self,
        workspace_id: str,
        dataset_id: str,
        dax_query: str,
        include_nulls: bool = True,
    ) -> dict[str, Any]:
        """
        Execute a DAX query against a dataset and return the raw API response.

        Uses the in-group executeQueries endpoint. The workspace_id must come
        from list_apps (the app's workspaceId field), not from list_workspaces —
        this ensures the correct app-granted permission context is used.

        The response shape is:
        {
          "results": [
            {
              "tables": [
                {
                  "rows": [{"[Column]": value, ...}, ...]
                }
              ]
            }
          ]
        }

        Parameters
        ----------
        workspace_id:
            GUID of the workspace (group) that owns the dataset. Must be
            obtained from list_apps workspaceId, not list_workspaces.
        dataset_id:
            GUID of the dataset to query.
        dax_query:
            A valid DAX query string (must start with EVALUATE).
        include_nulls:
            Whether to include null values in the result rows.
        """
        # Use org-level endpoint (not in-group) so app-granted access works.
        # In-group executeQueries requires workspace membership; org-level only
        # requires Build permission on the dataset, which is what Power BI Apps
        # grant. workspace_id is kept in the signature for API symmetry and
        # future use but is not part of the URL.
        del workspace_id  # intentionally unused — see comment above
        url = f"{BASE_URL}/datasets/{dataset_id}/executeQueries"
        payload = {
            "queries": [{"query": dax_query}],
            "serializerSettings": {"includeNulls": include_nulls},
        }
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, headers=self._headers, json=payload)
            _raise_for_status(resp)
            return resp.json()

    async def list_tables(self, workspace_id: str, dataset_id: str) -> list[Table]:
        """
        Return user-visible tables in a dataset.

        Filters out hidden tables and internal Power BI system tables
        (those whose names start with '$').
        """
        dax = """
EVALUATE
SELECTCOLUMNS(
    FILTER(
        INFO.VIEW.TABLES(),
        NOT [IsHidden] && LEFT([Name], 1) <> "$"
    ),
    "Name",        [Name],
    "Description", [Description],
    "IsHidden",    [IsHidden]
)
ORDER BY [Name]
""".strip()
        result = await self.execute_dax(workspace_id, dataset_id, dax)
        rows = _parse_dax_rows(result)
        return [Table.model_validate(row) for row in rows]

    async def list_measures(
        self, workspace_id: str, dataset_id: str, table_name: str | None = None
    ) -> list[Measure]:
        """
        Return measures defined in the dataset.

        INFO.VIEW.MEASURES() exposes the table name via the [Table] column
        (not [TableName] as the older INFO.MEASURES() schema used).

        Parameters
        ----------
        table_name:
            If provided, only return measures from that table.
        """
        table_filter = (
            f'\n    && [Table] = "{table_name}"'
            if table_name
            else ""
        )
        dax = f"""
EVALUATE
SELECTCOLUMNS(
    FILTER(
        INFO.VIEW.MEASURES(),
        NOT [IsHidden]{table_filter}
    ),
    "Name",         [Name],
    "TableName",    [Table],
    "Description",  [Description],
    "FormatString", [FormatString]
)
ORDER BY [TableName], [Name]
""".strip()
        result = await self.execute_dax(workspace_id, dataset_id, dax)
        rows = _parse_dax_rows(result)
        return [Measure.model_validate(row) for row in rows]

    async def list_columns(
        self, workspace_id: str, dataset_id: str, table_name: str | None = None
    ) -> list[Column]:
        """
        Return columns (dimensions) defined in the dataset.

        INFO.VIEW.COLUMNS() exposes the table name via [Table] (not [TableName]),
        uses [Name] and [DataType] directly (not [ExplicitName]/[ExplicitDataType]),
        and [Type] is a string: "Data" selects regular source columns only
        (excludes "Calculated", "CalculatedTableColumn", "RowNumber", etc.).

        Parameters
        ----------
        table_name:
            If provided, only return columns from that table.
        """
        table_filter = (
            f'\n    && [Table] = "{table_name}"'
            if table_name
            else ""
        )
        dax = f"""
EVALUATE
SELECTCOLUMNS(
    FILTER(
        INFO.VIEW.COLUMNS(),
        NOT [IsHidden] && [Type] = "Data"{table_filter}
    ),
    "Name",         [Name],
    "TableName",    [Table],
    "Description",  [Description],
    "DataType",     [DataType],
    "IsKey",        [IsKey]
)
ORDER BY [TableName], [Name]
""".strip()
        result = await self.execute_dax(workspace_id, dataset_id, dax)
        rows = _parse_dax_rows(result)
        return [Column.model_validate(row) for row in rows]


def _parse_dax_rows(api_response: dict[str, Any]) -> list[dict]:
    """
    Flatten the nested DAX executeQueries response into a plain list of dicts.

    Power BI returns column names prefixed with the table name in brackets,
    e.g. ``"[Name]"``.  This helper strips those brackets for cleaner output.
    """
    rows: list[dict] = []
    for result in api_response.get("results", []):
        for table in result.get("tables", []):
            for row in table.get("rows", []):
                clean_row = {_strip_brackets(k): v for k, v in row.items()}
                rows.append(clean_row)
    return rows


def _strip_brackets(name: str) -> str:
    """Remove leading [ and trailing ] from a DAX column name."""
    if name.startswith("[") and name.endswith("]"):
        return name[1:-1]
    return name
