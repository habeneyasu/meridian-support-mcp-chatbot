# config.py — load and validate environment variables at import time
import os
from dotenv import load_dotenv

load_dotenv()

# --- Required ---
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")

# --- Optional with defaults ---
_DEFAULT_MODELS = {
    "gemini": "gemini-1.5-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-20240307",
}

LLM_MODEL: str = os.getenv("LLM_MODEL", "")
MCP_SERVER_URL: str = os.getenv(
    "MCP_SERVER_URL", "https://order-mcp-74afyau24q-uc.a.run.app/mcp"
)


def validate():
    """Validate required env vars. Raises ValueError with the missing key name."""
    for key, value in [("LLM_PROVIDER", LLM_PROVIDER), ("LLM_API_KEY", LLM_API_KEY)]:
        if not value:
            raise ValueError(f"Missing required env var: {key}")

    if LLM_PROVIDER not in _DEFAULT_MODELS:
        raise ValueError(
            f"Invalid LLM_PROVIDER '{LLM_PROVIDER}'. Must be one of: {list(_DEFAULT_MODELS)}"
        )


def get_model() -> str:
    """Return the effective model name, falling back to the provider default."""
    return LLM_MODEL or _DEFAULT_MODELS.get(LLM_PROVIDER, "")
