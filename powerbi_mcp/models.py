"""
Pydantic models for Power BI API responses.

These models provide type safety and validation for data returned
from the Power BI REST API.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class App(BaseModel):
    """A Power BI installed app."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: Optional[str] = None
    published_by: Optional[str] = Field(None, alias="publishedBy")
    last_update: Optional[datetime] = Field(None, alias="lastUpdate")
    workspace_id: Optional[str] = Field(None, alias="workspaceId")


class AppReport(BaseModel):
    """
    A report returned from the app-context endpoint (/apps/{appId}/reports).

    Note: ``dataset_id`` is deliberately empty string in app context — the API
    detaches reports from their datasets.  Use ``original_report_object_id`` to
    resolve the report in workspace context where the real ``datasetId`` lives.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    dataset_id: Optional[str] = Field(None, alias="datasetId")
    original_report_object_id: Optional[str] = Field(
        None, alias="originalReportObjectId"
    )
    workspace_id: Optional[str] = Field(None, alias="workspaceId")
    web_url: Optional[str] = Field(None, alias="webUrl")


class UserReport(BaseModel):
    """A report returned from the org-level /myorg/reports endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    app_id: Optional[str] = Field(None, alias="appId")
    dataset_id: Optional[str] = Field(None, alias="datasetId")
    dataset_workspace_id: Optional[str] = Field(None, alias="datasetWorkspaceId")
    web_url: Optional[str] = Field(None, alias="webUrl")


class Workspace(BaseModel):
    """A Power BI workspace (group)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    type: Optional[str] = None
    state: Optional[str] = None
    is_on_dedicated_capacity: Optional[bool] = Field(
        None, alias="isOnDedicatedCapacity"
    )


class Dataset(BaseModel):
    """A Power BI dataset (semantic model)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    configured_by: Optional[str] = Field(None, alias="configuredBy")
    target_storage_mode: Optional[str] = Field(None, alias="targetStorageMode")
    is_refreshable: Optional[bool] = Field(None, alias="isRefreshable")
    created_date: Optional[datetime] = Field(None, alias="createdDate")
    web_url: Optional[str] = Field(None, alias="webUrl")
    description: Optional[str] = None
    is_effective_identity_required: Optional[bool] = Field(
        None, alias="isEffectiveIdentityRequired"
    )
    is_on_prem_gateway_required: Optional[bool] = Field(
        None, alias="isOnPremGatewayRequired"
    )


class RefreshEntry(BaseModel):
    """A dataset refresh history entry."""

    model_config = ConfigDict(populate_by_name=True)

    request_id: Optional[str] = Field(None, alias="requestId")
    status: Optional[str] = None
    start_time: Optional[datetime] = Field(None, alias="startTime")
    end_time: Optional[datetime] = Field(None, alias="endTime")
    refresh_type: Optional[str] = Field(None, alias="refreshType")


class Table(BaseModel):
    """A table in a Power BI dataset."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(alias="Name")
    description: Optional[str] = Field(None, alias="Description")
    is_hidden: Optional[bool] = Field(None, alias="IsHidden")


class Measure(BaseModel):
    """A measure in a Power BI dataset."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(alias="Name")
    table_name: str = Field(alias="TableName")
    description: Optional[str] = Field(None, alias="Description")
    format_string: Optional[str] = Field(None, alias="FormatString")


class Column(BaseModel):
    """A column in a Power BI dataset."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(alias="Name")
    table_name: str = Field(alias="TableName")
    description: Optional[str] = Field(None, alias="Description")
    data_type: Optional[str] = Field(None, alias="DataType")
    is_key: Optional[bool] = Field(None, alias="IsKey")
