---
title: Meridian Electronics Support Chatbot
emoji: 🖥️
colorFrom: blue
colorTo: indigo
sdk: docker
python_version: "3.11"
app_file: app.py
app_port: 8501
short_description: "Meridian support chatbot: Streamlit, Cerebras LLM, MCP"
pinned: false
---

# Meridian Electronics Support Chatbot

Streamlit UI + **Cerebras** LLM + remote **MCP** server for Meridian-style support: catalogue, orders, PIN auth, and order history.

## Screenshots

| Home | Chat (sign-in & stock) |
|------|-------------------------|
| ![Home](https://raw.githubusercontent.com/habeneyasu/meridian-support-mcp-chatbot/77545d6/docs/screenshots/default-home-page.png) | ![Login and stock](https://raw.githubusercontent.com/habeneyasu/meridian-support-mcp-chatbot/77545d6/docs/screenshots/login-and-stock.png) |

Screenshots are served from GitHub **raw** URLs so the Hugging Face Space git repo stays free of binary files ([HF policy](https://huggingface.co/docs/hub/xet)). To refresh images after UI changes, commit new PNGs on GitHub, then update these URLs (or point to `main` once merged).

## What it can do

- Check product availability and search the catalogue
- Place orders (confirm with the customer before submitting)
- Order history (after authentication)
- Authenticate with email + PIN (including Meridian MCP demo `@example.*` accounts)

## Quick Start

```bash
git clone https://github.com/habeneyasu/meridian-support-mcp-chatbot.git
cd meridian-support-mcp-chatbot
pip install -r requirements.txt
cp .env.example .env
# set CEREBRAS_API_KEY in .env
streamlit run app.py
# or: streamlit run streamlit_app.py
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CEREBRAS_API_KEY` | Yes | [Cerebras Cloud](https://cloud.cerebras.ai) API key |
| `CEREBRAS_MODEL` | No | Model id (default in `config.py`) |
| `MCP_SERVER_URL` | No | Defaults to Meridian Cloud Run MCP endpoint |

## Architecture

```
Streamlit (app.py) → Cerebras chat + tools
                  → mcp_client.py → MCP (Streamable HTTP)
```

## Requirements alignment (Kiro spec)

| Area | Spec | This repo |
|------|------|-----------|
| LLM | Gemini / OpenAI / Anthropic “flash” tier | **Cerebras** (cost-effective, OpenAI-style tools) |
| UI | Streamlit chat, spinner, friendly errors | Implemented; runtime errors also call `st.error` where wrapped |
| MCP | Connect, discover tools, `call_tool` | `mcp_client.py`; async wrapped for Streamlit |
| Auth gate | Block order tools until verified | `list_orders`, `get_order` gated; PIN via `verify_customer_pin` |
| Secrets | `.env`, `.env.example` | Yes; do not commit secrets |
| HF deploy | Public Space | **Docker** Space (`Dockerfile`), `app_port: 8501` |
| README | Quick start + env + URL | Fill in your Space URL below when live |

## Deploying to Hugging Face Spaces

Use **Docker** as the Space SDK (`sdk: docker`, `app_port: 8501` in this README). [Create a Space](https://huggingface.co/new-space), connect this repo, then **Settings → Variables and secrets** → add secret **`CEREBRAS_API_KEY`**. Optional: `CEREBRAS_MODEL`, `MCP_SERVER_URL`.

**Files at repo root:** `Dockerfile`, `requirements.txt`, `README.md`, `streamlit_app.py`, `app.py`, `config.py`, `mcp_client.py`.

**Troubleshooting:** Spiral “Welcome to Streamlit” = template files still present; ensure this repo (including `streamlit_app.py`) is what the Space builds. Build errors → check **Build** logs. “Support unavailable” → MCP URL unreachable from HF. Config error → missing `CEREBRAS_API_KEY` secret.

**Live Space URL:** `https://huggingface.co/spaces/<your-username>/<space-name>`

## Local Docker

```bash
docker build -t meridian-space .
docker run --rm -p 8502:8501 -e CEREBRAS_API_KEY="your-key" meridian-space
```

Open `http://localhost:8502` if port 8501 is already in use on the host.
