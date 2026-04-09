"""
OAuth authentication for Power BI using MSAL device code flow.

The user authenticates interactively via their browser; their delegated
permissions determine what data is accessible through the Power BI REST API.

Tokens are persisted in the OS secure store so subsequent calls skip the
browser step:

  - macOS   → Keychain
  - Windows → DPAPI-encrypted file
  - Linux   → LibSecret (gnome-keyring / KWallet); falls back to an
               encrypted file if LibSecret is unavailable.
"""

from __future__ import annotations

from pathlib import Path

import msal
from msal_extensions import (
    FilePersistence,
    PersistedTokenCache,
    build_encrypted_persistence,
)

AUTHORITY_BASE = "https://login.microsoftonline.com"

# Delegated scopes required for the tools in this server:
#   Dataset.Read.All   - list datasets, execute queries, read metadata
#   Workspace.Read.All - list workspaces (groups)
#   App.Read.All       - list installed apps
SCOPES = [
    "https://analysis.windows.net/powerbi/api/Dataset.Read.All",
    "https://analysis.windows.net/powerbi/api/Workspace.Read.All",
    "https://analysis.windows.net/powerbi/api/App.Read.All",
]

TOKEN_CACHE_PATH = Path.home() / ".powerbi_mcp_token_cache.bin"


def _build_cache(path: Path) -> PersistedTokenCache:
    """
    Build a platform-appropriate encrypted token cache.

    Falls back to a plain FilePersistence if the OS secure store is
    unavailable (e.g. a headless Linux server without gnome-keyring).
    """
    try:
        persistence = build_encrypted_persistence(str(path))
    except Exception:
        persistence = FilePersistence(str(path))
    return PersistedTokenCache(persistence)


class PowerBIAuth:
    """Handles OAuth token acquisition and caching for Power BI API access."""

    def __init__(self, client_id: str, tenant_id: str = "organizations"):
        self.client_id = client_id
        self.tenant_id = tenant_id
        self.cache = _build_cache(TOKEN_CACHE_PATH)

        self.app = msal.PublicClientApplication(
            client_id,
            authority=f"{AUTHORITY_BASE}/{tenant_id}",
            token_cache=self.cache,
        )

    def get_token_silent(self) -> str | None:
        """
        Return a valid access token from the secure cache.

        Returns None if no account is cached (login required).
        Raises RuntimeError if a token exists but cannot be refreshed
        (e.g. network unavailable, token revoked).
        """
        accounts = self.app.get_accounts()
        if not accounts:
            return None

        result = self.app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]

        if result and "error" in result:
            raise RuntimeError(
                f"Token refresh failed ({result['error']}): "
                f"{result.get('error_description', 'unknown error')}"
            )

        return None

    def initiate_device_flow(self) -> dict:
        """
        Start a device code flow.

        Returns the flow dict from MSAL which includes:
          - ``message``   - human-readable instructions with the URL and code
          - ``user_code`` - the code the user enters at the URL
          - ``expires_at``
        """
        flow = self.app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(
                f"Failed to initiate device flow: {flow.get('error_description', flow)}"
            )
        self._pending_flow = flow
        return flow

    def complete_device_flow(self, flow: dict) -> str:
        """
        Block until the user completes browser authentication, then return the token.
        Raises RuntimeError on failure.
        """
        result = self.app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(
                f"Authentication failed: {result.get('error_description', result)}"
            )
        return result["access_token"]

    def clear_cache(self) -> None:
        """Remove cached tokens (forces re-authentication on next call)."""
        if TOKEN_CACHE_PATH.exists():
            TOKEN_CACHE_PATH.unlink()
        self.cache = _build_cache(TOKEN_CACHE_PATH)
        self.app = msal.PublicClientApplication(
            self.client_id,
            authority=f"{AUTHORITY_BASE}/{self.tenant_id}",
            token_cache=self.cache,
        )
