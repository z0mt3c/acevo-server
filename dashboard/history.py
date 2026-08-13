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

import json
import os
import re
import sqlite3
import threading
import time
import urllib.request
from pathlib import Path

DB_PATH = Path(os.environ.get("ACEVO_HISTORY_DB", "/data/history.db"))
CONFIG_PATH = Path(os.environ.get("ACEVO_DASHBOARD_CONFIG", "/data/server_launcher.json"))
# When set, a lap that takes P1 is POSTed here — n8n turns that into a Discord post.
WEBHOOK_URL = os.environ.get("ACEVO_LEADER_WEBHOOK", "")
# n8n's /webhook/* routes are public — the shared secret is what lets the flow
# reject anyone else who finds the URL.
WEBHOOK_TOKEN = os.environ.get("ACEVO_LEADER_WEBHOOK_TOKEN", "")

_LINE_TIME = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
# "TimeAttackRemote Practice created" — the only phase marker the log offers.
_PHASE = re.compile(r"Remote (Practice|Qualify|Warmup|Race) created")

# The log names cars in its own namespace (ks_ferrari_296_gt3), which matches
# neither the metadata's internal_name (preset_296gt3_mech_1) nor its display
# name — so the class has to come out of the log name itself. Order matters:
# a GT3 Cup is a one-make cup car, not a GT3.
_CLASS_PATTERNS = (
    ("cup", re.compile(r"cup|trofeo|challenge|academy|clubsport")),
    ("formula", re.compile(r"f2004|sf_?-?25|formula|_f1\b")),
    ("gt3", re.compile(r"gt3")),
    ("gt2", re.compile(r"gt2")),
    ("gt4", re.compile(r"gt4")),
)
_CLASS_LABELS = {"cup": "Cup", "formula": "Formula", "gt3": "GT3", "gt2": "GT2", "gt4": "GT4"}


def car_class(car_name: str) -> str:
    lowered = (car_name or "").lower()
    for name, pattern in _CLASS_PATTERNS:
        if pattern.search(lowered):
            return name
    return ""


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
_state: dict = {"offset": None, "session_id": None, "cars": {}, "phase": ""}


def reset_state() -> None:
    with _lock:
        _state.update(offset=None, session_id=None, cars={}, phase="")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    if not any(row[1] == "phase" for row in conn.execute("PRAGMA table_info(laps)")):
        conn.execute("ALTER TABLE laps ADD COLUMN phase TEXT NOT NULL DEFAULT ''")
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
        _state.update(offset=0, session_id=session_id, cars={}, phase="")


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
        phase = _state["phase"]

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
        if (hit := _PHASE.search(line)) is not None:
            phase = hit.group(1).lower()
        elif (hit := live._CONNECT.search(line)) is not None:
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
            rows.append(
                (session_id, at, info.get("name", ""), info.get("steam_id", ""), info.get("car", ""), lap_ms, phase)
            )

    events = _detect_records(session_id, rows) if rows and WEBHOOK_URL else []
    if rows:
        with _connect() as conn:
            conn.executemany(
                "INSERT INTO laps (session_id, at, driver, steam_id, car, lap_ms, phase) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
    for event in events:
        _post_webhook(event)
    with _lock:
        _state["offset"] = size
        _state["cars"] = cars
        _state["phase"] = phase
    return len(rows)


def _format_lap(lap_ms: int | None) -> str:
    if not lap_ms:
        return ""
    return f"{lap_ms // 60000}:{(lap_ms % 60000) // 1000:02d}.{lap_ms % 1000:03d}"


def _car_label(internal: str) -> str:
    try:
        from . import metadata

        for car in metadata.build_metadata()["cars"]:
            if car["internal_name"] == internal:
                return car["display_name"]
    except Exception:  # noqa: BLE001 - a label is nice to have, not load-bearing
        pass
    # Log car names (ks_maserati_mc20_gt2) match no metadata entry — prettify.
    words = (internal or "").removeprefix("ks_").split("_")
    return " ".join(w.upper() if (len(w) <= 3 or any(c.isdigit() for c in w)) else w.capitalize() for w in words)


def _detect_records(session_id: int, rows: list[tuple]) -> list[dict]:
    """Compare the new laps against the stored bests BEFORE they are inserted.

    Tiers, highest wins: track record (fastest overall on the track), class
    record (fastest of the car's class), car record (fastest in this exact car).
    """
    with _connect() as conn:
        session = conn.execute("SELECT track FROM sessions WHERE id = ?", (session_id,)).fetchone()
        track = session["track"] if session else ""
        if not track:
            return []

        def stored_best(cars_in: list[str] | None = None) -> tuple[int | None, str]:
            query = (
                "SELECT MIN(l.lap_ms) AS ms, l.driver AS driver FROM laps l "
                "JOIN sessions s ON s.id = l.session_id WHERE l.lap_ms > 0 AND s.track = ?"
            )
            params: list = [track]
            if cars_in is not None:
                if not cars_in:
                    return (None, "")
                query += f" AND l.car IN ({','.join('?' * len(cars_in))})"
                params.extend(cars_in)
            best = conn.execute(query, params).fetchone()
            return (best["ms"], best["driver"] or "") if best and best["ms"] else (None, "")

        known_cars = [
            row["car"]
            for row in conn.execute(
                "SELECT DISTINCT l.car FROM laps l JOIN sessions s ON s.id = l.session_id WHERE s.track = ?",
                (track,),
            )
        ]
        overall = stored_best()
        new_cars = {row[4] for row in rows}
        car_bests = {car: stored_best([car]) for car in new_cars}
        class_bests = {}
        for car in new_cars:
            cls = car_class(car)
            if cls and cls not in class_bests:
                class_bests[cls] = stored_best([c for c in set(known_cars) | new_cars if car_class(c) == cls])

    events: list[dict] = []
    overall_ms, overall_driver = overall
    for _sid, _at, driver, _steam_id, car, lap_ms, phase in rows:
        cls = car_class(car)
        base = {
            "track": track,
            "car": _car_label(car),
            "car_class": _CLASS_LABELS.get(cls, ""),
            "phase": phase,
            "driver": driver or "Unknown",
            "lap_ms": lap_ms,
            "lap_time": _format_lap(lap_ms),
        }
        if overall_ms is None or lap_ms < overall_ms:
            events.append(
                {
                    "event": "track_record",
                    **base,
                    "previous_driver": overall_driver,
                    "previous_time": _format_lap(overall_ms),
                }
            )
            overall_ms, overall_driver = lap_ms, driver
            if cls:
                class_bests[cls] = (lap_ms, driver)
            car_bests[car] = (lap_ms, driver)
            continue
        if cls:
            class_ms, class_driver = class_bests.get(cls, (None, ""))
            if class_ms is None or lap_ms < class_ms:
                events.append(
                    {
                        "event": "class_record",
                        **base,
                        "previous_driver": class_driver,
                        "previous_time": _format_lap(class_ms),
                    }
                )
                class_bests[cls] = (lap_ms, driver)
                car_bests[car] = (lap_ms, driver)
                continue
        car_ms, car_driver = car_bests.get(car, (None, ""))
        if car_ms is None or lap_ms < car_ms:
            events.append(
                {"event": "car_record", **base, "previous_driver": car_driver, "previous_time": _format_lap(car_ms)}
            )
            car_bests[car] = (lap_ms, driver)
    return events


def _post_webhook(payload: dict) -> None:
    """Fire and forget: a slow or dead n8n must never stall the recorder."""
    if not WEBHOOK_URL:
        return

    def send() -> None:
        try:
            headers = {"Content-Type": "application/json"}
            if WEBHOOK_TOKEN:
                headers["X-Acevo-Token"] = WEBHOOK_TOKEN
            request = urllib.request.Request(
                WEBHOOK_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            urllib.request.urlopen(request, timeout=5).close()
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=send, daemon=True, name="leader-webhook").start()


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


def leaderboard(track: str, car: str = "", car_cls: str = "", phase: str = "") -> list[dict]:
    """Each driver's personal best on a track, ranked. Filters: exact-ish car
    name, car class (gt3, gt2, ...) and session phase (practice, qualify, race)."""
    with _connect() as conn:
        query = """
            SELECT l.driver, l.steam_id, l.car, MIN(l.lap_ms) AS best_ms, l.at, l.phase, COUNT(*) AS laps
            FROM laps l JOIN sessions s ON s.id = l.session_id
            WHERE l.lap_ms > 0 AND s.track LIKE ?
        """
        params: list = [f"%{track}%"]
        if car:
            query += " AND l.car LIKE ?"
            params.append(f"%{car}%")
        if car_cls:
            cars_in = [
                row["car"]
                for row in conn.execute("SELECT DISTINCT car FROM laps")
                if car_class(row["car"]) == car_cls.lower()
            ]
            if not cars_in:
                return []
            query += f" AND l.car IN ({','.join('?' * len(cars_in))})"
            params.extend(cars_in)
        if phase:
            query += " AND l.phase = ?"
            params.append(phase.lower())
        # Bare columns next to MIN() resolve to the winning row in SQLite, which is
        # exactly what puts the record car and date beside the record time.
        query += " GROUP BY COALESCE(NULLIF(l.steam_id, ''), l.driver) ORDER BY best_ms"
        rows = [dict(row) for row in conn.execute(query, params)]
    for row in rows:
        row["car_class"] = _CLASS_LABELS.get(car_class(row["car"]), "")
    return rows


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
        rows = [dict(row) for row in conn.execute(query, params)]
    for row in rows:
        row["car_class"] = _CLASS_LABELS.get(car_class(row["car"]), "")
    return rows


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
            "SELECT at, driver, car, lap_ms, phase FROM laps WHERE session_id = ? ORDER BY id LIMIT 500",
            (session_id,),
        ).fetchall()
    return {
        "session": dict(session),
        "standings": [dict(row) for row in standings],
        "laps": [dict(row) for row in laps],
    }
