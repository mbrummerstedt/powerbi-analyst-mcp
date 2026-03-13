"""
Configuration management using pydantic-settings.

Loads environment variables from .env file with POWERBI_ prefix.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_OUTPUT_DIR = str(Path.home() / "powerbi_output")


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Required environment variables:
        POWERBI_CLIENT_ID: Azure AD application (client) ID

    Optional environment variables:
        POWERBI_TENANT_ID: Azure AD tenant ID or "organizations" (default).
            Use "organizations" to allow any work/school account.
            Use your specific tenant ID (GUID or domain) if the app is
            registered as single-tenant.
        POWERBI_OUTPUT_DIR: Directory where large DAX query results are saved
            as CSV files (default: ~/powerbi_output). Uses an absolute path
            so the server works regardless of its working directory.
    """

    client_id: str
    tenant_id: str = "organizations"
    output_dir: str = _DEFAULT_OUTPUT_DIR

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="POWERBI_",
        case_sensitive=False,
    )
