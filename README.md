---
title: Meridian Electronics Support Chatbot
emoji: 🖥️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8501
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
| `CEREBRAS_API_KEY` | Yes | API key from [Cerebras Cloud](https://cloud.cerebras.ai) |
| `CEREBRAS_MODEL` | No | Model id (see Cerebras docs; repo default in `config.py`) |
| `MCP_SERVER_URL` | No | MCP server URL (defaults to Meridian Cloud Run endpoint) |

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
    └── LLM (Cerebras API, OpenAI-compatible chat completions)
```

## Deploying to Hugging Face Spaces

The **New Space** UI offers **Gradio**, **Docker**, and **Static** — not a separate Streamlit option. This project uses **Docker**: `README.md` sets `sdk: docker` and `app_port: 8501`; the `Dockerfile` installs dependencies and runs Streamlit on port **8501** (required for Streamlit on Spaces).

### 1. Create the Space

1. Log in at [huggingface.co](https://huggingface.co).
2. Click **New** → **Space** (or [huggingface.co/new-space](https://huggingface.co/new-space)).
3. Choose a name, license, and visibility (**Public** if you want a shareable URL).
4. Under **Select the Space SDK**, choose **Docker** (not Gradio — this app is Streamlit inside Docker).
5. Create the Space, then push this repository (or connect GitHub) so the Space root contains `Dockerfile`, `requirements.txt`, `streamlit_app.py`, `app.py`, `config.py`, `mcp_client.py`, and `README.md`.

### 2. Connect your code

**Option A — Push this repository**

1. Create an empty Space (or one linked to your GitHub account).
2. In the Space **Files** tab, use **Add file** → upload, or clone the Space locally and `git push` your project so the root contains at least:
   - `Dockerfile`, `requirements.txt`, `README.md` (YAML: `sdk: docker`, `app_port: 8501`)
   - `streamlit_app.py`, `app.py`, `config.py`, `mcp_client.py`

**Option B — GitHub integration**

1. When creating the Space, pick **Import from GitHub** and select this repo/branch.
2. Hugging Face will build from that branch on each push.

### 3. Add secrets (required)

1. Open the Space → **Settings** → **Variables and secrets**.
2. Under **Secrets**, add:
   - **`CEREBRAS_API_KEY`** — your Cerebras API key (same as in local `.env`).
3. Optionally add **Repository secrets** or **Variables**:
   - **`CEREBRAS_MODEL`** — if you want to override the default model.
   - **`MCP_SERVER_URL`** — only if you are not using the default Meridian MCP URL.

Do **not** commit `.env` or real keys; Spaces injects secrets as environment variables at runtime.

### 4. Build and open the app

1. After the first push, the Space **Build** log should build the `Dockerfile` (which runs `pip install -r requirements.txt`) and start Streamlit on port 8501.
2. When the build succeeds, open the public Space URL (e.g. `https://huggingface.co/spaces/<user>/<space-name>`).

### 5. Troubleshooting

- **You only see “Welcome to Streamlit!” / spiral demo** — the Space is still running Hugging Face’s template `streamlit_app.py`, not this repo. **Replace** the Space files with your GitHub push (include this repo’s `streamlit_app.py` and `app.py`), or delete the template `streamlit_app.py` and set the README `app_file` to `app.py` if you use a Streamlit-native Space. For **Docker** Spaces, ensure the **Build** log shows your `Dockerfile` building and `CMD` running `streamlit run streamlit_app.py` (or `app.py`).
- **Build fails on dependencies** — ensure `requirements.txt` pins compatible versions if needed; check the **Build** log.
- **Configuration error in the app** — `CEREBRAS_API_KEY` is missing or wrong; re-check **Variables and secrets** (secret names must match `config.py` exactly).
- **MCP unavailable** — the Space must reach the MCP URL over HTTPS; if you use a custom `MCP_SERVER_URL`, confirm it is reachable from the internet.

After go-live, add your public Space URL here for evaluators:  
`https://huggingface.co/spaces/<your-username>/<space-name>`
