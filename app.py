# app.py — Streamlit UI, LLM orchestration, chat handler
import os
import sys
import json
import re
import uuid
import streamlit as st
from cerebras.cloud.sdk import Cerebras
import config
import mcp_client

# ---------------------------------------------------------------------------
# Tools that require the customer to be authenticated before use
# ---------------------------------------------------------------------------
AUTH_REQUIRED_TOOLS = {"list_orders", "get_order"}


def _normalize_json_quotes_for_parse(s: str) -> str:
    """Replace common Unicode quotes so JSON tool-call blobs parse reliably."""
    for a, b in (
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u00ab", '"'),
        ("\u00bb", '"'),
    ):
        s = s.replace(a, b)
    return s


_MERIDIAN_TEST_EMAIL = re.compile(
    r"^[a-z0-9._%+-]+@example\.(net|com|org)\s*$",
    re.IGNORECASE,
)


def _is_meridian_demo_credentials(email: str, pin: str) -> bool:
    """True when email/PIN match the MCP assessment test-account pattern."""
    e = email.strip()
    p = pin.strip()
    if not _MERIDIAN_TEST_EMAIL.match(e):
        return False
    if not p.isdigit() or not (4 <= len(p) <= 8):
        return False
    return True


def _verify_pin_args_are_placeholders(args: dict) -> bool:
    """True if verify_customer_pin was given obvious template / filler values."""
    email = str(args.get("email") or args.get("customer_email") or "").strip().lower()
    pin = str(args.get("pin") or args.get("password") or "").strip().lower()
    if not email or not pin:
        return True
    # Official Meridian MCP test customers (example.net / .com / .org + numeric PIN)
    if _is_meridian_demo_credentials(email, pin):
        return False
    lone = {"email", "pin", "password", "none", "null", "n/a", "na", "xxx", "changeme"}
    if email in lone or pin in lone:
        return True
    # Do not use "@example." / "example@" substring checks — they false-positive on
    # real demo addresses like donaldgarcia@example.net.
    needles = (
        "your email",
        "your pin",
        "your_email",
        "your_pin",
        "youremail",
        "yourpin",
        "placeholder",
        "test@test",
        "dummy",
        "fake@",
        "sample@",
    )
    blob = f"{email} {pin}"
    if any(n in blob for n in needles):
        return True
    if email.startswith("your ") or pin.startswith("your "):
        return True
    return False


def _auth_placeholder_reply() -> str:
    return (
        "I still need a valid **email** and **PIN** to sign you in. Please send the "
        "email on your Meridian account and your numeric PIN together (for example: "
        "name@example.net and 1234). If you used placeholder text like \"your email\", "
        "replace it with your real details."
    )


# ---------------------------------------------------------------------------
# init_session
# ---------------------------------------------------------------------------
def init_session():
    """Initialise st.session_state on first load."""
    if "messages" not in st.session_state:
        st.session_state.messages = []      # list[dict] — {role, content}
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "customer_id" not in st.session_state:
        st.session_state.customer_id = None
    if "tools" not in st.session_state:
        tools = mcp_client.connect()
        st.session_state.tools = tools
        st.session_state.mcp_available = len(tools) > 0


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------
def build_system_prompt() -> str:
    return """You are Meridian Electronics customer support (monitors, keyboards, \
printers, networking gear, accessories). Use only the tools provided in this API \
call (schemas define names and arguments). The customer must never hear tool names, \
JSON, or \"I will call…\"; speak like a human agent.

Products/stock: call search_products or list_products without unnecessary delay; \
show name, SKU, price, and stock. If the product is unclear, ask once, then search.

Auth and orders: verify identity before sharing order/account details; ask for the \
email on file and PIN in plain language. Accept @example.net / .com / .org addresses \
with a 4–8 digit PIN when the customer supplies them (demo data). Never use \
placeholder credentials.

After each tool result, answer in natural language (no tool-only loops, no raw JSON).

Orders: get SKU (or a uniquely identifiable product) and quantity; confirm before \
submitting. Do not assume a category (e.g. monitor) unless the customer said it. \
If they only say they want to order, ask what item and how many or search the \
catalogue.

Order history: present order id, date, items, and status when listing.

Stay on-topic; be concise and professional."""


# ---------------------------------------------------------------------------
# Tool schema conversion — OpenAI-compatible format (Cerebras uses this)
# ---------------------------------------------------------------------------
def _tools_for_cerebras(tools: list[dict]) -> list[dict]:
    """Convert MCP tool dicts to OpenAI-compatible function tool format."""
    result = []
    for t in tools:
        schema = t.get("inputSchema", {})
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": schema if schema else {"type": "object", "properties": {}},
            },
        })
    return result


# ---------------------------------------------------------------------------
# call_llm — Cerebras (OpenAI-compatible)
# ---------------------------------------------------------------------------
def _trim_messages(messages: list[dict], max_turns: int = 6) -> list[dict]:
    """
    Keep only the most recent max_turns user/assistant/tool exchanges.
    This prevents context length errors on models with small windows.
    """
    # Filter to only conversational roles (skip any stray system entries)
    conv = [m for m in messages if m["role"] in ("user", "assistant", "tool")]
    # Keep last max_turns * 2 entries (each turn = user + assistant/tool)
    return conv[-(max_turns * 2):]


def call_llm(messages: list[dict], tools: list[dict]) -> dict:
    """
    Call Cerebras LLM synchronously.
    Returns {"type": "text", "content": str}
         or {"type": "tool_call", "name": str, "args": dict}
    """
    client = Cerebras(api_key=config.CEREBRAS_API_KEY)

    # Trim history to stay within context window
    trimmed = _trim_messages(messages)

    # Build message list with system prompt prepended.
    # OpenAI-compatible providers (Cerebras) require assistant messages that
    # include tool_calls, each followed by a tool message with matching tool_call_id.
    llm_messages = [{"role": "system", "content": build_system_prompt()}]
    for m in trimmed:
        role = m["role"]
        if role == "tool":
            tcid = m.get("tool_call_id")
            if tcid:
                llm_messages.append({
                    "role": "tool",
                    "tool_call_id": tcid,
                    "content": m.get("content") or "",
                })
            else:
                # Legacy history (before proper tool IDs)
                llm_messages.append({
                    "role": "user",
                    "content": f"[Tool result]: {m.get('content', '')}",
                })
        elif role == "assistant":
            entry: dict = {"role": "assistant"}
            if m.get("tool_calls"):
                entry["tool_calls"] = m["tool_calls"]
                entry["content"] = m.get("content") if m.get("content") else ""
            else:
                entry["content"] = m.get("content") or ""
            llm_messages.append(entry)
        elif role == "user":
            llm_messages.append({"role": "user", "content": m.get("content", "")})

    cerebras_tools = _tools_for_cerebras(tools) if tools else None
    kwargs = {
        "model": config.get_model(),
        "messages": llm_messages,
    }
    if cerebras_tools:
        kwargs["tools"] = cerebras_tools
        kwargs["tool_choice"] = "auto"

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0].message

    if choice.tool_calls:
        tc = choice.tool_calls[0]
        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
        return {"type": "tool_call", "name": tc.function.name, "args": args}

    content = choice.content or ""

    # Fallback: model sometimes emits tool calls as JSON text instead of tool_calls.
    tc = _parse_tool_call_from_text(content)
    if tc:
        return tc

    return {"type": "text", "content": content}


def _parse_tool_call_from_text(content: str) -> dict | None:
    """
    If content looks like a JSON tool invocation, return
    {"type": "tool_call", "name": str, "args": dict}; else None.

    Uses raw_decode so only the *first* JSON value is parsed — duplicate or
    trailing JSON blobs (common model mistake) no longer break parsing.
    """
    stripped = _normalize_json_quotes_for_parse(content.strip())
    if stripped.startswith("```"):
        parts = stripped.split("```")
        stripped = parts[1] if len(parts) > 1 else stripped
        if stripped.lstrip().startswith("json"):
            stripped = stripped.lstrip()[4:]
        stripped = stripped.strip()

    start = stripped.find("{")
    if start < 0:
        return None

    decoder = json.JSONDecoder()
    try:
        parsed, _end = decoder.raw_decode(stripped[start:])
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None
    name = parsed.get("name") or parsed.get("function")
    arguments = parsed.get("arguments") or parsed.get("parameters") or {}
    if name and isinstance(arguments, dict):
        return {"type": "tool_call", "name": name, "args": arguments}
    return None


# ---------------------------------------------------------------------------
# check_auth_gate
# ---------------------------------------------------------------------------
def check_auth_gate(tool_name: str) -> str | None:
    """
    Returns a prompt-to-authenticate string if the tool requires auth
    and the customer is not yet authenticated. Otherwise returns None.
    """
    if tool_name in AUTH_REQUIRED_TOOLS and not st.session_state.authenticated:
        return (
            "I need to verify your identity before I can show orders. "
            "Please share the email on your Meridian account and your PIN."
        )
    return None


# ---------------------------------------------------------------------------
# chat_handler
# ---------------------------------------------------------------------------
def chat_handler(user_message: str) -> str:
    """Main handler: appends user message, runs LLM tool loop, returns response."""
    try:
        st.session_state.messages.append({"role": "user", "content": user_message})

        tools = st.session_state.get("tools", [])
        discovered_names = {t["name"] for t in tools}

        # LLM loop — max 8 iterations (auth flows: get_customer + verify + reply)
        for _ in range(8):
            result = call_llm(st.session_state.messages, tools)

            if result["type"] == "text":
                response = result["content"]
                st.session_state.messages.append({"role": "assistant", "content": response})
                return response

            # Tool call path
            tool_name = result["name"]
            tool_args = result["args"]

            # Auth gate
            gate_msg = check_auth_gate(tool_name)
            if gate_msg:
                st.session_state.messages.append({"role": "assistant", "content": gate_msg})
                return gate_msg

            # Inline name validation — safety net
            if tool_name not in discovered_names:
                print(f"[INVALID TOOL] {tool_name} not in discovered tools", file=sys.stderr)
                msg = "I'm not able to perform that action. How else can I help you?"
                st.session_state.messages.append({"role": "assistant", "content": msg})
                return msg

            # Block template / hallucinated credentials (common model mistake)
            if tool_name == "verify_customer_pin" and _verify_pin_args_are_placeholders(
                tool_args
            ):
                print(
                    "[AUTH] blocked verify_customer_pin — placeholder or empty args",
                    file=sys.stderr,
                )
                msg = _auth_placeholder_reply()
                st.session_state.messages.append({"role": "assistant", "content": msg})
                return msg

            # Record assistant tool call (required for OpenAI-compatible tool chains)
            tool_call_id = f"call_{uuid.uuid4().hex[:24]}"
            st.session_state.messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_args) if tool_args else "{}",
                        },
                    }
                ],
            })

            # Execute tool
            success, tool_result = mcp_client.call_tool(tool_name, tool_args)

            # Update auth state on successful verify_customer_pin
            if tool_name == "verify_customer_pin" and success:
                st.session_state.authenticated = True
                cid = tool_args.get("customer_id") or tool_args.get("email")
                if cid:
                    st.session_state.customer_id = str(cid)

            tool_content = tool_result if success else f"[Tool error]: {tool_result}"
            # Truncate large tool results to avoid context overflow
            if len(tool_content) > 1500:
                tool_content = tool_content[:1500] + "... [truncated]"
            st.session_state.messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": tool_content,
            })

            if not success:
                st.session_state.messages.append({"role": "assistant", "content": tool_result})
                return tool_result

        fallback = (
            "I'm having trouble completing that request — the conversation hit an "
            "internal step limit. Please try again; for sign-in, share your customer "
            "ID (or email) and PIN in one message so I can verify you in fewer steps."
        )
        st.session_state.messages.append({"role": "assistant", "content": fallback})
        return fallback

    except Exception as e:
        print(f"[APP ERROR] {e}", file=sys.stderr)
        return "Something went wrong. Please try again."


def _run_chat_handler_safe(prompt: str) -> str:
    """Run chat_handler; on failure log, show st.error, return a safe message."""
    try:
        return chat_handler(prompt)
    except Exception as e:
        print(f"[APP ERROR] {e}", file=sys.stderr)
        st.error("Something went wrong. Please refresh and try again.")
        return "Something went wrong. Please try again."


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Meridian Electronics Support",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — dark tech theme with brand accent
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp {
    background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%);
    min-height: 100vh;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
    border-right: 1px solid #30363d;
}
[data-testid="stSidebar"] .stMarkdown h1, [data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 { color: #58a6ff; }
[data-testid="stChatMessage"] {
    background: rgba(22, 27, 34, 0.85) !important;
    border: 1px solid #30363d;
    border-radius: 12px !important;
    margin-bottom: 8px;
}
[data-testid="stChatMessage"][data-testid*="user"] { border-left: 3px solid #58a6ff; }
[data-testid="stChatInput"] {
    background: rgba(22, 27, 34, 0.9) !important;
    border: 1px solid #30363d !important;
    border-radius: 12px !important;
    color: #e6edf3 !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #58a6ff !important;
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.12) !important;
}
.stButton > button {
    background: linear-gradient(135deg, #1f6feb 0%, #388bfd 100%);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 500;
    width: 100%;
    padding: 0.5rem 1rem;
}
[data-testid="stMetric"] {
    background: rgba(22, 27, 34, 0.8);
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 1rem;
}
[data-testid="stMetricValue"] { color: #58a6ff; }
[data-testid="stMetricLabel"] { color: #8b949e; }
.stSuccess, .stError, .stInfo { border-radius: 8px; }
hr { border-color: #30363d; }
.stMarkdown, p, li { color: #e6edf3; }
h1, h2, h3 { color: #f0f6fc; }
.hero-banner {
    background: linear-gradient(135deg, #1f6feb22 0%, #388bfd11 100%);
    border: 1px solid #1f6feb44;
    border-radius: 16px;
    padding: 1.5rem 2rem;
    margin-bottom: 1.5rem;
    text-align: center;
}
.hero-title {
    font-size: 2rem;
    font-weight: 700;
    background: linear-gradient(135deg, #58a6ff, #79c0ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
}
.hero-subtitle { color: #8b949e; font-size: 0.95rem; margin-top: 0.4rem; }
.chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 1rem 0; }
.chip {
    background: rgba(31, 111, 235, 0.15);
    border: 1px solid #1f6feb44;
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.82rem;
    color: #58a6ff;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------
try:
    config.validate()
except ValueError as e:
    st.error(f"Configuration error: {e}")
    if os.getenv("SPACE_ID"):
        st.info(
            "This Space needs a **secret** named exactly `CEREBRAS_API_KEY`. "
            "Open **Settings → Variables and secrets → New secret**, add it, "
            "then **Factory reboot** (or push a new commit) so the app restarts."
        )
        st.markdown(
            f"[Open this Space’s settings](https://huggingface.co/spaces/{os.getenv('SPACE_ID')}/settings)"
        )
    else:
        st.info(
            "Copy `.env.example` to `.env`, set `CEREBRAS_API_KEY`, and run again "
            "(or pass `-e CEREBRAS_API_KEY=...` with Docker)."
        )
    st.stop()

init_session()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🖥️ Meridian Electronics")
    st.markdown("*AI-Powered Customer Support*")
    st.divider()

    # Auth status
    if st.session_state.authenticated:
        st.success(f"🔓 Signed in as **{st.session_state.customer_id or 'Customer'}**")
    else:
        st.info("🔒 Not authenticated\nSign in to view orders.")

    st.divider()

    # Quick actions
    st.markdown("### ⚡ Quick Actions")
    quick_actions = [
        ("🔍 Browse Products",    "Show me all available products"),
        ("📦 Check Stock",        "What monitors do you have in stock?"),
        ("🛒 Place an Order",     "I'd like to place an order"),
        ("📋 My Orders",          "Show me my order history"),
        ("🔐 Sign In",            "I want to authenticate my account"),
    ]
    for label, prompt_text in quick_actions:
        if st.button(label, key=f"qa_{label}"):
            st.session_state["_quick_action"] = prompt_text
            st.rerun()

    st.divider()

    # Stats
    st.markdown("### 📊 Session Info")
    msg_count = len([m for m in st.session_state.messages if m["role"] == "user"])
    tool_count = len([m for m in st.session_state.messages if m["role"] == "tool"])
    col1, col2 = st.columns(2)
    col1.metric("Messages", msg_count)
    col2.metric("Tool Calls", tool_count)

    st.divider()

    # Clear chat
    if st.button("🗑️ Clear Conversation", key="clear"):
        st.session_state.messages = []
        st.session_state.authenticated = False
        st.session_state.customer_id = None
        st.rerun()

    st.divider()
    st.markdown(
        "<div style='color:#8b949e;font-size:0.75rem;text-align:center'>"
        "Powered by Cerebras · MCP · Streamlit"
        "</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
if not st.session_state.mcp_available:
    st.error("⚠️ Support services are temporarily unavailable. Please try again later.")
    st.stop()

# Hero banner
st.markdown("""
<div class="hero-banner">
    <p class="hero-title">🖥️ Meridian Electronics Support</p>
    <p class="hero-subtitle">
        Check product availability · Place orders · Track your order history
    </p>
</div>
""", unsafe_allow_html=True)

# Welcome message on first load
if not st.session_state.messages:
    st.markdown("""
<div class="chip-row">
    <span class="chip">🔍 Browse products</span>
    <span class="chip">📦 Check stock</span>
    <span class="chip">🛒 Place an order</span>
    <span class="chip">📋 Order history</span>
    <span class="chip">🔐 Sign in</span>
</div>
""", unsafe_allow_html=True)

# Render conversation history (skip tool rows; skip assistant rows that are only tool_calls)
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(msg.get("content") or "")
    elif msg["role"] == "assistant":
        body = msg.get("content")
        if body:
            with st.chat_message("assistant"):
                st.markdown(body)

# Handle quick action injection
if "_quick_action" in st.session_state:
    injected = st.session_state.pop("_quick_action")
    with st.chat_message("user"):
        st.markdown(injected)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = _run_chat_handler_safe(injected)
        st.markdown(response)
    st.rerun()

if prompt := st.chat_input("Ask me anything about Meridian Electronics..."):
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = _run_chat_handler_safe(prompt)
        st.markdown(response)

