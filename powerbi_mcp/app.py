"""
Power BI MCP Server — application factory and entry point.

Loads settings, creates the FastMCP instance, and registers all tools.
"""

from __future__ import annotations

import sys
import textwrap

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from .config import Settings
from .knowledge import register_knowledge_tools
from .tools import register_tools

try:
    settings = Settings()
except ValidationError:
    print(
        "Configuration error: POWERBI_CLIENT_ID is not set.\n"
        "Set the environment variable or create a .env file before starting the server.",
        file=sys.stderr,
    )
    sys.exit(1)

mcp = FastMCP(
    "Power BI",
    instructions=textwrap.dedent(
        """
        This server gives you read-only access to Power BI semantic models
        (datasets) via the Power BI REST API.

        Typical workflow:
        1. Call `authenticate` if this is the first run or the token has expired.
        2. Call `list_apps` to find installed apps and get their workspaceId.
        3. Call `list_datasets` with the workspaceId from the app response.
        4. Call `list_tables`, `list_measures`, or `list_columns` to explore
           the data model structure.
        5. Call `execute_dax` to retrieve data using a DAX query.

        All dataset operations require BOTH a workspace_id AND a dataset_id.
        The workspace_id must come from `list_apps` (the workspaceId field) —
        never from workspace enumeration. Permissions are granted through apps.
        """
    ),
)

register_tools(mcp, settings.client_id, settings.tenant_id, settings.output_dir)
register_knowledge_tools(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
