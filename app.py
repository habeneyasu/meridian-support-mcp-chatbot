# app.py — Streamlit UI, LLM orchestration, chat handler
import sys
import json
import streamlit as st
import config
import mcp_client

# ---------------------------------------------------------------------------
# Tools that require the customer to be authenticated before use
# ---------------------------------------------------------------------------
AUTH_REQUIRED_TOOLS = {"list_orders", "get_order"}


# ---------------------------------------------------------------------------
# 2.1  init_session
# ---------------------------------------------------------------------------
def init_session():
    """Initialise st.session_state on first load."""
    if "messages" not in st.session_state:
        st.session_state.messages = []          # list[dict] — {role, content}
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "customer_id" not in st.session_state:
        st.session_state.customer_id = None
    if "tools" not in st.session_state:
        tools = mcp_client.connect()
        st.session_state.tools = tools
        st.session_state.mcp_available = len(tools) > 0


# ---------------------------------------------------------------------------
# 2.2  build_system_prompt
# ---------------------------------------------------------------------------
def build_system_prompt() -> str:
    return """You are a helpful customer support assistant for Meridian Electronics, \
a company that sells computer products including monitors, keyboards, printers, \
networking gear, and accessories.

You can help customers with the following workflows:
1. Check product availability — use list_products, get_product, or search_products
2. Place an order — use create_order (always confirm product and quantity with the customer first)
3. Look up order history — use list_orders or get_order (requires authentication)
4. Authenticate a returning customer — use get_customer to look up the account, \
then verify_customer_pin to confirm identity

Important rules:
- Before returning any account-specific data (orders, customer details), \
you MUST call verify_customer_pin to authenticate the customer. \
If the conversation history already shows a successful authentication, skip re-authentication.
- Before placing an order with create_order, confirm the product name/ID and quantity \
with the customer and wait for their explicit confirmation.
- Stay within the scope of Meridian Electronics product and order support. \
Politely decline unrelated requests.
- Be concise, friendly, and professional."""


# ---------------------------------------------------------------------------
# Helper — convert our tool dicts to the format each LLM provider expects
# ---------------------------------------------------------------------------
def _tools_for_gemini(tools: list[dict]) -> list[dict]:
    """Convert MCP tool dicts to Gemini function declarations."""
    declarations = []
    for t in tools:
        schema = t.get("inputSchema", {})
        declarations.append({
            "name": t["name"],
            "description": t["description"],
            "parameters": schema if schema else {"type": "object", "properties": {}},
        })
    return [{"function_declarations": declarations}]


def _tools_for_openai(tools: list[dict]) -> list[dict]:
    """Convert MCP tool dicts to OpenAI function tool format."""
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


def _tools_for_anthropic(tools: list[dict]) -> list[dict]:
    """Convert MCP tool dicts to Anthropic tool format."""
    result = []
    for t in tools:
        schema = t.get("inputSchema", {})
        result.append({
            "name": t["name"],
            "description": t["description"],
            "input_schema": schema if schema else {"type": "object", "properties": {}},
        })
    return result


# ---------------------------------------------------------------------------
# 2.3  call_llm
# ---------------------------------------------------------------------------
def call_llm(messages: list[dict], tools: list[dict]) -> dict:
    """
    Call the LLM synchronously.
    Returns {"type": "text", "content": str}
         or {"type": "tool_call", "name": str, "args": dict}
    """
    provider = config.LLM_PROVIDER
    model = config.get_model()

    if provider == "gemini":
        return _call_gemini(messages, tools, model)
    elif provider == "openai":
        return _call_openai(messages, tools, model)
    elif provider == "anthropic":
        return _call_anthropic(messages, tools, model)
    else:
        return {"type": "text", "content": "LLM provider not configured."}


def _call_gemini(messages: list[dict], tools: list[dict], model: str) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=config.LLM_API_KEY)

    # Build Gemini contents from message history (skip system messages)
    contents = []
    for m in messages:
        role = m["role"]
        content = m["content"]
        if role == "system":
            continue
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})
        elif role == "tool":
            contents.append({"role": "user", "parts": [{"text": f"[Tool result]: {content}"}]})

    gemini_tools = _tools_for_gemini(tools) if tools else None
    system_prompt = build_system_prompt()

    llm = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_prompt,
        tools=gemini_tools,
    )
    response = llm.generate_content(contents)

    # Check for function call
    for part in response.candidates[0].content.parts:
        if hasattr(part, "function_call") and part.function_call.name:
            fc = part.function_call
            args = dict(fc.args) if fc.args else {}
            return {"type": "tool_call", "name": fc.name, "args": args}

    # Plain text response
    return {"type": "text", "content": response.text}


def _call_openai(messages: list[dict], tools: list[dict], model: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=config.LLM_API_KEY)

    # Prepend system message
    oai_messages = [{"role": "system", "content": build_system_prompt()}]
    for m in messages:
        if m["role"] == "system":
            continue
        oai_messages.append({"role": m["role"], "content": m["content"]})

    oai_tools = _tools_for_openai(tools) if tools else None
    kwargs = {"model": model, "messages": oai_messages}
    if oai_tools:
        kwargs["tools"] = oai_tools
        kwargs["tool_choice"] = "auto"

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0].message

    if choice.tool_calls:
        tc = choice.tool_calls[0]
        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
        return {"type": "tool_call", "name": tc.function.name, "args": args}

    return {"type": "text", "content": choice.content or ""}


def _call_anthropic(messages: list[dict], tools: list[dict], model: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=config.LLM_API_KEY)

    anth_messages = []
    for m in messages:
        if m["role"] == "system":
            continue
        role = "assistant" if m["role"] == "assistant" else "user"
        anth_messages.append({"role": role, "content": m["content"]})

    anth_tools = _tools_for_anthropic(tools) if tools else None
    kwargs = {
        "model": model,
        "max_tokens": 1024,
        "system": build_system_prompt(),
        "messages": anth_messages,
    }
    if anth_tools:
        kwargs["tools"] = anth_tools

    response = client.messages.create(**kwargs)

    for block in response.content:
        if block.type == "tool_use":
            return {"type": "tool_call", "name": block.name, "args": block.input or {}}

    text = " ".join(b.text for b in response.content if hasattr(b, "text"))
    return {"type": "text", "content": text}


# ---------------------------------------------------------------------------
# 2.4  check_auth_gate
# ---------------------------------------------------------------------------
def check_auth_gate(tool_name: str) -> str | None:
    """
    Returns a prompt-to-authenticate string if the tool requires auth
    and the customer is not yet authenticated. Otherwise returns None.
    """
    if tool_name in AUTH_REQUIRED_TOOLS and not st.session_state.authenticated:
        return (
            "I need to verify your identity before I can access your orders. "
            "Could you please provide your customer ID?"
        )
    return None


# ---------------------------------------------------------------------------
# 2.5  chat_handler
# ---------------------------------------------------------------------------
def chat_handler(user_message: str) -> str:
    """
    Main chat handler: appends user message, runs LLM tool loop, returns response.
    """
    try:
        # Append user message to history
        st.session_state.messages.append({"role": "user", "content": user_message})

        tools = st.session_state.get("tools", [])
        discovered_names = {t["name"] for t in tools}

        # LLM loop — max 5 iterations to prevent runaway tool calls
        for _ in range(5):
            result = call_llm(st.session_state.messages, tools)

            if result["type"] == "text":
                response = result["content"]
                st.session_state.messages.append({"role": "assistant", "content": response})
                return response

            # Tool call path
            tool_name = result["name"]
            tool_args = result["args"]

            # Auth gate check
            gate_msg = check_auth_gate(tool_name)
            if gate_msg:
                st.session_state.messages.append({"role": "assistant", "content": gate_msg})
                return gate_msg

            # Inline name validation — safety net beyond LLM's native schema filtering
            if tool_name not in discovered_names:
                print(f"[INVALID TOOL] {tool_name} not in discovered tools", file=sys.stderr)
                msg = "I'm not able to perform that action. How else can I help you?"
                st.session_state.messages.append({"role": "assistant", "content": msg})
                return msg

            # Execute the tool
            success, tool_result = mcp_client.call_tool(tool_name, tool_args)

            # Handle successful auth — update session state
            if tool_name == "verify_customer_pin" and success:
                st.session_state.authenticated = True

            # Append tool result to history so LLM can synthesise a response
            tool_content = tool_result if success else f"[Tool error]: {tool_result}"
            st.session_state.messages.append({"role": "tool", "content": tool_content})

            # If tool failed, return the friendly error immediately
            if not success:
                st.session_state.messages.append({"role": "assistant", "content": tool_result})
                return tool_result

        # Fallback if loop exhausted without a text response
        fallback = "I'm having trouble completing that request. Please try again."
        st.session_state.messages.append({"role": "assistant", "content": fallback})
        return fallback

    except Exception as e:
        print(f"[APP ERROR] {e}", file=sys.stderr)
        return "Something went wrong. Please try again."


# ---------------------------------------------------------------------------
# Streamlit UI — wired up in Phase 4; minimal scaffold here
# ---------------------------------------------------------------------------
if __name__ == "__main__" or True:
    st.set_page_config(page_title="Meridian Support", page_icon="🖥️")

    try:
        config.validate()
    except ValueError as e:
        st.error(str(e))
        st.stop()

    init_session()

    st.title("🖥️ Meridian Electronics Support")
    st.caption("Ask me about products, place orders, or check your order history.")

    if not st.session_state.mcp_available:
        st.error("Support services are temporarily unavailable. Please try again later.")
        st.stop()

    # Render conversation history
    for msg in st.session_state.messages:
        if msg["role"] in ("user", "assistant"):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("How can I help you today?"):
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = chat_handler(prompt)
            st.markdown(response)
