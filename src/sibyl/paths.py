"""Workspace locations that stay consistent across launch directories and upgrades."""

import os
import sys
from pathlib import Path


def _checkout_workspace() -> Path | None:
    """Keep the source checkout's existing workspace independent of the launch directory."""
    module = Path(__file__).resolve()
    root = module.parents[2]
    if (root / "src" / "sibyl" / "paths.py") == module and (root / "pyproject.toml").is_file():
        return root / ".sibyl"
    return None


def default_data_dir() -> Path:
    """Keep source workspaces; use per-user installed data unless ``SIBYL_DATA_DIR`` overrides it."""
    checkout = _checkout_workspace()
    if checkout is not None:
        return checkout
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Sibyl"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "Sibyl"
    base = Path(os.environ.get("XDG_DATA_HOME", ""))
    if not base.is_absolute():
        base = Path.home() / ".local" / "share"
    return base / "sibyl"
