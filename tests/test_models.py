"""
Tests for Pydantic model validation in powerbi_mcp/models.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from powerbi_mcp.models import Column, Dataset, Measure, RefreshEntry, Table, Workspace
from tests.conftest import (
    make_column_dax_row,
    make_dataset_payload,
    make_measure_dax_row,
    make_refresh_entry_payload,
    make_table_dax_row,
    make_workspace_payload,
)


class TestWorkspace:
    def test_parses_full_payload(self):
        ws = Workspace.model_validate(make_workspace_payload())
        assert ws.id == "aaaaaaaa-0000-0000-0000-000000000001"
        assert ws.name == "Test Workspace"
        assert ws.type == "Workspace"
        assert ws.state == "Active"
        assert ws.is_on_dedicated_capacity is False

    def test_parses_camel_case_alias(self):
        ws = Workspace.model_validate({"id": "x", "name": "y", "isOnDedicatedCapacity": True})
        assert ws.is_on_dedicated_capacity is True

    def test_optional_fields_default_to_none(self):
        ws = Workspace.model_validate({"id": "x", "name": "y"})
        assert ws.type is None
        assert ws.state is None
        assert ws.is_on_dedicated_capacity is None

    def test_missing_required_id_raises(self):
        with pytest.raises(ValidationError):
            Workspace.model_validate({"name": "y"})

    def test_missing_required_name_raises(self):
        with pytest.raises(ValidationError):
            Workspace.model_validate({"id": "x"})


class TestDataset:
    def test_parses_full_payload(self):
        ds = Dataset.model_validate(make_dataset_payload())
        assert ds.id == "bbbbbbbb-0000-0000-0000-000000000002"
        assert ds.name == "Test Dataset"
        assert ds.configured_by == "user@example.com"
        assert ds.target_storage_mode == "Import"
        assert ds.is_refreshable is True
        assert ds.web_url == "https://app.powerbi.com/groups/me/datasets/bbbbbbbb"

    def test_parses_created_date_as_datetime(self):
        ds = Dataset.model_validate(make_dataset_payload())
        assert isinstance(ds.created_date, datetime)
        assert ds.created_date.year == 2024

    def test_parses_camel_case_aliases(self):
        ds = Dataset.model_validate({
            "id": "x",
            "name": "y",
            "configuredBy": "admin@test.com",
            "targetStorageMode": "DirectQuery",
            "isRefreshable": False,
            "isEffectiveIdentityRequired": True,
            "isOnPremGatewayRequired": True,
        })
        assert ds.configured_by == "admin@test.com"
        assert ds.target_storage_mode == "DirectQuery"
        assert ds.is_refreshable is False
        assert ds.is_effective_identity_required is True
        assert ds.is_on_prem_gateway_required is True

    def test_optional_fields_default_to_none(self):
        ds = Dataset.model_validate({"id": "x", "name": "y"})
        assert ds.configured_by is None
        assert ds.created_date is None
        assert ds.web_url is None

    def test_missing_required_id_raises(self):
        with pytest.raises(ValidationError):
            Dataset.model_validate({"name": "y"})


class TestRefreshEntry:
    def test_parses_full_payload(self):
        entry = RefreshEntry.model_validate(make_refresh_entry_payload())
        assert entry.request_id == "cccccccc-0000-0000-0000-000000000003"
        assert entry.status == "Completed"
        assert entry.refresh_type == "Scheduled"

    def test_parses_start_end_times_as_datetime(self):
        entry = RefreshEntry.model_validate(make_refresh_entry_payload())
        assert isinstance(entry.start_time, datetime)
        assert isinstance(entry.end_time, datetime)
        assert entry.start_time < entry.end_time

    def test_all_fields_optional(self):
        entry = RefreshEntry.model_validate({})
        assert entry.request_id is None
        assert entry.status is None
        assert entry.start_time is None
        assert entry.end_time is None
        assert entry.refresh_type is None


class TestTable:
    def test_parses_title_case_aliases(self):
        table = Table.model_validate(make_table_dax_row())
        assert table.name == "Sales"
        assert table.description == ""
        assert table.is_hidden is False

    def test_optional_description_can_be_none(self):
        table = Table.model_validate({"Name": "Dates", "Description": None, "IsHidden": False})
        assert table.description is None

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            Table.model_validate({"Description": "x", "IsHidden": False})


class TestMeasure:
    def test_parses_all_fields(self):
        m = Measure.model_validate(make_measure_dax_row())
        assert m.name == "Total Sales"
        assert m.table_name == "Sales"
        assert m.format_string == "#,##0"
        assert m.expression == "SUM(Sales[Amount])"

    def test_optional_fields_default_to_none(self):
        m = Measure.model_validate({"Name": "M", "TableName": "T"})
        assert m.description is None
        assert m.format_string is None
        assert m.expression is None

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            Measure.model_validate({"TableName": "T"})

    def test_missing_table_name_raises(self):
        with pytest.raises(ValidationError):
            Measure.model_validate({"Name": "M"})


class TestColumn:
    def test_parses_all_fields(self):
        col = Column.model_validate(make_column_dax_row())
        assert col.name == "ProductName"
        assert col.table_name == "Products"
        assert col.data_type == "String"
        assert col.is_key is False

    def test_is_key_true(self):
        col = Column.model_validate(make_column_dax_row(is_key=True))
        assert col.is_key is True

    def test_optional_fields_default_to_none(self):
        col = Column.model_validate({"Name": "C", "TableName": "T"})
        assert col.description is None
        assert col.data_type is None
        assert col.is_key is None

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            Column.model_validate({"TableName": "T"})
