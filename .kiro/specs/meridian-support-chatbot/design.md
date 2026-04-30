# Design Document: Meridian Support Chatbot

## Overview

A single-file-first Python app (`app.py` + 2 helper modules) connecting a Streamlit chat UI to a remote MCP server via synchronous LLM calls. No async, no custom exception classes, no test framework. Session state lives in `st.session_state`. Deployment target is HuggingFace Spaces.

**Stack:** Python 3.11 · Streamlit · `mcp` Python SDK (sync) · Gemini Flash (or GPT-4o-mini / Claude Haiku) · `python-dotenv`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        HuggingFace Spaces                       │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                        app.py                           │   │
│  │                                                         │   │
│  │  st.chat_input ──► chat_handler()                       │   │
│  │                         │                               │   │
│  │              ┌──────────┴──────────┐                    │   │
│  │              │                     │                    │   │
│  │       call_llm()            call_tool()                 │   │
│  │       (LLM API,             (mcp_client.py)             │   │
│  │        sync)                     │                      │   │
│  │              │                   │ HTTPS                │   │
│  └──────────────┼───────────────────┼────────────────────-─┘   │
│                 │                   │                           │
└─────────────────┼───────────────────┼───────────────────────────┘
                  │                   │
           LLM Provider          MCP_Server
           (Gemini/OpenAI/       (Cloud Run,
            Anthropic API)        Streamable HTTP)
```

**Request flow (single turn):**

```
Customer types message
  → chat_handler(user_message) in app.py
    → append {"role": "user", "content": user_message} to st.session_state.messages
    → auth gate: if tool is account-specific and not authenticated → return prompt
    → call_llm(st.session_state.messages, tools=discovered_tools)
      → LLM returns text OR tool_call
        → if tool_call:
            inline name-check: tool_name in discovered_tools?
            → call_tool(name, args) in mcp_client.py
              → returns (True, result_str) or (False, error_str)
            → append tool result to messages
            → call_llm again with updated messages
        → if text: return text
    → append {"role": "assistant", "content": response} to st.session_state.messages
    → st.rerun() to render updated chat
```

---

## Module Structure

```
app.py            # Streamlit UI + chat handler + LLM call loop (main file)
mcp_client.py     # MCP connection, tool discovery, call_tool()
config.py         # env var loading and validation
.env              # secrets (gitignored)
.env.example      # committed placeholder
requirements.txt
README.md
```

### `config.py`

Loads `.env` at import time. Raises `ValueError` with the missing key name for any absent required var. Exposes constants only — no classes.

```python
# Required
LLM_PROVIDER: str   # "gemini" | "openai" | "anthropic"
LLM_API_KEY: str

# Optional with defaults
LLM_MODEL: str      # defaults: "gemini-1.5-flash" / "gpt-4o-mini" / "claude-haiku-..."
MCP_SERVER_URL: str # default: "https://order-mcp-74afyau24q-uc.a.run.app/mcp"
```

### `mcp_client.py`

Synchronous wrapper around the `mcp` Python SDK. Called once at startup to connect and discover tools. Exposes two functions:

```python
def connect() -> list[dict]:
    """Connect to MCP server, return list of tool dicts {name, description, inputSchema}."""

def call_tool(name: str, args: dict) -> tuple[bool, str]:
    """Call a tool. Returns (True, result_text) or (False, user_friendly_error)."""
```

All exceptions caught inside `call_tool` — nothing propagates up. Errors printed to stderr.

### `app.py`

Contains everything else: Streamlit UI, LLM client setup, chat handler, tool dispatch loop, auth gate. Keeps orchestration logic as plain functions rather than a class.

Key functions:

```python
def init_session():
    """Initialise st.session_state.messages and st.session_state.authenticated."""

def build_system_prompt() -> str:
    """Return the system prompt string."""

def call_llm(messages: list[dict], tools: list[dict]) -> dict:
    """Call LLM synchronously. Returns response dict with 'text' or 'tool_call'."""

def check_auth_gate(tool_name: str) -> str | None:
    """Return a prompt-to-authenticate string if tool requires auth and user is not authenticated. Else None."""

def chat_handler(user_message: str) -> str:
    """Main handler: append message, run LLM loop, return final response string."""
```

---

## Session State

No custom dataclasses. Everything lives in `st.session_state`:

```python
st.session_state.messages       # list[dict] — {"role": "user"|"assistant"|"tool", "content": str}
st.session_state.authenticated  # bool — True after successful auth tool call
st.session_state.customer_id    # str | None — set on successful auth
st.session_state.tools          # list[dict] — discovered at startup, never changes
st.session_state.mcp_available  # bool — False if connect() failed at startup
```

Message list is a plain Python list. Append-only during a session — no mutation of existing entries.

---

## Conversation Flow Detail

### Normal turn

1. Customer submits message via `st.chat_input`
2. `chat_handler(user_message)` called
3. Message appended to `st.session_state.messages`
4. `call_llm(messages, tools=st.session_state.tools)` called synchronously
5. If LLM returns `tool_call`:
   - `check_auth_gate(tool_name)` — if blocked, return prompt immediately
   - Inline check: `tool_name in {t["name"] for t in st.session_state.tools}` — if not found, log to stderr, return friendly message
   - `call_tool(name, args)` called
   - Result appended to messages as `{"role": "tool", "content": result}`
   - Loop back to step 4 (max 5 iterations to prevent runaway)
6. If LLM returns text: append as assistant message, return text
7. `st.rerun()` triggers Streamlit to re-render the chat

### Authentication flow

- `st.session_state.authenticated` starts as `False`
- System prompt instructs LLM: call the `authenticate` tool when the customer asks for account data; skip if already authenticated (visible in message history)
- On successful auth tool result: `st.session_state.authenticated = True`, store `customer_id`
- `check_auth_gate` blocks order history tool calls when `authenticated` is `False`

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | Yes | — | `gemini`, `openai`, or `anthropic` |
| `LLM_API_KEY` | Yes | — | API key for the chosen LLM provider |
| `LLM_MODEL` | No | provider flash/mini | Model name override |
| `MCP_SERVER_URL` | No | Cloud Run endpoint | MCP server URL |

---

## Error Handling Strategy

Single pattern throughout: catch at the boundary, print to stderr, return a plain string. No custom exception classes.

```
mcp_client.call_tool()
  └─ try/except Exception
       ├─ print(f"[MCP ERROR] tool={name} error={e}", file=sys.stderr)
       └─ return (False, "I couldn't complete that request. Please try again.")

app.py chat_handler()
  └─ if not success: return error_str directly as assistant response

app.py top-level Streamlit handler
  └─ try/except Exception (catch-all)
       ├─ print(f"[APP ERROR] {e}", file=sys.stderr)
       └─ st.error("Something went wrong. Please refresh and try again.")
```

**Invalid tool name:**
- Print: `[INVALID TOOL] {name} not in discovered tools` to stderr
- Return: `"I'm not able to perform that action. How else can I help you?"`
- `call_tool` is never invoked

**Missing env var at startup:**
- `config.py` raises `ValueError("Missing required env var: LLM_API_KEY")`
- Streamlit shows the traceback in the build log; app does not start

**MCP server unreachable at startup:**
- `connect()` catches the error, prints to stderr, returns empty list
- `st.session_state.mcp_available = False`
- UI renders `st.error("Support services are temporarily unavailable.")`
