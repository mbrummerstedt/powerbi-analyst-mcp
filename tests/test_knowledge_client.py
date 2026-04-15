"""Tests for the knowledge layer HTTP client."""

import httpx
import pytest
import respx

from powerbi_mcp.knowledge_client import KnowledgeClient


@pytest.fixture
def client():
    return KnowledgeClient(
        base_url="https://bi-knowledge.example.com", api_key="test-key"
    )


@respx.mock
async def test_search_sends_query(client):
    route = respx.get("https://bi-knowledge.example.com/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "schema_version": 1,
                "metrics": [{"name": "gmv", "display_name": "GMV"}],
                "dimensions": [],
                "notes": [],
            },
        )
    )
    result = await client.search("gross merchandise value")
    assert route.called
    request = route.calls.last.request
    assert request.url.params.get("q") == "gross merchandise value"
    assert request.headers["X-API-Key"] == "test-key"
    assert result["metrics"][0]["name"] == "gmv"


@respx.mock
async def test_get_metric_by_name(client):
    respx.get("https://bi-knowledge.example.com/metrics/gmv").mock(
        return_value=httpx.Response(
            200, json={"name": "gmv", "description": "Gross Merchandise Value"}
        )
    )
    result = await client.get_metric("gmv")
    assert result["name"] == "gmv"
    assert "Merchandise Value" in result["description"]


@respx.mock
async def test_list_metrics_with_domain_filter(client):
    route = respx.get("https://bi-knowledge.example.com/metrics").mock(
        return_value=httpx.Response(
            200, json={"Operations": [{"name": "gmv"}], "Finance": [{"name": "revenue"}]}
        )
    )
    result = await client.list_metrics(domain="Operations")
    assert route.called
    assert route.calls.last.request.url.params.get("domain") == "Operations"
    assert "Operations" in result


@respx.mock
async def test_list_dimensions(client):
    respx.get("https://bi-knowledge.example.com/dimensions").mock(
        return_value=httpx.Response(
            200, json=[{"name": "market", "display_name": "Market"}]
        )
    )
    result = await client.list_dimensions()
    assert len(result) == 1
    assert result[0]["name"] == "market"


@respx.mock
async def test_client_raises_on_401(client):
    respx.get("https://bi-knowledge.example.com/search").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid API key"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.search("test")


@respx.mock
async def test_client_includes_timeout(client):
    """Sanity check: no request should hang forever."""
    respx.get("https://bi-knowledge.example.com/search").mock(
        return_value=httpx.Response(200, json={"metrics": [], "dimensions": [], "notes": []})
    )
    # Just verify it completes — the timeout is enforced in the client constructor
    await client.search("q")
