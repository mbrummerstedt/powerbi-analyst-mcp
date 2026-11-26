"""
OAuth authentication for Power BI using MSAL device code flow.

The user authenticates interactively via their browser; their delegated
permissions determine what data is accessible through the Power BI REST API.

Tokens are persisted in the OS secure store so subsequent calls skip the
browser step:

  - macOS   → Keychain
  - Windows → DPAPI-encrypted file
  - Linux   → LibSecret (gnome-keyring / KWallet)

If secure storage is unavailable, tokens last only for the server process.
"""

from __future__ import annotations

import logging
from functools import cached_property
from pathlib import Path

import msal
from msal_extensions import (
    CrossPlatLock,
    PersistedTokenCache,
    build_encrypted_persistence,
)

AUTHORITY_BASE = "https://login.microsoftonline.com"

# Delegated scopes required for the tools in this server:
#   Dataset.Read.All   - execute DAX queries, read dataset metadata
#   Report.Read.All    - GET /apps/{appId}/reports (dataset discovery path)
#   Workspace.Read.All - resolve workspace-context reports for real datasetId
#   App.Read.All       - list installed apps
SCOPES = [
    "https://analysis.windows.net/powerbi/api/Dataset.Read.All",
    "https://analysis.windows.net/powerbi/api/Report.Read.All",
    "https://analysis.windows.net/powerbi/api/Workspace.Read.All",
    "https://analysis.windows.net/powerbi/api/App.Read.All",
]

TOKEN_CACHE_PATH = Path.home() / ".powerbi_mcp_token_cache.bin"
logger = logging.getLogger(__name__)


class PowerBIAuth:
    """Handles OAuth token acquisition and caching for Power BI API access."""

    def __init__(self, client_id: str, tenant_id: str = "organizations"):
        self._client_id = client_id
        self._authority = f"{AUTHORITY_BASE}/{tenant_id}"
        try:
            self._persistence = build_encrypted_persistence(str(TOKEN_CACHE_PATH))
        except (ImportError, OSError, RuntimeError, ValueError):
            logger.warning("OS secure storage is unavailable. Power BI sign-in lasts for this session only.")
            self._persistence = None

        if self._persistence is None:
            self.cache = msal.SerializableTokenCache()
        else:
            self._cache_lock = self._persistence.get_location() + ".lockfile"
            self.cache = PersistedTokenCache(self._persistence, lock_location=self._cache_lock)

    @cached_property
    def app(self) -> msal.PublicClientApplication:
        # MSAL contacts Entra ID during construction. Logout works offline.
        return msal.PublicClientApplication(
            self._client_id,
            authority=self._authority,
            token_cache=self.cache,
            timeout=15,
        )

    @property
    def can_persist_tokens(self) -> bool:
        return self._persistence is not None

    def get_token_silent(self) -> str | None:
        """
        Return a valid access token from the secure cache.

        Returns None when sign-in is required.
        """
        accounts = self.app.get_accounts()
        if not accounts:
            return None

        result = self.app.acquire_token_silent(SCOPES, account=accounts[0])
        return result.get("access_token") if result else None

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
                f"Failed to initiate device flow: {flow.get('error', 'unknown error')}"
            )
        return flow

    def poll_device_flow(self, flow: dict) -> dict:
        return self.app.acquire_token_by_device_flow(flow, exit_condition=lambda _: True)

    def complete_device_flow(self, flow: dict) -> str:
        """
        Block until the user completes browser authentication, then return the token.
        Raises RuntimeError on failure.
        """
        result = self.app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(
                f"Authentication failed: {result.get('error', 'unknown error')}"
            )
        return result["access_token"]

    def clear_cache(self) -> None:
        """Remove cached tokens (forces re-authentication on next call)."""
        if self._persistence is not None:
            # Keychain and LibSecret use the file only to signal cache updates.
            with CrossPlatLock(self._cache_lock):
                self._persistence.save("{}")
        self.cache.deserialize(None)
