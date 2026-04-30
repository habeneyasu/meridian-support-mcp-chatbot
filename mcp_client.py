# mcp_client.py — MCP server connection, tool discovery, and tool execution
import sys
import asyncio
import json
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession
import config

# Module-level cache — populated once by connect()
_tools: list[dict] = []


def connect() -> list[dict]:
    """
    Connect to the MCP server, discover tools, and cache them.
    Returns a list of tool dicts: {name, description, inputSchema}.
    On failure prints to stderr and returns an empty list.
    """
    try:
        tools = asyncio.run(_connect_async())
        _tools.clear()
        _tools.extend(tools)
        return tools
    except Exception as e:
        print(f"[MCP ERROR] connect failed: {e}", file=sys.stderr)
        return []


async def _connect_async() -> list[dict]:
    async with streamablehttp_client(config.MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            tools = []
            for tool in result.tools:
                schema = {}
                if tool.inputSchema:
                    # inputSchema is already a dict from the SDK
                    schema = tool.inputSchema if isinstance(tool.inputSchema, dict) else tool.inputSchema.model_dump()
                tool_dict = {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": schema,
                }
                tools.append(tool_dict)
                print(f"[MCP] Discovered tool: {tool.name}")
            return tools


def call_tool(name: str, args: dict) -> tuple[bool, str]:
    """
    Call a tool on the MCP server.
    Returns (True, result_text) on success.
    Returns (False, user_friendly_error) on any failure.
    """
    try:
        result = asyncio.run(_call_tool_async(name, args))
        return (True, result)
    except Exception as e:
        print(f"[MCP ERROR] tool={name} error={e}", file=sys.stderr)
        return (False, "I couldn't complete that request. Please try again.")


async def _call_tool_async(name: str, args: dict) -> str:
    async with streamablehttp_client(config.MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            # Extract text content from the result
            if result.content:
                parts = []
                for item in result.content:
                    if hasattr(item, "text"):
                        parts.append(item.text)
                    elif hasattr(item, "model_dump"):
                        parts.append(json.dumps(item.model_dump()))
                    else:
                        parts.append(str(item))
                return "\n".join(parts)
            return ""
