"""HTTP client for the Miinto BI Knowledge Layer.

Thin wrapper over httpx that handles auth header injection, base URL
composition, and error propagation. No retries on the first pass —
failures bubble up so Claude's tool-result feedback can guide recovery.
"""

from __future__ import annotations

from typing import Any

import httpx


class KnowledgeClient:
    """Async client for the Railway-hosted knowledge layer API.

    Instances are cheap; create one per tool call or reuse across calls.
    The underlying httpx.AsyncClient is recreated per request so there's
    no event-loop affinity.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key, "Accept": "application/json"}

    async def _get(self, path: str, params: dict | None = None) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}{path}",
                params=params or {},
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    # --- Search ---

    async def search(
        self, query: str, limit: int = 10
    ) -> dict:
        """Cross-entity semantic search."""
        return await self._get("/search", {"q": query, "limit": limit})

    # --- Metrics ---

    async def get_metric(self, name: str) -> dict:
        """Deep-dive on one metric by name. Includes variants + opinions."""
        return await self._get(f"/metrics/{name}")

    async def list_metrics(self, domain: str | None = None) -> dict:
        """List metrics grouped by domain, with variant summaries."""
        params = {"domain": domain} if domain else None
        return await self._get("/metrics", params)

    # --- Dimensions ---

    async def list_dimensions(self) -> list[dict]:
        """List all dimensions with dataset mappings."""
        return await self._get("/dimensions")
