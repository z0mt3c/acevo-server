"""MCP endpoint, served by the dashboard itself.

Streamable HTTP is JSON-RPC over POST, so it needs no framework: the transport
is implemented here against the standard library, matching the rest of the
dashboard. Tools call the same modules the HTTP API does — no loopback requests.

Exposed at POST /mcp. Stateless: every request stands on its own, which is what
n8n's MCP client expects when it opens a fresh connection per tool call.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from . import config_io, history, live, metadata, results, server_control

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "acevo", "version": "1.0.0"}

_TOOLS: list[dict] = []
_HANDLERS: dict[str, Callable[..., Any]] = {}


def tool(name: str, description: str, schema: dict | None = None):
    def register(func):
        _TOOLS.append(
            {
                "name": name,
                "description": description,
                "inputSchema": schema or {"type": "object", "properties": {}},
            }
        )
        _HANDLERS[name] = func
        return func

    return register


def _string(name: str, description: str) -> dict:
    return {"type": "string", "description": description}


def _apply_flag() -> dict:
    return {
        "type": "boolean",
        "description": "true also restarts the server, which disconnects everyone on track",
        "default": False,
    }


def _config_path():
    from .app import DEFAULT_CONFIG_PATH

    return DEFAULT_CONFIG_PATH


def _form() -> dict:
    import os

    return config_io.effective_runtime_form(_config_path(), os.environ)


def _save(form: dict, apply: bool) -> dict:
    saved = config_io.save(form, _config_path())
    out = {"saved": True, "warnings": saved.get("warnings", [])}
    if apply:
        out["restart"] = server_control.restart()
    return out


def _tracks(form: dict) -> list[dict]:
    meta = metadata.build_metadata()
    race = "RACE_WEEKEND" in (form.get("event", {}).get("type") or "").upper()
    return meta["tracks"]["race_weekend" if race else "practice"]


# --- reading -----------------------------------------------------------------


@tool("status", "Server state, who is on track, in what car and how fast.")
def _status() -> dict:
    return {"status": server_control.status(), "live": live.snapshot()}


@tool("get_config", "The current race configuration: server, event, sessions, car count.")
def _get_config() -> dict:
    form = _form()
    cars = form.get("cars", [])
    return {
        "server": form.get("server"),
        "event": form.get("event"),
        "sessions": form.get("sessions"),
        "cars_selected": sum(1 for car in cars if car.get("is_selected")),
        "cars_total": len(cars),
    }


@tool(
    "list_tracks",
    "Tracks available in the current mode. Practice and race weekend differ — "
    "Nürburgring Touristenfahrten for instance only exists as a practice event.",
    {"type": "object", "properties": {"search": _string("search", "optional name filter")}},
)
def _list_tracks(search: str = "") -> dict:
    form = _form()
    needle = (search or "").strip().lower()
    names = [t["display"] for t in _tracks(form) if not needle or needle in t["display"].lower()]
    race = "RACE_WEEKEND" in (form["event"]["type"] or "").upper()
    return {"mode": "race weekend" if race else "practice", "count": len(names), "tracks": names}


@tool(
    "list_cars",
    "Cars with performance index, category and their ballast.",
    {
        "type": "object",
        "properties": {
            "only_selected": {"type": "boolean", "default": False},
            "search": _string("search", "optional name filter"),
        },
    },
)
def _list_cars(only_selected: bool = False, search: str = "") -> dict:
    meta = metadata.build_metadata()
    chosen = {car["name"]: car for car in _form().get("cars", [])}
    needle = (search or "").strip().lower()
    out = []
    for car in meta["cars"]:
        entry = chosen.get(car["internal_name"], {})
        if only_selected and not entry.get("is_selected"):
            continue
        if needle and needle not in car["display_name"].lower():
            continue
        out.append(
            {
                "name": car["display_name"],
                "pi": car["pi"],
                "category": f"{car['type']}/{car['era']}/{car['engine']}",
                "selected": bool(entry.get("is_selected")),
                "ballast": entry.get("ballast", 0),
                "restrictor": entry.get("restrictor", 0),
            }
        )
    return {"count": len(out), "cars": out}


@tool(
    "logs",
    "Recent server log lines, optionally filtered.",
    {
        "type": "object",
        "properties": {
            "tail": {"type": "integer", "default": 100},
            "contains": _string("contains", "only lines containing this text"),
        },
    },
)
def _logs(tail: int = 100, contains: str = "") -> dict:
    lines = server_control.logs(tail=int(tail)).get("lines", "").split("\n")
    if contains:
        lines = [line for line in lines if contains.lower() in line.lower()]
    return {"count": len(lines), "lines": "\n".join(lines)}


@tool("list_profiles", "Saved configuration profiles.")
def _list_profiles() -> dict:
    return {"profiles": config_io.list_profiles(_config_path())}


@tool("list_results", "Result deliveries the server posted to the dashboard webhook.")
def _list_results() -> dict:
    return {"deliveries": results.stored()}


def _car_names() -> dict:
    return {car["internal_name"]: car["display_name"] for car in metadata.build_metadata()["cars"]}


@tool(
    "leaderboard",
    "Ranked personal bests per driver on one track — the leaderboard. Optionally "
    "narrowed to a single car. Times come from the recorded lap history.",
    {
        "type": "object",
        "properties": {
            "track": _string("track", "track name or part of it, e.g. 'Laguna' or 'Nordschleife'"),
            "car": _string("car", "optional car filter, name or part of it"),
        },
        "required": ["track"],
    },
)
def _leaderboard(track: str, car: str = "") -> dict:
    rows = history.leaderboard(track, car)
    names = _car_names()
    for row in rows:
        row["car"] = names.get(row["car"], row["car"])
    return {"track": track, "count": len(rows), "leaderboard": rows}


@tool(
    "best_times",
    "The record holder for every track+car combination, with driver name and date.",
    {
        "type": "object",
        "properties": {
            "track": _string("track", "optional track filter"),
            "car": _string("car", "optional car filter"),
        },
    },
)
def _best_times(track: str = "", car: str = "") -> dict:
    rows = history.bests(track, car)
    names = _car_names()
    for row in rows:
        row["car"] = names.get(row["car"], row["car"])
    return {"count": len(rows), "bests": rows}


@tool(
    "session_history",
    "Past sessions in which someone actually drove: when, which track, how many "
    "drivers and laps. Use session_detail for one session's standings.",
    {"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}},
)
def _session_history(limit: int = 20) -> dict:
    return {"sessions": history.sessions(limit=int(limit))}


@tool(
    "session_detail",
    "One session's standings (best lap per driver and car) and its laps.",
    {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
)
def _session_detail(id: int) -> dict:
    detail = history.session_detail(int(id))
    if "standings" in detail:
        names = _car_names()
        for row in detail["standings"]:
            row["car"] = names.get(row["car"], row["car"])
    return detail


# --- changing ----------------------------------------------------------------


@tool(
    "set_track",
    "Pick a track by (partial) name, e.g. 'Laguna' or 'Nordschleife'. Also caps the "
    "slot count at the track's pit limit.",
    {
        "type": "object",
        "properties": {"track": _string("track", "full or partial track name"), "apply": _apply_flag()},
        "required": ["track"],
    },
)
def _set_track(track: str, apply: bool = False) -> dict:
    form = _form()
    needle = (track or "").strip().lower()
    candidates = [t for t in _tracks(form) if needle in t["display"].lower()]
    if not candidates:
        return {"error": f"no track matches {track!r} in this mode", "hint": "use list_tracks"}
    exact = [t for t in candidates if t["display"].lower().startswith(needle)]
    chosen = (exact or candidates)[0]
    form["event"]["track"] = chosen["token"]
    limit = chosen.get("max_pit_slot", 50)
    form["server"]["max_players_limit"] = limit
    if form["server"].get("max_players", 0) > limit:
        form["server"]["max_players"] = limit
    return {"track": chosen["display"], "pit_limit": limit, **_save(form, apply)}


@tool(
    "set_mode",
    "Switch between 'practice' and 'race' (race weekend). Keeps the same circuit where "
    "it exists in the target mode and fills in session lengths if a race weekend would "
    "otherwise have nothing to drive.",
    {
        "type": "object",
        "properties": {"mode": _string("mode", "'practice' or 'race'"), "apply": _apply_flag()},
        "required": ["mode"],
    },
)
def _set_mode(mode: str, apply: bool = False) -> dict:
    form = _form()
    race = (mode or "").strip().lower().startswith("race")
    form["event"]["type"] = "GameModeType_RACE_WEEKEND" if race else "GameModeType_PRACTICE"

    previous = form["event"]["track"]
    target = _tracks(form)
    identity = "|".join(previous.split("|")[:2])
    match = next((t for t in target if "|".join(t["token"].split("|")[:2]) == identity), None)
    chosen = match or target[0]
    form["event"]["track"] = chosen["token"]

    if race and not form["sessions"]["race"]["length_sec"] and not form["sessions"]["qualify"]["length_sec"]:
        for name, seconds in (("practice", 1800), ("qualify", 900), ("warmup", 300), ("race", 2700)):
            form["sessions"][name]["length_sec"] = seconds

    return {
        "mode": "race weekend" if race else "practice",
        "track": chosen["display"],
        "track_kept": bool(match),
        **_save(form, apply),
    }


@tool(
    "set_session",
    "Set the length of 'practice', 'qualify', 'warmup' or 'race' in minutes.",
    {
        "type": "object",
        "properties": {
            "session": _string("session", "practice, qualify, warmup or race"),
            "minutes": {"type": "integer"},
            "apply": _apply_flag(),
        },
        "required": ["session", "minutes"],
    },
)
def _set_session(session: str, minutes: int, apply: bool = False) -> dict:
    form = _form()
    key = (session or "").strip().lower()
    if key not in form.get("sessions", {}):
        return {"error": f"unknown session {session!r}", "known": sorted(form.get("sessions", {}))}
    form["sessions"][key]["length_sec"] = max(0, int(minutes) * 60)
    return {"session": key, "minutes": int(minutes), **_save(form, apply)}


@tool(
    "set_server_options",
    "Change the public server name, the slot count or the weather. Empty or zero values stay untouched.",
    {
        "type": "object",
        "properties": {
            "name": _string("name", "public server name"),
            "max_players": {"type": "integer", "default": 0},
            "weather": _string("weather", "e.g. Clear, Rain, Overcast"),
            "apply": _apply_flag(),
        },
    },
)
def _set_server_options(name: str = "", max_players: int = 0, weather: str = "", apply: bool = False) -> dict:
    form = _form()
    if name:
        form["server"]["server_name"] = name
    if max_players:
        limit = form["server"].get("max_players_limit", 50)
        form["server"]["max_players"] = min(int(max_players), limit)
    if weather:
        options = metadata.build_metadata()["enums"]["weather"]
        hit = next((o for o in options if weather.strip().lower() in o["label"].lower()), None)
        if not hit:
            return {"error": f"unknown weather {weather!r}", "known": [o["label"] for o in options]}
        form["event"]["weather"] = hit["value"]
    return {"server": form["server"]["server_name"], **_save(form, apply)}


def _class_rules() -> dict:
    def race(car):
        return car["type"] == "race"

    return {
        "all": lambda car: True,
        "none": lambda car: False,
        "gt3": lambda car: race(car) and "GT3" in car["display_name"] and "GT3 Cup" not in car["display_name"],
        "gt2": lambda car: race(car) and "GT2" in car["display_name"],
        "gt4": lambda car: race(car) and "GT4" in car["display_name"],
        "formula": lambda car: race(car) and any(k in car["display_name"] for k in ("SF-25", "F2004", "Formula")),
        "cup": lambda car: race(car) and any(k in car["display_name"] for k in ("Cup", "Challenge", "Trofeo")),
        "race": race,
        "road": lambda car: car["type"] == "road",
        "track": lambda car: car["type"] == "track",
        "vintage": lambda car: car["era"] == "vintage",
        "electric": lambda car: car["engine"] == "ev",
    }


@tool(
    "select_cars",
    "Choose the car field: a class (gt3, gt2, gt4, formula, cup, race, road, track, "
    "vintage, electric, all, none) or a comma-separated list of name fragments.",
    {
        "type": "object",
        "properties": {
            "cars": _string("cars", "class name or comma-separated name fragments"),
            "mode": _string("mode", "'only' replaces the selection, 'add' extends it"),
            "apply": _apply_flag(),
        },
        "required": ["cars"],
    },
)
def _select_cars(cars: str, mode: str = "only", apply: bool = False) -> dict:
    meta = metadata.build_metadata()
    form = _form()
    by_name = {car["internal_name"]: car for car in meta["cars"]}
    wanted = (cars or "").strip().lower()
    rules = _class_rules()

    if wanted in rules:
        matches = rules[wanted]
    else:
        fragments = [part.strip().lower() for part in cars.split(",") if part.strip()]

        def matches(car):
            return any(part in car["display_name"].lower() for part in fragments)

    count = 0
    for entry in form["cars"]:
        car = by_name.get(entry["name"])
        hit = bool(car and matches(car))
        if (mode or "").strip().lower() == "add":
            if hit:
                entry["is_selected"] = True
        else:
            entry["is_selected"] = hit
        count += 1 if entry["is_selected"] else 0
    if count == 0 and wanted != "none":
        return {"error": f"{cars!r} matched no car", "hint": "use list_cars"}
    return {"selected": count, **_save(form, apply)}


@tool(
    "balance_by_pi",
    "Ballast the selected cars in proportion to how far their performance index sits "
    "above the slowest one. Ballast only removes performance, so the slowest car is the "
    "target. The factor is a starting point, not physics — say so and verify on track.",
    {
        "type": "object",
        "properties": {"per_pi_point": {"type": "integer", "default": 10}, "apply": _apply_flag()},
    },
)
def _balance_by_pi(per_pi_point: int = 10, apply: bool = False) -> dict:
    meta = metadata.build_metadata()
    form = _form()
    by_name = {car["internal_name"]: car for car in meta["cars"]}
    selected = [(e, by_name[e["name"]]) for e in form["cars"] if e.get("is_selected") and e["name"] in by_name]
    if len(selected) < 2:
        return {"error": "select at least two cars first"}
    slowest = min(car["pi"] for _entry, car in selected)
    applied = []
    for entry, car in selected:
        entry["ballast"] = round((car["pi"] - slowest) * per_pi_point)
        applied.append({"car": car["display_name"], "pi": car["pi"], "ballast": entry["ballast"]})
    return {"target_pi": slowest, "cars": applied, **_save(form, apply)}


@tool(
    "apply_profile",
    "Load a saved profile into the live configuration.",
    {
        "type": "object",
        "properties": {"name": _string("name", "profile name"), "apply": _apply_flag()},
        "required": ["name"],
    },
)
def _apply_profile(name: str, apply: bool = False) -> dict:
    form = config_io.load_profile(name, _config_path())
    if form is None:
        return {"error": f"profile {name!r} not found"}
    return {"profile": name, **_save(form, apply)}


@tool(
    "save_profile",
    "Store the current configuration as a profile.",
    {"type": "object", "properties": {"name": _string("name", "profile name")}, "required": ["name"]},
)
def _save_profile(name: str) -> dict:
    return config_io.save_profile(name, _form(), _config_path())


@tool(
    "control",
    "Run a server action: start, stop, restart or update. 'update' pulls a new build via "
    "SteamCMD and restarts. All of these disconnect anyone on track except 'start'.",
    {
        "type": "object",
        "properties": {"action": _string("action", "start, stop, restart or update")},
        "required": ["action"],
    },
)
def _control(action: str) -> dict:
    verb = (action or "").strip().lower()
    actions = {
        "start": server_control.start,
        "stop": server_control.stop,
        "restart": server_control.restart,
        "update": server_control.update,
    }
    if verb not in actions:
        return {"error": f"unknown action {action!r}", "known": sorted(actions)}
    return actions[verb]()


# --- JSON-RPC ----------------------------------------------------------------


def _result(request_id, payload) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(request: dict) -> dict | None:
    """One JSON-RPC request in, one response out. None means "notification, stay quiet"."""
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": _TOOLS})
    if method == "tools/call":
        name = params.get("name")
        handler = _HANDLERS.get(name)
        if handler is None:
            return _error(request_id, -32602, f"unknown tool: {name}")
        try:
            payload = handler(**(params.get("arguments") or {}))
        except TypeError as exc:
            return _error(request_id, -32602, f"bad arguments for {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - a tool failure is a result, not a transport error
            return _result(
                request_id,
                {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True},
            )
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        return _result(
            request_id,
            {"content": [{"type": "text", "text": text}], "structuredContent": payload, "isError": False},
        )
    return _error(request_id, -32601, f"unknown method: {method}")
