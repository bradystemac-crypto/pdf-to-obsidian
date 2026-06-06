# config.py
# Loads project settings from .env file (via python-dotenv) with sensible defaults.

import os
from dotenv import load_dotenv

# Load .env file from the project root
load_dotenv()

# ---------------------------------------------------------------------------
# Paths (derived from project structure, not from .env)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# ---------------------------------------------------------------------------
# Obsidian vault path (required – must be set in .env)
# ---------------------------------------------------------------------------
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH")
if not OBSIDIAN_VAULT_PATH:
    raise ValueError(
        "Missing OBSIDIAN_VAULT_PATH. "
        "Set it in your .env file or environment variables. "
        "Run `python setup.py` to configure."
    )

# ---------------------------------------------------------------------------
# AI model configuration
# ---------------------------------------------------------------------------
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

# ---------------------------------------------------------------------------
# Retry / resilience settings
# ---------------------------------------------------------------------------
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
BASE_SLEEP_SECONDS = int(os.getenv("BASE_SLEEP_SECONDS", "2"))

# ---------------------------------------------------------------------------
# PDF rendering quality (dots per inch)
# ---------------------------------------------------------------------------
PDF_DPI = int(os.getenv("PDF_DPI", "300"))