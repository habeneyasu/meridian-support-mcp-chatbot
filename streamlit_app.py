"""
Hugging Face Streamlit Spaces often default to this filename (template demo).
Loads the real Meridian chatbot from app.py — do not edit app.py here.
"""
import importlib.util
from pathlib import Path

_app_path = Path(__file__).resolve().parent / "app.py"
_spec = importlib.util.spec_from_file_location("meridian_app", _app_path)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Cannot load {_app_path}")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
