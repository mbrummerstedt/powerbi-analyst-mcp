"""
Pydantic models for Power BI API responses.

These models provide type safety and validation for data returned
from the Power BI REST API.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
