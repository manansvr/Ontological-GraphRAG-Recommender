"""Where the RL model file lives: one rule shared by sr8-mcp and ollama-mcp.

Both programs load this file by path (importlib), so they always resolve RL_MODEL_PATH
the same way and therefore read and write the same .rl-model.json:

- unset or empty: thesis-extension/.rl-model.json
- relative: resolved against the thesis-extension folder, not the current directory
- absolute (or starting with ~): used as given
"""

import os
from pathlib import Path
from typing import Mapping, Optional

EXTENSION_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_FILE = ".rl-model.json"


def resolve_rl_model_path(env: Optional[Mapping[str, str]] = None) -> Path:
    """Return the RL model file path from RL_MODEL_PATH (in env, default os.environ)."""
    value = (os.environ if env is None else env).get("RL_MODEL_PATH") or DEFAULT_MODEL_FILE
    path = Path(value).expanduser()
    return path if path.is_absolute() else EXTENSION_DIR / path
