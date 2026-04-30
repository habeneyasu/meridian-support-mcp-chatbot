# mcp_client.py — MCP server connection, tool discovery, and tool execution
import sys
import json
import asyncio
import threading
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession
import config


def _schema_dict(tool) -> dict:
    if not tool.inputSchema:
        return {}
    if isinstance(tool.inputSchema, dict):
        return tool.inputSchema
    return tool.inputSchema.model_dump()


def _content_text(result) -> str:
    if not result.content:
        return ""
    parts = []
    for item in result.content:
        if hasattr(item, "text"):
            parts.append(item.text)
        elif hasattr(item, "model_dump"):
            parts.append(json.dumps(item.model_dump()))
        else:
            parts.append(str(item))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Run async code safely from a sync context (works inside Streamlit's loop)
# ---------------------------------------------------------------------------
def _run_async(coro):
    """
    Run an async coroutine in a dedicated background thread with its own
    event loop. This avoids conflicts with Streamlit's internal event loop.
    """
    result_holder = {}

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_holder["result"] = loop.run_until_complete(coro)
        except Exception as e:
            result_holder["error"] = e
        finally:
            loop.close()

    t = threading.Thread(target=run)
    t.start()
    t.join()

    if "error" in result_holder:
        raise result_holder["error"]
    return result_holder["result"]


# ---------------------------------------------------------------------------
# connect — discover tools at startup
# ---------------------------------------------------------------------------
def connect() -> list[dict]:
    """
    Connect to the MCP server, discover tools.
    Returns a list of tool dicts: {name, description, inputSchema}.
    On failure prints to stderr and returns an empty list.
    """
    try:
        return _run_async(_connect_async())
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
                tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": _schema_dict(tool),
                })
                print(f"[MCP] Discovered tool: {tool.name}")
            return tools


# ---------------------------------------------------------------------------
# call_tool — execute a single tool call
# ---------------------------------------------------------------------------
def call_tool(name: str, args: dict) -> tuple[bool, str]:
    """
    Call a tool on the MCP server.
    Returns (True, result_text) on success.
    Returns (False, user_friendly_error) on any failure.
    """
    try:
        result = _run_async(_call_tool_async(name, args))
        return (True, result)
    except Exception as e:
        print(f"[MCP ERROR] tool={name} error={e}", file=sys.stderr)
        return (False, "I couldn't complete that request. Please try again.")


async def _call_tool_async(name: str, args: dict) -> str:
    async with streamablehttp_client(config.MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            return _content_text(result)
