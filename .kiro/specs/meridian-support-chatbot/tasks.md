# Implementation Plan: Meridian Support Chatbot

## Overview

3-module Python app (`config.py`, `mcp_client.py`, `app.py`) connecting a Streamlit UI to a remote MCP server via synchronous LLM calls. No async, no tests, no Docker. Scoped to 3 hours.

## Tasks

- [ ] 1. Phase 1 — Project setup and configuration (0–30 min)

  - [x] 1.1 Scaffold project structure
    - Create `requirements.txt` with: `mcp`, `streamlit`, `python-dotenv`, `google-generativeai` (or `openai` / `anthropic`)
    - Create `.env.example` with placeholder values for `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `MCP_SERVER_URL`
    - Create empty files: `config.py`, `mcp_client.py`, `app.py`
    - _Requirements: 9.2_

  - [x] 1.2 Implement `config.py`
    - Use `python-dotenv` to load `.env` at import time
    - Expose `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `MCP_SERVER_URL` as module-level constants
    - For each required key (`LLM_PROVIDER`, `LLM_API_KEY`): raise `ValueError(f"Missing required env var: {key}")` if absent
    - Default `LLM_MODEL` to the provider's flash/mini tier; default `MCP_SERVER_URL` to the Cloud Run endpoint
    - _Requirements: 9.1, 9.3_

  - [x] 1.3 Implement `mcp_client.py` — `connect()`
    - Use the `mcp` Python SDK with `StreamableHTTPClientTransport` to connect to `MCP_SERVER_URL`
    - Call `session.list_tools()`, print each tool name to stdout, return the list as plain dicts `{name, description, inputSchema}`
    - On any exception: print `[MCP ERROR] connect failed: {e}` to stderr, return empty list
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 1.4 Implement `mcp_client.py` — `call_tool()`
    - Signature: `def call_tool(name: str, args: dict) -> tuple[bool, str]`
    - On success: return `(True, result_text)`
    - On any exception: print `[MCP ERROR] tool={name} error={e}` to stderr, return `(False, "I couldn't complete that request. Please try again.")`
    - _Requirements: 2.5, 8.1, 8.2_

- [x] 2. Phase 2 — LLM integration and core orchestration (30–90 min)

  - [x] 2.1 Implement `init_session()` in `app.py`
    - Initialise `st.session_state.messages = []`, `st.session_state.authenticated = False`, `st.session_state.customer_id = None`
    - On first run: call `mcp_client.connect()`, store result in `st.session_state.tools` and set `st.session_state.mcp_available`
    - _Requirements: 2.3, 3.2_

  - [x] 2.2 Implement `build_system_prompt()` in `app.py`
    - Return a system prompt string that: identifies the assistant as Meridian Electronics support, lists the four supported workflows (auth, availability, order, history), instructs the LLM to call `authenticate` before returning account data, and instructs it to confirm order details before placing an order
    - _Requirements: 7.2_

  - [x] 2.3 Implement `call_llm()` in `app.py`
    - Signature: `def call_llm(messages: list[dict], tools: list[dict]) -> dict`
    - Build the LLM request synchronously using the provider SDK selected by `config.LLM_PROVIDER`
    - Pass `tools` as the function/tool schema list so the LLM's native function-calling API constrains proposals to discovered tools
    - Return `{"type": "text", "content": str}` or `{"type": "tool_call", "name": str, "args": dict}`
    - _Requirements: 7.1, 7.3, 7.4_

  - [x] 2.4 Implement `check_auth_gate()` in `app.py`
    - Signature: `def check_auth_gate(tool_name: str) -> str | None`
    - If `tool_name` is an account-data tool (e.g. `get_order_history`) and `st.session_state.authenticated` is `False`: return `"Please authenticate first. What is your customer ID and password?"`
    - Otherwise return `None`
    - _Requirements: 3.3, 6.3_

  - [x] 2.5 Implement `chat_handler()` in `app.py`
    - Append user message to `st.session_state.messages`
    - Run LLM loop (max 5 iterations):
      - Call `call_llm(messages, tools)`
      - If `tool_call`: run `check_auth_gate`; if blocked return gate message. Inline name-check: if tool not in discovered set, print to stderr, return friendly message. Call `call_tool(name, args)`. Append tool result to messages. Continue loop.
      - If `text`: append as assistant message, return text
    - On any unhandled exception: print `[APP ERROR] {e}` to stderr, return `"Something went wrong. Please try again."`
    - _Requirements: 7.3, 7.4, 7.5, 8.1, 8.3_

- [-] 3. Phase 3 — Four core workflows (90–120 min)

  - [ ] 3.1 Verify authentication flow end-to-end
    - Run app locally, trigger auth by asking for order history
    - Confirm LLM calls the auth tool, `st.session_state.authenticated` becomes `True` on success
    - Confirm unauthenticated request is blocked with a prompt-to-authenticate message
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 3.2 Verify product availability flow end-to-end
    - Ask about a product by name; confirm LLM extracts identifier and calls the availability tool
    - Confirm response presents stock status in plain language
    - Confirm LLM asks for clarification when product name is ambiguous
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ] 3.3 Verify order placement flow end-to-end
    - Request an order; confirm LLM collects product ID and quantity, confirms with user, then calls the order tool
    - Confirm confirmation number is shown on success
    - Confirm rejection reason is relayed on failure
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 3.4 Verify order history flow end-to-end
    - Authenticate first, then request order history
    - Confirm orders are displayed with ID, date, items, and status
    - Confirm unauthenticated request is blocked
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 4. Phase 4 — UI polish and README (120–150 min)

  - [x] 4.1 Polish Streamlit UI
    - Add page title and a brief description of what the chatbot can do
    - Show a spinner (`st.spinner`) while the LLM is generating a response
    - If `st.session_state.mcp_available` is `False`, show `st.error()` banner and disable chat input
    - _Requirements: 1.1, 1.3, 2.4_

  - [x] 4.2 Write `README.md`
    - Quick Start: clone repo, copy `.env.example` to `.env`, fill in values, `pip install -r requirements.txt`, `streamlit run app.py`
    - Document all env vars with expected values or sources
    - Include the HuggingFace Spaces deployment URL (fill in after deploy)
    - _Requirements: 10.1, 10.2, 10.3_

- [ ] 5. Phase 5 — Deployment and submission (150–180 min)

  - [ ] 5.1 Deploy to HuggingFace Spaces
    - Add `sdk: streamlit` front-matter to `README.md` for Spaces auto-detection
    - Add all required env vars as Spaces secrets (Settings → Variables and secrets)
    - Push repo to HuggingFace; verify public HTTPS URL is live and all four workflows work
    - _Requirements: 1.1, 10.3_

  - [ ] 5.2 Final smoke test and GitHub push
    - Test all four workflows on the live Spaces URL
    - Push final code to GitHub; confirm repo is public and `.env` is gitignored
    - _Requirements: 9.1, 10.3_

  - [ ]* 5.3 Bonus deployment (stretch — only if time remains)
    - Deploy to Vercel, GCP Cloud Run, or another public platform
    - Update README with bonus deployment URL and platform-specific setup steps
    - _Requirements: 11.1, 11.2_

## Notes

- Tasks marked `*` are optional stretch items
- No automated tests — verify each workflow manually in tasks 3.1–3.4
- All errors go to stdout/stderr; nothing surfaces as a raw traceback in the UI
- Keep everything synchronous — no `async/await` anywhere
