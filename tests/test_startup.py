import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_packaged_server_advertises_the_bundle_tools(tmp_path):
    manifest = Path(__file__).resolve().parents[1] / "bundle" / "manifest.template.json"
    expected = {tool["name"] for tool in json.loads(manifest.read_text(encoding="utf-8"))["tools"]}
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "powerbi_mcp"],
        cwd=tmp_path,
        env={"POWERBI_CLIENT_ID": "startup-test"},
    )
    async with stdio_client(server) as streams, ClientSession(*streams) as session:
        await session.initialize()
        tools = {tool.name: tool for tool in (await session.list_tools()).tools}

    assert tools.keys() == expected
    schema = tools["list_datasets"].inputSchema
    assert schema["required"] == ["app_id"]
    assert schema["properties"]["app_id"]["type"] == "string"
