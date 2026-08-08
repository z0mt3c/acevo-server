"""Live session state: who is on track, in what, and how fast.

The dedicated server offers no API for this. Its HTTP listing port only reports a
client count, so driver identity, car and lap times have to be reconstructed from
the server log. Parsing is deliberately forgiving — anything that does not match
is skipped, because a log format change must degrade the view, not break it.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from . import server_control

LISTING_URL = os.environ.get("ACEVO_LISTING_URL", "http://127.0.0.1:8080/")
_MAX_LOG_READ = 2 * 1024 * 1024

# "connecting gamecar <carId> (Max Bearman | 76561198200085390)"
_CONNECT = re.compile(r"connecting gamecar ([0-9a-fA-F-]+) \(([^|]+?) \| (\d+)\)")
# "76561198200085390 connected (true) on car ks_maserati_mc20_gt2, with new carId <carId>"
_CAR = re.compile(r"connected \([a-z]+\) on car ([\w.-]+), with new carId ([0-9a-fA-F-]+)")
# "Car [<carId>] #20 for driver Max Bearman [76561198200085390]"
_NUMBER = re.compile(r"Car \[([0-9a-fA-F-]+)\] #(\d+) for driver")
# "New lap carId <carId>: 01:36.369"
_LAP = re.compile(r"New lap carId ([0-9a-fA-F-]+): (\d+:\d+\.\d+)")
# "Removing disconnected remote_car <carId>" — dashed here, undashed on connect.
_DISCONNECT = re.compile(r"Removing disconnected remote_car ([0-9a-fA-F-]+)")
_PLAYERS = re.compile(r"Server updated: (\d+) players")
_LAP_TIME = re.compile(r"^(\d+):(\d+)\.(\d+)$")


def lap_to_ms(value: str) -> int | None:
    match = _LAP_TIME.match((value or "").strip())
    if not match:
        return None
    minutes, seconds, millis = (int(part) for part in match.groups())
    return minutes * 60000 + seconds * 1000 + millis


def _key(car_id: str) -> str:
    """Car ids appear dashed in some lines and undashed in others."""
    return car_id.replace("-", "").lower()


def parse_log(text: str) -> dict:
    drivers: dict[str, dict] = {}
    players = 0

    def entry(car_id: str) -> dict:
        return drivers.setdefault(
            _key(car_id),
            {
                "car_id": car_id,
                "name": "",
                "steam_id": "",
                "car": "",
                "number": None,
                "laps": 0,
                "last_lap_ms": None,
                "best_lap_ms": None,
                "connected": True,
            },
        )

    for line in text.splitlines():
        if (hit := _CONNECT.search(line)) is not None:
            driver = entry(hit.group(1))
            driver.update(name=hit.group(2).strip(), steam_id=hit.group(3), connected=True)
        elif (hit := _CAR.search(line)) is not None:
            entry(hit.group(2))["car"] = hit.group(1)
        elif (hit := _NUMBER.search(line)) is not None:
            entry(hit.group(1))["number"] = int(hit.group(2))
        elif (hit := _LAP.search(line)) is not None:
            driver = entry(hit.group(1))
            lap_ms = lap_to_ms(hit.group(2))
            if lap_ms is not None:
                driver["laps"] += 1
                driver["last_lap_ms"] = lap_ms
                if driver["best_lap_ms"] is None or lap_ms < driver["best_lap_ms"]:
                    driver["best_lap_ms"] = lap_ms
        elif (hit := _DISCONNECT.search(line)) is not None:
            entry(hit.group(1))["connected"] = False
        elif (hit := _PLAYERS.search(line)) is not None:
            players = int(hit.group(1))

    ordered = sorted(
        drivers.values(),
        key=lambda d: (not d["connected"], d["best_lap_ms"] is None, d["best_lap_ms"] or 0),
    )
    return {"drivers": ordered, "players": players}


def fetch_listing() -> dict | None:
    """The server's own listing endpoint — the only structured source it offers."""
    try:
        with urllib.request.urlopen(LISTING_URL, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def _read_log_tail() -> str:
    log_file = server_control.LOG_FILE
    try:
        if not log_file.exists():
            return ""
        size = log_file.stat().st_size
        with open(log_file, "rb") as handle:
            if size > _MAX_LOG_READ:
                handle.seek(size - _MAX_LOG_READ)
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def snapshot() -> dict:
    parsed = parse_log(_read_log_tail())
    listing = fetch_listing()
    return {
        "drivers": parsed["drivers"],
        "players": parsed["players"],
        "clients": listing.get("clients") if isinstance(listing, dict) else None,
        "listing": listing,
    }
