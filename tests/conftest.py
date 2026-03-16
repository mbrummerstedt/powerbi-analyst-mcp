"""
Shared fixtures and mock payloads for the Power BI MCP Server test suite.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

APP_ID = "eeeeeeee-0000-0000-0000-000000000005"
WORKSPACE_ID = "aaaaaaaa-0000-0000-0000-000000000001"
DATASET_ID = "bbbbbbbb-0000-0000-0000-000000000002"
FAKE_TOKEN = "fake-bearer-token"


# ---------------------------------------------------------------------------
# Raw API payload factories — mirror the actual Power BI REST API shapes
# ---------------------------------------------------------------------------


def make_app_payload(
    *,
    id: str = APP_ID,
    name: str = "Test App",
    description: str = "A test app",
    published_by: str = "Data Insight",
    last_update: str = "2026-03-16T14:06:32.021Z",
    workspace_id: str = WORKSPACE_ID,
) -> dict:
    return {
        "id": id,
        "name": name,
        "description": description,
        "publishedBy": published_by,
        "lastUpdate": last_update,
        "workspaceId": workspace_id,
    }


def make_workspace_payload(
    *,
    id: str = WORKSPACE_ID,
    name: str = "Test Workspace",
    type: str = "Workspace",
    state: str = "Active",
    is_on_dedicated_capacity: bool = False,
) -> dict:
    return {
        "id": id,
        "name": name,
        "type": type,
        "state": state,
        "isOnDedicatedCapacity": is_on_dedicated_capacity,
    }


def make_dataset_payload(
    *,
    id: str = DATASET_ID,
    name: str = "Test Dataset",
    configured_by: str = "user@example.com",
    target_storage_mode: str = "Import",
    is_refreshable: bool = True,
    created_date: str = "2024-01-15T10:00:00Z",
    web_url: str = "https://app.powerbi.com/groups/me/datasets/bbbbbbbb",
    description: str = "",
    is_effective_identity_required: bool = False,
    is_on_prem_gateway_required: bool = False,
) -> dict:
    return {
        "id": id,
        "name": name,
        "configuredBy": configured_by,
        "targetStorageMode": target_storage_mode,
        "isRefreshable": is_refreshable,
        "createdDate": created_date,
        "webUrl": web_url,
        "description": description,
        "isEffectiveIdentityRequired": is_effective_identity_required,
        "isOnPremGatewayRequired": is_on_prem_gateway_required,
    }


def make_refresh_entry_payload(
    *,
    request_id: str = "cccccccc-0000-0000-0000-000000000003",
    status: str = "Completed",
    start_time: str = "2024-01-15T08:00:00Z",
    end_time: str = "2024-01-15T08:05:00Z",
    refresh_type: str = "Scheduled",
) -> dict:
    return {
        "requestId": request_id,
        "status": status,
        "startTime": start_time,
        "endTime": end_time,
        "refreshType": refresh_type,
    }


def make_dax_response(rows: list[dict]) -> dict:
    """Wrap rows in the nested Power BI executeQueries response envelope."""
    return {
        "results": [
            {
                "tables": [
                    {
                        "rows": rows,
                    }
                ]
            }
        ]
    }


def make_table_dax_row(name: str = "Sales", description: str = "") -> dict:
    """A single row as returned by DAX INFO.VIEW.TABLES() after bracket-stripping."""
    return {"Name": name, "Description": description, "IsHidden": False}


def make_measure_dax_row(
    name: str = "Total Sales",
    table_name: str = "Sales",
    description: str = "",
    format_string: str = "#,##0",
) -> dict:
    return {
        "Name": name,
        "TableName": table_name,
        "Description": description,
        "FormatString": format_string,
    }


def make_column_dax_row(
    name: str = "ProductName",
    table_name: str = "Products",
    description: str = "",
    data_type: str = "String",
    is_key: bool = False,
) -> dict:
    return {
        "Name": name,
        "TableName": table_name,
        "Description": description,
        "DataType": data_type,
        "IsKey": is_key,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_payload() -> dict:
    return make_app_payload()


@pytest.fixture
def workspace_payload() -> dict:
    return make_workspace_payload()


@pytest.fixture
def dataset_payload() -> dict:
    return make_dataset_payload()


@pytest.fixture
def refresh_entry_payload() -> dict:
    return make_refresh_entry_payload()


@pytest.fixture
def mock_token():
    """Patch PowerBIAuth.get_token_silent to return a fake token."""
    with patch(
        "powerbi_mcp.auth.PowerBIAuth.get_token_silent",
        return_value=FAKE_TOKEN,
    ) as mock:
        yield mock
