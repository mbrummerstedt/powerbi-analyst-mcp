"""
Integration tests against the live Power BI REST API.

These tests are SKIPPED automatically when no cached token exists.
To run them:

  1. python server.py --login
  2. pytest tests/integration/ -v

Tests make structural assertions only (valid JSON shape, presence of required
fields) — no hardcoded workspace or dataset IDs are required.
"""

from __future__ import annotations

import json
import uuid

import pytest

from powerbi_mcp.auth import TOKEN_CACHE_PATH, PowerBIAuth
from powerbi_mcp.client import PowerBIClient
from powerbi_mcp.config import Settings

pytestmark = pytest.mark.skipif(
    not TOKEN_CACHE_PATH.exists(),
    reason="No cached token — run 'python server.py --login' first",
)


@pytest.fixture(scope="module")
def live_client() -> PowerBIClient:
    """Authenticated client using the real cached token."""
    settings = Settings()
    auth = PowerBIAuth(settings.client_id)
    token = auth.get_token_silent()
    if token is None:
        pytest.skip("Token cache exists but no valid token — re-run login")
    return PowerBIClient(token)


# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------


class TestLiveListApps:
    async def test_returns_list(self, live_client: PowerBIClient):
        apps = await live_client.list_apps()
        assert isinstance(apps, list)

    async def test_each_app_has_id_name_and_workspace_id(self, live_client: PowerBIClient):
        apps = await live_client.list_apps()
        if not apps:
            pytest.skip("No installed apps for this account")
        for app in apps:
            assert app.id, "app id must be non-empty"
            assert app.name, "app name must be non-empty"
            uuid.UUID(app.id)
            if app.workspace_id:
                uuid.UUID(app.workspace_id)

    async def test_workspace_id_can_list_datasets(self, live_client: PowerBIClient):
        """The workspaceId from an app should be usable to list datasets."""
        apps = await live_client.list_apps()
        for app in apps:
            if app.workspace_id:
                datasets = await live_client.list_datasets(app.workspace_id)
                assert isinstance(datasets, list)
                return
        pytest.skip("No apps with workspaceId found")


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


class TestLiveListWorkspaces:
    async def test_returns_json_array(self, live_client: PowerBIClient):
        workspaces = await live_client.list_workspaces()
        assert isinstance(workspaces, list)

    async def test_each_workspace_has_id_and_name(self, live_client: PowerBIClient):
        workspaces = await live_client.list_workspaces()
        for ws in workspaces:
            assert ws.id, "workspace id must be non-empty"
            assert ws.name, "workspace name must be non-empty"
            # id should be a valid UUID
            uuid.UUID(ws.id)


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


class TestLiveListDatasets:
    async def test_datasets_in_first_workspace(self, live_client: PowerBIClient):
        workspaces = await live_client.list_workspaces()
        if not workspaces:
            pytest.skip("No workspaces available for this account")
        datasets = await live_client.list_datasets(workspaces[0].id)
        # May be empty — just assert the call succeeds and returns a list
        assert isinstance(datasets, list)

    async def test_dataset_fields_when_present(self, live_client: PowerBIClient):
        workspaces = await live_client.list_workspaces()
        for ws in workspaces:
            datasets = await live_client.list_datasets(ws.id)
            if datasets:
                ds = datasets[0]
                assert ds.id
                assert ds.name
                uuid.UUID(ds.id)
                return
        pytest.skip("No datasets found across all workspaces")


# ---------------------------------------------------------------------------
# Dataset info
# ---------------------------------------------------------------------------


class TestLiveGetDatasetInfo:
    async def test_response_has_expected_fields(self, live_client: PowerBIClient):
        workspaces = await live_client.list_workspaces()
        for ws in workspaces:
            datasets = await live_client.list_datasets(ws.id)
            if datasets:
                ds = datasets[0]
                info = await live_client.get_dataset(ws.id, ds.id)
                assert info.id == ds.id
                assert info.name == ds.name
                history = await live_client.get_dataset_refresh_history(ws.id, ds.id, top=5)
                assert isinstance(history, list)
                return
        pytest.skip("No datasets found")


# ---------------------------------------------------------------------------
# DAX execution — universal smoke test
# ---------------------------------------------------------------------------


class TestLiveExecuteDax:
    async def test_row_function_returns_one_row(self, live_client: PowerBIClient):
        """EVALUATE ROW(...) always returns exactly 1 row regardless of dataset."""
        workspaces = await live_client.list_workspaces()
        for ws in workspaces:
            datasets = await live_client.list_datasets(ws.id)
            if datasets:
                raw = await live_client.execute_dax(
                    ws.id,
                    datasets[0].id,
                    'EVALUATE ROW("TestColumn", 42)',
                )
                from powerbi_mcp.client import _parse_dax_rows
                rows = _parse_dax_rows(raw)
                assert len(rows) == 1
                assert rows[0].get("TestColumn") == 42
                return
        pytest.skip("No datasets available for DAX execution")
