"""Load siren/.env (gitignored) into os.environ for the LIVE entrypoints.

Fills only variables not already set (setdefault), so a real exported env always
wins. Dependency-free (no python-dotenv). Deliberately NOT used by agent/demo.py,
which keeps env explicit so stub-vs-live is controllable for testing.
"""
from __future__ import annotations

import os


def load_local_env(path: str | None = None) -> None:
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            val = val.split("#", 1)[0].strip().strip('"').strip("'")  # drop inline comments/quotes
            os.environ.setdefault(key.strip(), val)
