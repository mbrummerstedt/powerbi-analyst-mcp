"""MCP tools that call the Miinto BI Knowledge Layer.

These tools ship alongside the existing Power BI tools (execute_dax,
list_datasets, etc.) in the same MCP server. The user experience: a
single install, a unified tool surface, the knowledge layer is
invisible plumbing.
"""

from __future__ import annotations

import os

from powerbi_mcp.knowledge_client import KnowledgeClient


def _get_client() -> KnowledgeClient:
    """Build a KnowledgeClient from env vars.

    Called on every tool invocation so changes to env vars (e.g. during
    local dev) take effect without restarting the MCP server.
    """
    base_url = os.environ.get("KNOWLEDGE_API_BASE", "")
    api_key = os.environ.get("KNOWLEDGE_API_KEY", "")
    if not base_url:
        raise RuntimeError(
            "KNOWLEDGE_API_BASE not set. Configure it in your Claude "
            "Desktop config alongside your Power BI settings."
        )
    if not api_key:
        raise RuntimeError(
            "KNOWLEDGE_API_KEY not set. Configure it in your Claude "
            "Desktop config alongside your Power BI settings."
        )
    return KnowledgeClient(base_url=base_url, api_key=api_key)


# --- Tool functions (registered in app.py via register_knowledge_tools) ---


async def search_knowledge(query: str, limit: int = 10) -> dict:
    """Semantic search across metrics, dimensions, tables, columns.

    Given a natural-language question like "what is our GMV per category
    in Norway", returns the minimal set of entities the client needs to
    construct a Power BI query: the metric to use, the right currency
    variant, the dimension columns to filter on, the right dataset, and
    any business opinions that apply.

    Use this BEFORE writing DAX for any ad-hoc question. It saves
    traversal time and prevents common dataset/metric mismatches.

    Args:
        query: natural-language question or search terms
        limit: max results per entity type (default 10)

    Returns: flat response with metrics, variants, dimensions, tables,
             columns, optional cross_dataset hint, and applicable notes
    """
    client = _get_client()
    return await client.search(query, limit=limit)


async def get_metric(name: str) -> dict:
    """Get the full definition of a parent metric by name.

    Returns the metric's description, when_to_use, formula, filter,
    all variants (currency/time-shifted versions), business caveats,
    thresholds, trust state, and applicable opinions.

    Use this when you need the FULL context on a metric — e.g. when
    composing an answer that requires knowing not just what GMV is but
    also when it excludes/includes, how to interpret it, how to compare
    across periods.

    Args:
        name: dbt-style snake_case metric name, e.g. "gmv",
              "gmv_after_rejections", "rejection_rate_items"

    Returns: metric detail dict
    """
    client = _get_client()
    return await client.get_metric(name)


async def list_metrics(domain: str | None = None) -> dict:
    """Browse the full metric catalog, optionally filtered by domain.

    Returns a grouped-by-domain dict of metric summaries. Use this when
    the user wants to explore what's available (e.g. "what metrics do
    we have for customer experience?") rather than answering a specific
    question.

    Args:
        domain: optional filter — "Operations" | "Products" | "Finance"
                | "Marketing" | "Customer Experience"

    Returns: {domain: [metric_summary, ...]}
    """
    client = _get_client()
    return await client.list_metrics(domain=domain)


async def list_dimensions() -> list[dict]:
    """List all curated dimensions with their dataset mappings.

    Returns each dimension with its typical values, description, and
    which PBI datasets/tables/columns it maps to. Use this when the
    user asks about a dimension concept (e.g. "what do we have for
    market?") rather than a metric.

    Returns: list of dimension dicts with dataset mappings
    """
    client = _get_client()
    return await client.list_dimensions()
