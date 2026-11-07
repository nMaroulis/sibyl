"""Discover installed entry points; import only names explicitly enabled at startup."""

import hashlib
import importlib.metadata as metadata
import platform
import re

import numpy as np
import pandas as pd

from sibyl import __version__
from sibyl.forecasting.engine import fingerprint
from sibyl.strategies.plugins.contracts import StrategyPlugin

GROUP = "sibyl.strategies"


def source_digest(point):
    """Pin the installed distribution's Python sources, without returning source or paths."""
    files = sorted((p for p in point.dist.files or [] if str(p).endswith(".py")), key=str)
    if not files or len(files) > 256:
        raise ValueError("Plugin sources must be an inspectable bounded Python distribution.")
    digest, size = hashlib.sha256(), 0
    for file in files:
        data = point.dist.locate_file(file).read_bytes()
        size += len(data)
        if size > 2 * 1024 * 1024:
            raise ValueError("Plugin source exceeds the two-MiB inspection budget.")
        digest.update(str(file).encode())
        digest.update(b"\0")
        digest.update(data)
    return digest.hexdigest()


class PluginRegistry:
    """No plugin import when the allowlist is empty; loading errors stay sanitized."""

    def __init__(self, enabled=()):
        self.ready, self.items = {}, []
        points = {}
        for point in metadata.entry_points(group=GROUP):
            if re.fullmatch(r"[a-z][a-z0-9-]{0,63}", point.name):
                points.setdefault(point.name, []).append(point)
        for name in sorted(set(points) | set(enabled)):
            item = {"id": name, "status": "disabled", "error": None}
            self.items.append(item)
            if name not in enabled:
                continue
            candidates = points.get(name, [])
            if len(candidates) != 1:
                item.update(
                    status="unavailable",
                    error="Install exactly one entry point with this name, then restart Sibyl.",
                )
                continue
            point = candidates[0]
            try:
                factory = point.load()
                plugin = factory()
                if not isinstance(plugin, StrategyPlugin):
                    raise TypeError("Not a strategy plugin.")
                spec = plugin.spec
                from sibyl.strategies.plugins.contracts import PluginSpec

                spec = PluginSpec.model_validate(spec.model_dump())
                provenance = {
                    "distribution": point.dist.metadata["Name"],
                    "version": point.dist.version,
                    "entry_point": point.value,
                    "source_digest": source_digest(point),
                    "sibyl_version": __version__,
                    "python": platform.python_version(),
                    "numpy": np.__version__,
                    "pandas": pd.__version__,
                }
                revision = fingerprint({"spec": spec.model_dump(), "implementation": provenance})
                self.ready[name] = (factory, spec, point, provenance, revision)
                item.update(
                    status="ready", spec=spec.model_dump(), implementation=provenance, revision=revision
                )
            except Exception:
                item.update(
                    status="unavailable",
                    error="This enabled plugin could not load a valid bounded manifest/source distribution. Check its installation and restart Sibyl.",
                )

    def catalog(self):
        return {
            "items": self.items,
            "entry_point_group": GROUP,
            "research_only": True,
            "note": "Only explicitly enabled installed Python packages run. Plugins have backend process privileges; install only code you trust. No code upload or live/paper execution is provided.",
        }

    def resolve(self, name, revision):
        saved = self.ready.get(name)
        if saved is None:
            raise ValueError("Enable and install this custom strategy, then restart Sibyl.")
        factory, spec, point, provenance, current = saved
        try:
            unchanged = source_digest(point) == provenance["source_digest"]
        except (OSError, ValueError):
            unchanged = False
        if revision != current or not unchanged:
            raise ValueError(
                "The plugin implementation changed. Restart Sibyl and review its current revision; old results cannot silently use new code."
            )
        return saved
