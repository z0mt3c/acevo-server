"""Receiver for the server's result webhook.

AC EVO can POST session results to `SERVER_RESULTS_POST_URL`, but nothing
documents what it sends or when. So this stores every delivery verbatim and
echoes a summary into the server log, where it shows up in the dashboard's log
view — the point is to find out what the format is, not to interpret it yet.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

RESULTS_DIR = Path(os.environ.get("ACEVO_RESULTS_DIR", "/data/results"))
_MAX_ECHO = 2000


def _summarise(raw: bytes) -> str:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return f"{len(raw)} bytes, not JSON: {raw[:200]!r}"
    if isinstance(parsed, dict):
        return f"JSON object, keys: {sorted(parsed)}"
    if isinstance(parsed, list):
        return f"JSON array of {len(parsed)} items"
    return f"JSON {type(parsed).__name__}"


def record(raw: bytes, content_type: str = "", log_writer=None) -> dict:
    """Persist one delivery and return what was stored."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    suffix = "json" if "json" in (content_type or "").lower() else "txt"
    # Two deliveries can share a timestamp; without the counter the second one
    # would silently overwrite the first.
    target = RESULTS_DIR / f"webhook-{stamp}.{suffix}"
    counter = 1
    while target.exists():
        target = RESULTS_DIR / f"webhook-{stamp}-{counter}.{suffix}"
        counter += 1
    target.write_bytes(raw)

    summary = _summarise(raw)
    if log_writer is not None:
        log_writer(
            f"\n--- results webhook: {len(raw)} bytes, content-type={content_type or 'unset'} ---\n"
            f"{summary}\n{raw[:_MAX_ECHO].decode('utf-8', errors='replace')}\n"
        )
    return {"ok": True, "stored": str(target), "bytes": len(raw), "summary": summary}


def stored() -> list[dict]:
    if not RESULTS_DIR.exists():
        return []
    files = sorted(RESULTS_DIR.glob("*"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [{"name": path.name, "bytes": path.stat().st_size, "modified": path.stat().st_mtime} for path in files[:50]]
