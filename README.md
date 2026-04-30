---
title: Meridian Electronics Support Chatbot
emoji: 🖥️
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: "1.35.0"
app_file: app.py
pinned: false
---

# 🖥️ Meridian Electronics Support Chatbot

An AI-powered customer support chatbot for Meridian Electronics. Connects to a live MCP server to handle product availability, order placement, and order history — with customer authentication.

## What it can do

- Check product availability and search the catalogue
- Place orders (with confirmation before submitting)
- Look up order history (requires authentication)
- Authenticate returning customers via PIN

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/habeneyasu/meridian-support-mcp-chatbot.git
cd meridian-support-mcp-chatbot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and fill in your values

# 4. Run
streamlit run app.py
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Yes | `gemini`, `openai`, or `anthropic` |
| `LLM_API_KEY` | Yes | API key for the chosen provider |
| `LLM_MODEL` | No | Model override (defaults to flash/mini tier) |
| `MCP_SERVER_URL` | No | MCP server URL (defaults to Meridian's Cloud Run endpoint) |

Default models per provider:
- `gemini` → `gemini-1.5-flash`
- `openai` → `gpt-4o-mini`
- `anthropic` → `claude-haiku-20240307`

## Architecture

```
Streamlit UI (app.py)
    │
    ├── config.py          — env var loading and validation
    ├── mcp_client.py      — MCP server connection and tool execution
    │       │
    │       └── MCP Server (https://order-mcp-74afyau24q-uc.a.run.app/mcp)
    │               Tools: list_products, get_product, search_products,
    │                      get_customer, verify_customer_pin,
    │                      list_orders, get_order, create_order
    │
    └── LLM (Gemini Flash / GPT-4o-mini / Claude Haiku)
```

## Deployment

**Live URL:** *(add HuggingFace Spaces URL after deployment)*

Deployed on HuggingFace Spaces. To deploy your own:
1. Create a new Space with `sdk: streamlit`
2. Push this repo
3. Add `LLM_PROVIDER` and `LLM_API_KEY` as Spaces secrets (Settings → Variables and secrets)
