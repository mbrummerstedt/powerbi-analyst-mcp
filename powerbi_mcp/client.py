"""
Async Power BI REST API client.

Dataset discovery uses the org-level reports endpoint to avoid the workspace
membership requirement of the direct groups/datasets endpoint:

  GET /v1.0/myorg/reports
    → all user-visible reports with populated datasetId + datasetWorkspaceId
    → filter by datasetWorkspaceId == workspace_id to scope to the right app workspace

  GET /v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}
    → dataset metadata when the caller has workspace access
    → otherwise infer the dataset name from its reports

This avoids the 2-hop path (app reports → workspace reports) that fails with
401 for App (Build) users who have no direct workspace membership.

DAX execution uses the org-level endpoint which requires only Build permission
and works for app-granted access without direct workspace membership:
  POST /v1.0/myorg/datasets/{dataset_id}/executeQueries

Reference: https://learn.microsoft.com/en-us/rest/api/power-bi/
"""

from __future__ import annotations

from itertools import chain
from typing import Any
from uuid import UUID

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


def _guid(value: str, parameter: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as error:
        raise PowerBIError(400, f"{parameter} must be a GUID.") from error


def _dax_table_filter(table_name: str | None) -> str:
    if not table_name:
        return ""
    quoted_name = table_name.replace('"', '""')
    return f'\n    && [Table] = "{quoted_name}"'


def _dataset_name_from_reports(report_names: list[str]) -> str:
    """Infer a dataset name from the report names that reference it.

    Power BI conventions:
      "<DatasetName> - Report Template"       → "<DatasetName>"
      "<DatasetName> - Presentation Template" → "<DatasetName>"

    Falls back to the shortest report name when neither suffix is found.
    """
    for suffix in (" - Report Template", " - Presentation Template"):
        for name in report_names:
            if name.endswith(suffix):
                return name[: -len(suffix)]
    return min(report_names, key=len)


def _error_message(error: object, default: str) -> str:
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or default)
    return default


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        payload = response.json()
    except ValueError:
        payload = None
    error = payload.get("error") if isinstance(payload, dict) else None
    raise PowerBIError(response.status_code, _error_message(error, response.reason_phrase))


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

        The app endpoint may omit the dataset ID. Use ``list_datasets``
        to discover datasets via the organization-level reports endpoint.
        """
        url = f"{BASE_URL}/apps/{_guid(app_id, 'app_id')}/reports"
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
           ``datasetWorkspaceId`` matches the app's ``workspace_id``. Exclude
           reports that explicitly identify a different app.
        2. Deduplicate by ``datasetId``.
        3. ``GET /groups/{workspace_id}/datasets/{datasetId}``
           → dataset metadata or a name inferred from report names when
           metadata is inaccessible.

        Parameters
        ----------
        app_id:
            The ``id`` field from ``list_apps``.
        workspace_id:
            The ``workspaceId`` field from the same app in ``list_apps``.
            Used to filter org-level reports to only those belonging to this
            app's workspace.
        """
        import asyncio

        user_reports = await self.list_user_reports()

        # Filter to reports whose dataset lives in the target workspace,
        # and that actually have a dataset_id populated.
        # Track report names per dataset so we can synthesize a name if the
        # metadata fetch fails.
        seen: dict[str, tuple[str, list[str]]] = {}  # dataset_id → (workspace_id, report_names)
        for report in user_reports:
            if not report.dataset_id or not report.dataset_workspace_id:
                continue
            if report.dataset_workspace_id != workspace_id:
                continue
            if report.app_id and report.app_id.lower() != app_id.lower():
                continue
            if report.dataset_id not in seen:
                seen[report.dataset_id] = (report.dataset_workspace_id, [])
            seen[report.dataset_id][1].append(report.name)

        if not seen:
            return []

        async def _get_or_synthesize(
            ds_id: str, ds_ws_id: str, report_names: list[str]
        ) -> tuple[Dataset, str]:
            try:
                ds = await self.get_dataset(ds_ws_id, ds_id)
                return ds, ds_ws_id
            except PowerBIError as error:
                if error.status_code not in (401, 403, 404):
                    raise
                # App-only users may have Build permission without workspace membership.
                ds = Dataset(id=ds_id, name=_dataset_name_from_reports(report_names))
                return ds, ds_ws_id

        results = await asyncio.gather(
            *[_get_or_synthesize(ds_id, ws_id, names) for ds_id, (ws_id, names) in seen.items()]
        )

        return list(results)

    async def get_dataset_org(self, dataset_id: str) -> Dataset:
        """
        Return dataset metadata using the org-level endpoint.

        Does not require direct workspace membership — works with Build
        permission granted via a Power BI app.
        """
        url = f"{BASE_URL}/datasets/{_guid(dataset_id, 'dataset_id')}"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=self._headers)
            _raise_for_status(resp)
            return Dataset.model_validate(resp.json())

    async def get_dataset(self, workspace_id: str, dataset_id: str) -> Dataset:
        """Return metadata for a single dataset."""
        workspace_id = _guid(workspace_id, "workspace_id")
        dataset_id = _guid(dataset_id, "dataset_id")
        url = f"{BASE_URL}/groups/{workspace_id}/datasets/{dataset_id}"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=self._headers)
            _raise_for_status(resp)
            return Dataset.model_validate(resp.json())

    async def get_dataset_refresh_history(
        self, workspace_id: str, dataset_id: str, top: int = 10
    ) -> list[RefreshEntry]:
        """Return recent refresh history for a dataset."""
        workspace_id = _guid(workspace_id, "workspace_id")
        dataset_id = _guid(dataset_id, "dataset_id")
        url = f"{BASE_URL}/groups/{workspace_id}/datasets/{dataset_id}/refreshes"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(url, headers=self._headers, params={"$top": top})
            _raise_for_status(response)
            data = response.json().get("value", [])
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

        Uses the org-level executeQueries endpoint, which supports app-granted
        dataset access.

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
            GUID of the workspace that owns the dataset. Retained for client
            compatibility.
        dataset_id:
            GUID of the dataset to query.
        dax_query:
            A valid DAX query string (must start with EVALUATE).
        include_nulls:
            Whether to include null values in the result rows.
        """
        url = f"{BASE_URL}/datasets/{_guid(dataset_id, 'dataset_id')}/executeQueries"
        payload = {
            "queries": [{"query": dax_query}],
            "serializerSettings": {"includeNulls": include_nulls},
        }
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(url, headers=self._headers, json=payload)
            _raise_for_status(response)
            result = response.json()

        # Power BI can report truncation via an error in an HTTP 200 response.
        query_results = result.get("results", [])
        tables = (
            table
            for query_result in query_results
            for table in query_result.get("tables", [])
        )
        for envelope in chain((result,), query_results, tables):
            if error := envelope.get("error"):
                raise PowerBIError(
                    response.status_code, _error_message(error, "Incomplete DAX result")
                )
        return result

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
        table_filter = _dax_table_filter(table_name)
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
        table_filter = _dax_table_filter(table_name)
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
