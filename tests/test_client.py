"""
Tests for PowerBIClient and helper functions in powerbi_mcp/client.py.

HTTP calls are intercepted by respx so no real network traffic occurs.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from powerbi_mcp.client import (
    PowerBIClient,
    PowerBIError,
    _dataset_name_from_reports,
    _parse_dax_rows,
    _strip_brackets,
)
from powerbi_mcp.models import App, Column, Dataset, Measure, RefreshEntry, Table, Workspace
from tests.conftest import (
    APP_ID,
    DATASET_ID,
    FAKE_TOKEN,
    WORKSPACE_ID,
    make_app_payload,
    make_column_dax_row,
    make_dataset_payload,
    make_dax_response,
    make_measure_dax_row,
    make_refresh_entry_payload,
    make_table_dax_row,
    make_user_report_payload,
    make_workspace_payload,
)

BASE = "https://api.powerbi.com/v1.0/myorg"


@pytest.fixture
def client() -> PowerBIClient:
    return PowerBIClient(FAKE_TOKEN)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestStripBrackets:
    def test_strips_bracketed_name(self):
        assert _strip_brackets("[Name]") == "Name"

    def test_strips_multi_word_name(self):
        assert _strip_brackets("[Total Sales]") == "Total Sales"

    def test_leaves_plain_string_unchanged(self):
        assert _strip_brackets("Name") == "Name"

    def test_leaves_partial_bracket_unchanged(self):
        assert _strip_brackets("[Name") == "[Name"
        assert _strip_brackets("Name]") == "Name]"

    def test_empty_brackets_become_empty_string(self):
        assert _strip_brackets("[]") == ""


class TestParseDaxRows:
    def test_flattens_nested_structure(self):
        raw = make_dax_response([{"[Name]": "Sales", "[IsHidden]": False}])
        rows = _parse_dax_rows(raw)
        assert rows == [{"Name": "Sales", "IsHidden": False}]

    def test_strips_brackets_from_keys(self):
        raw = make_dax_response([{"[TableName]": "T", "[Expression]": "SUM(x)"}])
        rows = _parse_dax_rows(raw)
        assert rows[0] == {"TableName": "T", "Expression": "SUM(x)"}

    def test_multiple_rows(self):
        raw = make_dax_response([
            {"[Name]": "A"},
            {"[Name]": "B"},
            {"[Name]": "C"},
        ])
        rows = _parse_dax_rows(raw)
        assert len(rows) == 3
        assert [r["Name"] for r in rows] == ["A", "B", "C"]

    def test_empty_results(self):
        assert _parse_dax_rows({}) == []
        assert _parse_dax_rows({"results": []}) == []

    def test_empty_rows(self):
        raw = {"results": [{"tables": [{"rows": []}]}]}
        assert _parse_dax_rows(raw) == []


# ---------------------------------------------------------------------------
# PowerBIClient tests
# ---------------------------------------------------------------------------


class TestListApps:
    @respx.mock
    async def test_returns_typed_models(self, client: PowerBIClient):
        respx.get(f"{BASE}/apps").mock(
            return_value=Response(200, json={"value": [make_app_payload()]})
        )
        result = await client.list_apps()
        assert len(result) == 1
        assert isinstance(result[0], App)
        assert result[0].id == APP_ID
        assert result[0].workspace_id == WORKSPACE_ID

    @respx.mock
    async def test_correct_url(self, client: PowerBIClient):
        route = respx.get(f"{BASE}/apps").mock(
            return_value=Response(200, json={"value": []})
        )
        await client.list_apps()
        assert route.called

    @respx.mock
    async def test_empty_value_returns_empty_list(self, client: PowerBIClient):
        respx.get(f"{BASE}/apps").mock(
            return_value=Response(200, json={"value": []})
        )
        assert await client.list_apps() == []

    @respx.mock
    async def test_api_error_raises_powerbi_error(self, client: PowerBIClient):
        respx.get(f"{BASE}/apps").mock(
            return_value=Response(401, json={"error": {"message": "Unauthorized"}})
        )
        with pytest.raises(PowerBIError) as exc_info:
            await client.list_apps()
        assert exc_info.value.status_code == 401


class TestListWorkspaces:
    @respx.mock
    async def test_returns_typed_models(self, client: PowerBIClient):
        respx.get(f"{BASE}/groups").mock(
            return_value=Response(200, json={"value": [make_workspace_payload()]})
        )
        result = await client.list_workspaces()
        assert len(result) == 1
        assert isinstance(result[0], Workspace)
        assert result[0].id == WORKSPACE_ID

    @respx.mock
    async def test_correct_url(self, client: PowerBIClient):
        route = respx.get(f"{BASE}/groups").mock(
            return_value=Response(200, json={"value": []})
        )
        await client.list_workspaces()
        assert route.called

    @respx.mock
    async def test_empty_value_returns_empty_list(self, client: PowerBIClient):
        respx.get(f"{BASE}/groups").mock(
            return_value=Response(200, json={"value": []})
        )
        assert await client.list_workspaces() == []

    @respx.mock
    async def test_api_error_raises_powerbi_error(self, client: PowerBIClient):
        respx.get(f"{BASE}/groups").mock(
            return_value=Response(401, json={"error": {"message": "Unauthorized"}})
        )
        with pytest.raises(PowerBIError) as exc_info:
            await client.list_workspaces()
        assert exc_info.value.status_code == 401


class TestListDatasets:
    @respx.mock
    async def test_returns_typed_models(self, client: PowerBIClient):
        respx.get(f"{BASE}/reports").mock(
            return_value=Response(200, json={"value": [make_user_report_payload()]})
        )
        respx.get(f"{BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}").mock(
            return_value=Response(200, json=make_dataset_payload())
        )
        result = await client.list_datasets(APP_ID, WORKSPACE_ID)
        assert len(result) == 1
        ds, ws_id = result[0]
        assert isinstance(ds, Dataset)
        assert ds.id == DATASET_ID
        assert ws_id == WORKSPACE_ID

    @respx.mock
    async def test_uses_org_level_reports_url(self, client: PowerBIClient):
        route = respx.get(f"{BASE}/reports").mock(
            return_value=Response(200, json={"value": []})
        )
        await client.list_datasets(APP_ID, WORKSPACE_ID)
        assert route.called

    @respx.mock
    async def test_deduplicates_datasets(self, client: PowerBIClient):
        """Two reports pointing to the same dataset → one dataset returned."""
        report_a = make_user_report_payload(id="rep-a-id")
        report_b = make_user_report_payload(id="rep-b-id")
        respx.get(f"{BASE}/reports").mock(
            return_value=Response(200, json={"value": [report_a, report_b]})
        )
        respx.get(f"{BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}").mock(
            return_value=Response(200, json=make_dataset_payload())
        )
        result = await client.list_datasets(APP_ID, WORKSPACE_ID)
        assert len(result) == 1

    @respx.mock
    async def test_skips_reports_with_wrong_workspace(self, client: PowerBIClient):
        """Reports with a different datasetWorkspaceId are filtered out."""
        wrong_ws_report = make_user_report_payload(
            id="rep-wrong-ws",
            dataset_workspace_id="ffffffff-0000-0000-0000-000000000099",
        )
        right_ws_report = make_user_report_payload(id="rep-right-ws")
        respx.get(f"{BASE}/reports").mock(
            return_value=Response(200, json={"value": [wrong_ws_report, right_ws_report]})
        )
        respx.get(f"{BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}").mock(
            return_value=Response(200, json=make_dataset_payload())
        )
        result = await client.list_datasets(APP_ID, WORKSPACE_ID)
        assert len(result) == 1
        ds, ws_id = result[0]
        assert ws_id == WORKSPACE_ID

    @respx.mock
    async def test_skips_reports_linked_to_another_app_in_the_same_workspace(
        self, client: PowerBIClient
    ):
        report = {
            **make_user_report_payload(),
            "appId": "ffffffff-0000-0000-0000-000000000099",
        }
        respx.get(f"{BASE}/reports").mock(
            return_value=Response(200, json={"value": [report]})
        )
        assert await client.list_datasets(APP_ID, WORKSPACE_ID) == []

    @respx.mock
    async def test_skips_reports_with_missing_dataset_fields(self, client: PowerBIClient):
        """Reports with empty datasetId or missing datasetWorkspaceId are skipped."""
        valid = make_user_report_payload()
        no_dataset_id = make_user_report_payload(id="r2", dataset_id="")
        no_workspace_id = make_user_report_payload(id="r3", dataset_workspace_id=None)
        respx.get(f"{BASE}/reports").mock(
            return_value=Response(200, json={"value": [valid, no_dataset_id, no_workspace_id]})
        )
        respx.get(f"{BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}").mock(
            return_value=Response(200, json=make_dataset_payload())
        )
        result = await client.list_datasets(APP_ID, WORKSPACE_ID)
        assert len(result) == 1

    @respx.mock
    async def test_synthesizes_dataset_on_api_error(self, client: PowerBIClient):
        """When get_dataset returns 401/404, a Dataset is synthesised from report names."""
        report = make_user_report_payload(name="Sales - Report Template")
        respx.get(f"{BASE}/reports").mock(
            return_value=Response(200, json={"value": [report]})
        )
        respx.get(f"{BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}").mock(
            return_value=Response(401, json={"error": {"message": "Unauthorized"}})
        )
        result = await client.list_datasets(APP_ID, WORKSPACE_ID)
        assert len(result) == 1
        ds, ws_id = result[0]
        assert isinstance(ds, Dataset)
        assert ds.id == DATASET_ID
        assert ds.name == "Sales"
        assert ws_id == WORKSPACE_ID

    @respx.mock
    async def test_surfaces_metadata_rate_limit(self, client: PowerBIClient):
        respx.get(f"{BASE}/reports").mock(
            return_value=Response(200, json={"value": [make_user_report_payload()]})
        )
        respx.get(f"{BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}").mock(
            return_value=Response(429, json={"error": {"message": "Rate limited"}})
        )
        with pytest.raises(PowerBIError, match="Rate limited") as error:
            await client.list_datasets(APP_ID, WORKSPACE_ID)
        assert error.value.status_code == 429


class TestDatasetNameFromReports:
    def test_strips_report_template_suffix(self):
        assert _dataset_name_from_reports(["Sales - Report Template"]) == "Sales"

    def test_strips_presentation_template_suffix(self):
        assert _dataset_name_from_reports(["Sales - Presentation Template"]) == "Sales"

    def test_prefers_report_template_over_presentation(self):
        names = ["Sales - Presentation Template", "Sales - Report Template"]
        assert _dataset_name_from_reports(names) == "Sales"

    def test_fallback_to_shortest_name(self):
        names = ["A longer report name", "Short"]
        assert _dataset_name_from_reports(names) == "Short"

    def test_single_name_no_suffix(self):
        assert _dataset_name_from_reports(["My Dataset"]) == "My Dataset"


class TestGetDataset:
    @respx.mock
    async def test_returns_single_dataset(self, client: PowerBIClient):
        respx.get(f"{BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}").mock(
            return_value=Response(200, json=make_dataset_payload())
        )
        result = await client.get_dataset(WORKSPACE_ID, DATASET_ID)
        assert isinstance(result, Dataset)
        assert result.name == "Test Dataset"

    @respx.mock
    async def test_api_error_raises(self, client: PowerBIClient):
        respx.get(f"{BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}").mock(
            return_value=Response(404, json={"error": {"message": "Not found"}})
        )
        with pytest.raises(PowerBIError) as exc_info:
            await client.get_dataset(WORKSPACE_ID, DATASET_ID)
        assert exc_info.value.status_code == 404


class TestGetDatasetRefreshHistory:
    @respx.mock
    async def test_returns_typed_entries(self, client: PowerBIClient):
        respx.get(
            f"{BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}/refreshes",
            params={"$top": "5"},
        ).mock(
            return_value=Response(200, json={"value": [make_refresh_entry_payload()]})
        )
        result = await client.get_dataset_refresh_history(WORKSPACE_ID, DATASET_ID, top=5)
        assert len(result) == 1
        assert isinstance(result[0], RefreshEntry)
        assert result[0].status == "Completed"

    @respx.mock
    async def test_includes_top_query_param(self, client: PowerBIClient):
        route = respx.get(
            f"{BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}/refreshes",
        ).mock(return_value=Response(200, json={"value": []}))
        await client.get_dataset_refresh_history(WORKSPACE_ID, DATASET_ID, top=3)
        assert route.called
        assert "3" in str(route.calls.last.request.url)


class TestExecuteDax:
    @respx.mock
    async def test_rejects_invalid_dataset_id_before_making_a_request(
        self, client: PowerBIClient
    ):
        with pytest.raises(PowerBIError, match="dataset_id must be a GUID"):
            await client.execute_dax(WORKSPACE_ID, "invalid", 'EVALUATE ROW("x", 1)')
        assert not respx.calls

    @respx.mock
    async def test_posts_to_org_level_url(self, client: PowerBIClient):
        """execute_dax uses the org-level endpoint so app-granted access works
        (in-group requires workspace membership, which app users don't have)."""
        route = respx.post(
            f"{BASE}/datasets/{DATASET_ID}/executeQueries"
        ).mock(return_value=Response(200, json=make_dax_response([])))
        await client.execute_dax(WORKSPACE_ID, DATASET_ID, "EVALUATE ROW(\"x\", 1)")
        assert route.called

    @respx.mock
    async def test_payload_contains_queries_key(self, client: PowerBIClient):
        import json

        route = respx.post(
            f"{BASE}/datasets/{DATASET_ID}/executeQueries"
        ).mock(return_value=Response(200, json=make_dax_response([])))
        dax = "EVALUATE ROW(\"x\", 1)"
        await client.execute_dax(WORKSPACE_ID, DATASET_ID, dax)
        body = json.loads(route.calls.last.request.content)
        assert "queries" in body
        assert body["queries"][0]["query"] == dax

    @respx.mock
    async def test_api_error_raises(self, client: PowerBIClient):
        respx.post(
            f"{BASE}/datasets/{DATASET_ID}/executeQueries"
        ).mock(return_value=Response(400, json={"error": {"message": "Invalid DAX"}}))
        with pytest.raises(PowerBIError) as exc_info:
            await client.execute_dax(WORKSPACE_ID, DATASET_ID, "INVALID")
        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize("level", ["response", "result", "table"])
    @respx.mock
    async def test_partial_dax_results_report_api_error(
        self, client: PowerBIClient, level: str
    ):
        payload = make_dax_response([{"[x]": 1}])
        result = payload["results"][0]
        envelopes = {"response": payload, "result": result, "table": result["tables"][0]}
        envelopes[level]["error"] = {"code": "DAXQueryError", "message": "Too many rows"}
        respx.post(f"{BASE}/datasets/{DATASET_ID}/executeQueries").mock(
            return_value=Response(200, json=payload)
        )
        with pytest.raises(PowerBIError, match="Too many rows"):
            await client.execute_dax(WORKSPACE_ID, DATASET_ID, 'EVALUATE ROW("x", 1)')


class TestListTables:
    @respx.mock
    async def test_returns_typed_table_models(self, client: PowerBIClient):
        row = make_table_dax_row("Sales")
        bracketed = {f"[{k}]": v for k, v in row.items()}
        respx.post(
            f"{BASE}/datasets/{DATASET_ID}/executeQueries"
        ).mock(return_value=Response(200, json=make_dax_response([bracketed])))
        result = await client.list_tables(WORKSPACE_ID, DATASET_ID)
        assert len(result) == 1
        assert isinstance(result[0], Table)
        assert result[0].name == "Sales"

    @respx.mock
    async def test_dax_query_references_info_view_tables(self, client: PowerBIClient):
        import json

        route = respx.post(
            f"{BASE}/datasets/{DATASET_ID}/executeQueries"
        ).mock(return_value=Response(200, json=make_dax_response([])))
        await client.list_tables(WORKSPACE_ID, DATASET_ID)
        body = json.loads(route.calls.last.request.content)
        assert "INFO.VIEW.TABLES()" in body["queries"][0]["query"]


class TestListMeasures:
    @respx.mock
    async def test_returns_all_measures(self, client: PowerBIClient):
        row = make_measure_dax_row()
        bracketed = {f"[{k}]": v for k, v in row.items()}
        respx.post(
            f"{BASE}/datasets/{DATASET_ID}/executeQueries"
        ).mock(return_value=Response(200, json=make_dax_response([bracketed])))
        result = await client.list_measures(WORKSPACE_ID, DATASET_ID)
        assert len(result) == 1
        assert isinstance(result[0], Measure)
        assert result[0].name == "Total Sales"

    @respx.mock
    async def test_dax_query_uses_info_view_measures(self, client: PowerBIClient):
        import json

        route = respx.post(
            f"{BASE}/datasets/{DATASET_ID}/executeQueries"
        ).mock(return_value=Response(200, json=make_dax_response([])))
        await client.list_measures(WORKSPACE_ID, DATASET_ID)
        body = json.loads(route.calls.last.request.content)
        query = body["queries"][0]["query"]
        assert "INFO.VIEW.MEASURES()" in query
        assert "[Table]" in query

    @respx.mock
    async def test_filter_by_table_name_in_dax(self, client: PowerBIClient):
        import json

        route = respx.post(
            f"{BASE}/datasets/{DATASET_ID}/executeQueries"
        ).mock(return_value=Response(200, json=make_dax_response([])))
        await client.list_measures(WORKSPACE_ID, DATASET_ID, table_name="Sales")
        body = json.loads(route.calls.last.request.content)
        assert '"Sales"' in body["queries"][0]["query"]

    @pytest.mark.parametrize("method_name", ["list_measures", "list_columns"])
    @respx.mock
    async def test_doubles_quotes_in_table_name(self, client: PowerBIClient, method_name: str):
        import json

        route = respx.post(f"{BASE}/datasets/{DATASET_ID}/executeQueries").mock(
            return_value=Response(200, json=make_dax_response([]))
        )
        await getattr(client, method_name)(
            WORKSPACE_ID, DATASET_ID, table_name='Sales "Domestic"'
        )
        query = json.loads(route.calls.last.request.content)["queries"][0]["query"]
        assert '[Table] = "Sales ""Domestic"""' in query


class TestListColumns:
    @respx.mock
    async def test_returns_typed_column_models(self, client: PowerBIClient):
        row = make_column_dax_row()
        bracketed = {f"[{k}]": v for k, v in row.items()}
        respx.post(
            f"{BASE}/datasets/{DATASET_ID}/executeQueries"
        ).mock(return_value=Response(200, json=make_dax_response([bracketed])))
        result = await client.list_columns(WORKSPACE_ID, DATASET_ID)
        assert len(result) == 1
        assert isinstance(result[0], Column)
        assert result[0].name == "ProductName"

    @respx.mock
    async def test_dax_query_uses_info_view_columns(self, client: PowerBIClient):
        import json

        route = respx.post(
            f"{BASE}/datasets/{DATASET_ID}/executeQueries"
        ).mock(return_value=Response(200, json=make_dax_response([])))
        await client.list_columns(WORKSPACE_ID, DATASET_ID)
        body = json.loads(route.calls.last.request.content)
        query = body["queries"][0]["query"]
        assert "INFO.VIEW.COLUMNS()" in query
        assert '[Type] = "Data"' in query
        assert "[Table]" in query

    @respx.mock
    async def test_filter_by_table_name_in_dax(self, client: PowerBIClient):
        import json

        route = respx.post(
            f"{BASE}/datasets/{DATASET_ID}/executeQueries"
        ).mock(return_value=Response(200, json=make_dax_response([])))
        await client.list_columns(WORKSPACE_ID, DATASET_ID, table_name="Products")
        body = json.loads(route.calls.last.request.content)
        assert '"Products"' in body["queries"][0]["query"]


class TestRaiseForStatus:
    @respx.mock
    async def test_401_raises_powerbi_error(self, client: PowerBIClient):
        respx.get(f"{BASE}/groups").mock(
            return_value=Response(401, json={"error": {"message": "Unauthorized"}})
        )
        with pytest.raises(PowerBIError) as exc_info:
            await client.list_workspaces()
        assert exc_info.value.status_code == 401
        assert "401" in str(exc_info.value)

    @respx.mock
    async def test_500_raises_powerbi_error(self, client: PowerBIClient):
        respx.get(f"{BASE}/groups").mock(
            return_value=Response(500, text="Internal Server Error")
        )
        with pytest.raises(PowerBIError) as exc_info:
            await client.list_workspaces()
        assert exc_info.value.status_code == 500

    @respx.mock
    async def test_200_does_not_raise(self, client: PowerBIClient):
        respx.get(f"{BASE}/groups").mock(
            return_value=Response(200, json={"value": []})
        )
        result = await client.list_workspaces()
        assert result == []
