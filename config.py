# config.py — load and validate environment variables at import time
import os
from dotenv import load_dotenv

load_dotenv()

# --- Required ---
CEREBRAS_API_KEY: str = os.getenv("CEREBRAS_API_KEY", "")

# --- Optional with defaults ---
CEREBRAS_MODEL: str = os.getenv("CEREBRAS_MODEL", "llama3.1-8b")

MCP_SERVER_URL: str = os.getenv(
    "MCP_SERVER_URL", "https://order-mcp-74afyau24q-uc.a.run.app/mcp"
)


def validate():
    """Validate required env vars. Raises ValueError with the missing key name."""
    if not CEREBRAS_API_KEY:
        raise ValueError("Missing required env var: CEREBRAS_API_KEY")


def get_model() -> str:
    """Return the effective Cerebras model name."""
    return CEREBRAS_MODEL
