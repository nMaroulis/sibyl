"""Bounded current-process resource observations without inspecting other processes or secrets."""

import shutil
import threading
import time
from datetime import UTC, datetime

import psutil


class ProcessResources:
    """Read lightweight counters at most once per five seconds; CPU needs two observations.

    CPU is process CPU time divided by elapsed wall time (one busy CPU = 100%).
    These counters cover the Python API process, not Ollama, the browser or host
    uptime. Permissions/platform limitations produce explicit unavailable values.
    """

    def __init__(self, store, *, process=None, clock=time.monotonic):
        self.store, self.clock = store, clock
        try:
            self.process = process if process is not None else psutil.Process()
        except (psutil.Error, OSError):
            self.process = None
        self.started = clock()
        self.previous = self.cached = None
        self.lock = threading.Lock()

    def snapshot(self):
        """Inspect CPU, resident memory, threads, database files and free workspace-volume space."""
        with self.lock:
            now = self.clock()
            if self.cached and now - self.cached[0] < 5:
                return dict(self.cached[1])
            result = {
                "observed_at": datetime.now(UTC).isoformat(),
                "uptime_seconds": max(0, round(now - self.started, 1)),
                "cpu_percent": None,
                "sample_seconds": None,
                "rss_bytes": None,
                "threads": None,
                "database_bytes": None,
                "volume_free_bytes": None,
                "unavailable": [],
                "scope": "Current Python API process. CPU is measured between observations; one CPU is 100%. Other processes and external uptime are excluded.",
            }
            try:
                if self.process is None:
                    raise psutil.AccessDenied()
                with self.process.oneshot():
                    cpu = self.process.cpu_times()
                    cpu_seconds = cpu.user + cpu.system
                    result.update(
                        rss_bytes=self.process.memory_info().rss, threads=self.process.num_threads()
                    )
                if self.previous and now > self.previous[0] and cpu_seconds >= self.previous[1]:
                    seconds = now - self.previous[0]
                    result.update(
                        cpu_percent=round((cpu_seconds - self.previous[1]) / seconds * 100, 2),
                        sample_seconds=round(seconds, 3),
                    )
                self.previous = (now, cpu_seconds)
            except (psutil.Error, OSError):
                result["unavailable"].append("process_counters")
            try:
                result["database_bytes"] = self.store.path.stat().st_size
                wal = self.store.path.with_name(self.store.path.name + "-wal")
                if wal.exists():
                    result["database_bytes"] += wal.stat().st_size
            except OSError:
                result["unavailable"].append("database_size")
            try:
                result["volume_free_bytes"] = shutil.disk_usage(self.store.path.parent).free
            except OSError:
                result["unavailable"].append("volume_space")
            result["status"] = "partial" if result["unavailable"] else "observed"
            self.cached = (now, result)
            return dict(result)
