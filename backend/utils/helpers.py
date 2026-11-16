import os
import re
from typing import Dict, Any


def load_env_file(filepath: str = ".env"):
    """
    Safely load key-value pairs from a .env file into os.environ without requiring external packages.
    """
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception:
        pass


def sanitize_sensitive_data(text: str) -> str:
    """
    Mask tokens, passwords, and sensitive keys from log strings.
    """
    if not text:
        return text
    # Mask github tokens (ghp_..., github_pat_...)
    text = re.sub(r"(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{50,})", r"[REDACTED_GITHUB_TOKEN]", text)
    # Mask OpenAI / API keys (sk-...)
    text = re.sub(r"(sk-[a-zA-Z0-9_\-]{20,})", r"[REDACTED_API_KEY]", text)
    # Mask basic auth in URLs (https://user:token@github.com)
    text = re.sub(r"(https?://[^:]+:)([^@]+)(@github\.com)", r"\1***\3", text)
    return text
