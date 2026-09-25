"""Lightweight wall-time and process-memory profiling for pipeline stages."""
from __future__ import annotations

import json
import os
import resource
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable


def current_rss_bytes() -> int | None:
    """Best-effort current resident-set size without adding a dependency."""
    statm = Path("/proc/self/statm")
    try:
        resident_pages = int(statm.read_text().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def peak_rss_bytes() -> int | None:
    """Return process peak RSS in bytes on platforms supported by resource."""
    try:
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (AttributeError, OSError):
        return None
    # Linux reports KiB; macOS/BSD report bytes.
    return int(value if sys.platform == "darwin" else value * 1024)


class StageProfiler:
    """Aggregate repeated stage timings and memory observations."""

    def __init__(
        self,
        metadata: dict | None = None,
        clock: Callable[[], float] = time.perf_counter,
        rss_reader: Callable[[], int | None] = current_rss_bytes,
        peak_reader: Callable[[], int | None] = peak_rss_bytes,
    ):
        self.metadata = dict(metadata or {})
        self._clock = clock
        self._rss_reader = rss_reader
        self._peak_reader = peak_reader
        self._stages: dict[str, dict] = {}

    @contextmanager
    def stage(self, name: str):
        if not name:
            raise ValueError("stage name must be non-empty")
        started = self._clock()
        rss_before = self._rss_reader()
        peak_before = self._peak_reader()
        try:
            yield
        finally:
            elapsed = self._clock() - started
            rss_after = self._rss_reader()
            peak_after = self._peak_reader()
            row = self._stages.setdefault(
                name,
                {
                    "count": 0,
                    "wall_seconds": 0.0,
                    "max_call_seconds": 0.0,
                    "rss_start_bytes": rss_before,
                    "rss_end_bytes": rss_after,
                    "peak_rss_bytes": peak_after,
                },
            )
            row["count"] += 1
            row["wall_seconds"] += elapsed
            row["max_call_seconds"] = max(row["max_call_seconds"], elapsed)
            if row["rss_start_bytes"] is None:
                row["rss_start_bytes"] = rss_before
            row["rss_end_bytes"] = rss_after
            observed_peaks = [x for x in (row["peak_rss_bytes"], peak_before, peak_after) if x is not None]
            row["peak_rss_bytes"] = max(observed_peaks) if observed_peaks else None

    def snapshot(self) -> dict:
        stages = {}
        for name, row in self._stages.items():
            item = dict(row)
            item["wall_seconds"] = round(float(item["wall_seconds"]), 6)
            item["max_call_seconds"] = round(float(item["max_call_seconds"]), 6)
            start, end = item["rss_start_bytes"], item["rss_end_bytes"]
            item["rss_delta_bytes"] = None if start is None or end is None else int(end - start)
            stages[name] = item
        return {
            "schema_version": 1,
            "metadata": self.metadata,
            "stages": stages,
            "process_peak_rss_bytes": self._peak_reader(),
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(self.snapshot(), indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(path)
