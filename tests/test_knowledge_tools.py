"""Tests for the knowledge-layer MCP tools.

Tools are pure async functions that take arguments and return
JSON-serializable dicts. They wrap KnowledgeClient with no additional
logic beyond routing.
"""

from unittest.mock import AsyncMock, patch

import pytest

from powerbi_mcp.knowledge import (
    get_metric,
    list_dimensions,
    list_metrics,
    search_knowledge,
)


@pytest.fixture
def client_mock():
    """A KnowledgeClient mock that returns canned responses."""
    m = AsyncMock()
    m.search.return_value = {
        "schema_version": 1,
        "metrics": [{"name": "gmv"}],
        "dimensions": [],
        "notes": [],
    }
    m.get_metric.return_value = {"name": "gmv", "description": "GMV"}
    m.list_metrics.return_value = {"Operations": [{"name": "gmv"}]}
    m.list_dimensions.return_value = [{"name": "market"}]
    return m


async def test_search_knowledge_returns_result(client_mock):
    with patch("powerbi_mcp.knowledge._get_client", return_value=client_mock):
        result = await search_knowledge(query="gmv trend")
    assert result["metrics"][0]["name"] == "gmv"
    client_mock.search.assert_called_once_with("gmv trend", limit=10)


async def test_get_metric_returns_detail(client_mock):
    with patch("powerbi_mcp.knowledge._get_client", return_value=client_mock):
        result = await get_metric(name="gmv")
    assert result["name"] == "gmv"
    client_mock.get_metric.assert_called_once_with("gmv")


async def test_list_metrics_with_domain(client_mock):
    with patch("powerbi_mcp.knowledge._get_client", return_value=client_mock):
        result = await list_metrics(domain="Operations")
    assert "Operations" in result
    client_mock.list_metrics.assert_called_once_with(domain="Operations")


async def test_list_dimensions_empty_filter(client_mock):
    with patch("powerbi_mcp.knowledge._get_client", return_value=client_mock):
        result = await list_dimensions()
    assert result[0]["name"] == "market"
    client_mock.list_dimensions.assert_called_once()
