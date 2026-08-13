"""Lap history: leaderboards per track, records per track+car, past sessions.

The game server keeps nothing, so the dashboard records what its own log parser
sees: every "New lap" line becomes a row in a SQLite file on /data. A session
starts whenever the server process starts — server_control calls
notify_server_start right after truncating the log — so one session is one
server run with whatever track was configured at that moment.

The recorder reads the log incrementally by offset. On its very first poll it
only positions itself at the end of the file: replaying what is already there
would double-count every lap a previous dashboard process stored.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("ACEVO_HISTORY_DB", "/data/history.db"))
CONFIG_PATH = Path(os.environ.get("ACEVO_DASHBOARD_CONFIG", "/data/server_launcher.json"))

_LINE_TIME = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  track TEXT NOT NULL DEFAULT '',
  mode TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS laps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  at TEXT NOT NULL,
  driver TEXT NOT NULL DEFAULT '',
  steam_id TEXT NOT NULL DEFAULT '',
  car TEXT NOT NULL DEFAULT '',
  lap_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_laps_session ON laps(session_id);
CREATE INDEX IF NOT EXISTS idx_laps_car ON laps(car, lap_ms);
"""

_lock = threading.Lock()
_state: dict = {"offset": None, "session_id": None, "cars": {}}


def reset_state() -> None:
    with _lock:
        _state.update(offset=None, session_id=None, cars={})


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _current_track() -> tuple[str, str]:
    try:
        from . import config_io

        form = config_io.load_saved(CONFIG_PATH)
        token = form["event"]["track"] or ""
        mode = "race" if "RACE_WEEKEND" in (form["event"]["type"] or "").upper() else "practice"
        return " ".join(token.split("|")[:2]), mode
    except Exception:  # noqa: BLE001 - history must never block a server start
        return "", ""


def notify_server_start() -> None:
    """Called by server_control right after it truncated the log."""
    track, mode = _current_track()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO sessions (started_at, track, mode) VALUES (datetime('now'), ?, ?)",
            (track, mode),
        )
        session_id = cursor.lastrowid
    with _lock:
        _state.update(offset=0, session_id=session_id, cars={})


def poll() -> int:
    """Read new log bytes, store any new laps. Returns the number of rows written."""
    # Late imports: live imports server_control, which imports this module.
    from . import live, server_control

    log = server_control.LOG_FILE
    try:
        size = log.stat().st_size
    except OSError:
        return 0

    with _lock:
        offset = _state["offset"]
        session_id = _state["session_id"]
        cars = dict(_state["cars"])

    if offset is None:
        with _lock:
            _state["offset"] = size
        return 0
    if size < offset:
        offset = 0
    if size == offset:
        return 0

    with open(log, "rb") as handle:
        handle.seek(offset)
        text = handle.read(size - offset).decode("utf-8", errors="replace")

    rows = []
    for line in text.splitlines():
        if (hit := live._CONNECT.search(line)) is not None:
            entry = cars.setdefault(live._key(hit.group(1)), {})
            entry["name"] = hit.group(2).strip()
            entry["steam_id"] = hit.group(3)
        elif (hit := live._CAR.search(line)) is not None:
            cars.setdefault(live._key(hit.group(2)), {})["car"] = hit.group(1)
        elif (hit := live._LAP.search(line)) is not None:
            lap_ms = live.lap_to_ms(hit.group(2))
            if lap_ms is None or session_id is None:
                continue
            info = cars.get(live._key(hit.group(1)), {})
            stamp = _LINE_TIME.match(line)
            at = stamp.group(1) if stamp else time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
            rows.append((session_id, at, info.get("name", ""), info.get("steam_id", ""), info.get("car", ""), lap_ms))

    if rows:
        with _connect() as conn:
            conn.executemany(
                "INSERT INTO laps (session_id, at, driver, steam_id, car, lap_ms) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
    with _lock:
        _state["offset"] = size
        _state["cars"] = cars
    return len(rows)


def snapshot_backup() -> Path:
    """Write a consistent copy next to the live DB.

    The host's weekly volume backup tars the file while it is being written to,
    which can catch a mid-transaction state. VACUUM INTO produces a clean
    snapshot, and the tar picks both up.
    """
    target = DB_PATH.with_name(DB_PATH.stem + "-backup.db")
    temp = target.with_suffix(".tmp")
    temp.unlink(missing_ok=True)
    with _connect() as conn:
        conn.execute("VACUUM INTO ?", (str(temp),))
    temp.replace(target)
    return target


def start_recorder(interval: float = 3.0, backup_every: float = 24 * 3600) -> threading.Thread:
    def loop() -> None:
        last_backup = 0.0
        while True:
            try:
                poll()
                if time.monotonic() - last_backup > backup_every:
                    snapshot_backup()
                    last_backup = time.monotonic()
            except Exception:  # noqa: BLE001 - the recorder must survive anything
                pass
            time.sleep(interval)

    thread = threading.Thread(target=loop, daemon=True, name="lap-recorder")
    thread.start()
    return thread


# --- queries -----------------------------------------------------------------


def leaderboard(track: str, car: str = "") -> list[dict]:
    """Each driver's personal best on a track, ranked. `car` narrows to one car."""
    query = """
        SELECT l.driver, l.steam_id, l.car, MIN(l.lap_ms) AS best_ms, l.at, COUNT(*) AS laps
        FROM laps l JOIN sessions s ON s.id = l.session_id
        WHERE l.lap_ms > 0 AND s.track LIKE ?
    """
    params: list = [f"%{track}%"]
    if car:
        query += " AND l.car LIKE ?"
        params.append(f"%{car}%")
    # Bare columns next to MIN() resolve to the winning row in SQLite, which is
    # exactly what puts the record car and date beside the record time.
    query += " GROUP BY COALESCE(NULLIF(l.steam_id, ''), l.driver) ORDER BY best_ms"
    with _connect() as conn:
        return [dict(row) for row in conn.execute(query, params)]


def bests(track: str = "", car: str = "") -> list[dict]:
    """The record holder for every track+car combination."""
    query = """
        SELECT s.track, l.car, l.driver, l.steam_id, MIN(l.lap_ms) AS best_ms, l.at
        FROM laps l JOIN sessions s ON s.id = l.session_id
        WHERE l.lap_ms > 0
    """
    params: list = []
    if track:
        query += " AND s.track LIKE ?"
        params.append(f"%{track}%")
    if car:
        query += " AND l.car LIKE ?"
        params.append(f"%{car}%")
    query += " GROUP BY s.track, l.car ORDER BY s.track, best_ms"
    with _connect() as conn:
        return [dict(row) for row in conn.execute(query, params)]


def sessions(limit: int = 50, include_empty: bool = False) -> list[dict]:
    having = "" if include_empty else "HAVING laps > 0"
    query = f"""
        SELECT s.id, s.started_at, s.track, s.mode,
               COUNT(l.id) AS laps,
               COUNT(DISTINCT COALESCE(NULLIF(l.steam_id, ''), l.driver)) AS drivers,
               MIN(l.lap_ms) AS best_ms
        FROM sessions s LEFT JOIN laps l ON l.session_id = s.id
        GROUP BY s.id {having}
        ORDER BY s.id DESC LIMIT ?
    """
    with _connect() as conn:
        return [dict(row) for row in conn.execute(query, (int(limit),))]


def session_detail(session_id: int) -> dict:
    with _connect() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if session is None:
            return {"error": f"session {session_id} not found"}
        standings = conn.execute(
            """
            SELECT driver, steam_id, car, COUNT(*) AS laps, MIN(lap_ms) AS best_ms
            FROM laps WHERE session_id = ? AND lap_ms > 0
            GROUP BY COALESCE(NULLIF(steam_id, ''), driver), car
            ORDER BY best_ms
            """,
            (session_id,),
        ).fetchall()
        laps = conn.execute(
            "SELECT at, driver, car, lap_ms FROM laps WHERE session_id = ? ORDER BY id LIMIT 500",
            (session_id,),
        ).fetchall()
    return {
        "session": dict(session),
        "standings": [dict(row) for row in standings],
        "laps": [dict(row) for row in laps],
    }
