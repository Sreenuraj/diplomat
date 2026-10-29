"""Load and save the JSON config. Writes are atomic; a corrupt file is backed up."""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

PROVIDERS = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "other": "",
}

# Sliders are stored as 0-100 (same scale as the UI). prompt.py maps them to 5 bands.
DEFAULTS: dict = {
    "provider": "ollama",
    "base_url": PROVIDERS["ollama"],
    "api_key": None,
    "model": "",  # empty = not chosen yet; pick one in Settings (or the CLI picks an installed one)
    "hotkey": "option+space",
    "default_preset": "slack_office",
    "slop_rules": True,
    "tone_open": False,
    "sliders": {
        "formality": 50,
        "warmth": 50,
        "directness": 50,
        "humor": 0,
        "sarcasm": 0,
        "enthusiasm": 30,
        "brevity": 50,
    },
}


def config_path() -> Path:
    override = os.environ.get("DIPLOMAT_CONFIG")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "Diplomat" / "config.json"


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    if not path.exists():
        return copy.deepcopy(DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config root must be an object")
    except (OSError, ValueError):
        backup = path.with_name(f"{path.stem}.corrupt-{int(time.time())}{path.suffix}")
        try:
            path.rename(backup)
        except OSError:
            pass
        return copy.deepcopy(DEFAULTS)
    return _merge(DEFAULTS, data)


def save(cfg: dict, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def is_local_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"} or host.endswith(".local")