from unittest.mock import Mock

import msal
from msal_extensions.persistence import BasePersistence

from powerbi_mcp.auth import PowerBIAuth


def test_unavailable_secure_store_keeps_tokens_in_memory(monkeypatch, tmp_path):
    path = tmp_path / "token-cache"
    monkeypatch.setattr("powerbi_mcp.auth.TOKEN_CACHE_PATH", path)
    monkeypatch.setattr("msal.PublicClientApplication", Mock())
    monkeypatch.setattr(
        "powerbi_mcp.auth.build_encrypted_persistence",
        Mock(side_effect=ImportError("No LibSecret")),
    )

    auth = PowerBIAuth("client")
    refresh_token = {
        "credential_type": msal.TokenCache.CredentialType.REFRESH_TOKEN,
        "home_account_id": "account",
        "environment": "login.microsoftonline.com",
        "client_id": "client",
    }
    auth.cache.update_rt(refresh_token, "test-refresh-token")

    assert not path.exists()
    assert "test-refresh-token" in auth.cache.serialize()
    assert not auth.can_persist_tokens


def test_logout_empties_the_secure_store_and_memory_cache(monkeypatch, tmp_path):
    marker = tmp_path / "token-cache"
    marker.touch()
    persistence = Mock(spec=BasePersistence, get_location=Mock(return_value=str(marker)))
    monkeypatch.setattr("powerbi_mcp.auth.TOKEN_CACHE_PATH", marker)
    app_factory = Mock(side_effect=OSError("Entra ID is unreachable"))
    monkeypatch.setattr("msal.PublicClientApplication", app_factory)
    monkeypatch.setattr("powerbi_mcp.auth.build_encrypted_persistence", Mock(return_value=persistence))

    auth = PowerBIAuth("client")
    auth.cache.deserialize('{"RefreshToken": {"cached": {"secret": "test-value"}}}')

    auth.clear_cache()

    app_factory.assert_not_called()
    persistence.save.assert_called_once_with("{}")
    assert auth.cache.serialize() == "{}"
    assert marker.exists()
