# api_secrets.py
# Loads API keys from .env file (via python-dotenv).

import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError(
        "Missing GEMINI_API_KEY. "
        "Set it in your .env file or environment variables. "
        "Run `python setup.py` to configure."
    )
