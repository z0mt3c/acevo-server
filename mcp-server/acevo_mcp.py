"""MCP server for the AC EVO dashboard.

Wraps the dashboard's HTTP API so an assistant can inspect and drive the race
server. Every config tool follows the same fetch → modify → save cycle, so a
call is atomic and never leaves a half-written configuration behind.

Run it with:
    uvx --from . acevo-mcp
    ACEVO_URL=https://acevo.rock.w0rk.de uvx --from . acevo-mcp

Environment:
    ACEVO_URL       dashboard base URL (default http://127.0.0.1:8090)
    ACEVO_USER      basic-auth user, only if the dashboard has a password set
    ACEVO_PASSWORD  basic-auth password
    ACEVO_VERIFY    "false" to skip TLS verification for internal certificates
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

from mcp.server.mcpserver import MCPServer

BASE_URL = os.environ.get("ACEVO_URL", "http://127.0.0.1:8090").rstrip("/")
USER = os.environ.get("ACEVO_USER", "")
PASSWORD = os.environ.get("ACEVO_PASSWORD", "")
VERIFY = os.environ.get("ACEVO_VERIFY", "true").lower() != "false"

server = MCPServer("acevo", version="0.1.0")


def _context() -> ssl.SSLContext | None:
    if VERIFY:
        return None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _call(path: str, payload: dict | None = None) -> dict:
    request = urllib.request.Request(f"{BASE_URL}{path}")
    if USER or PASSWORD:
        token = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    if payload is not None:
        request.data = json.dumps(payload).encode()
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30, context=_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}", "detail": exc.read().decode("utf-8", errors="replace")[:400]}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"error": str(exc)}


def _form() -> dict:
    return _call("/api/config").get("form", {})


def _save(form: dict, apply: bool) -> dict:
    saved = _call("/api/save", {"form": form})
    if saved.get("error"):
        return saved
    result = {"saved": True, "warnings": saved.get("warnings", [])}
    if apply:
        result["restart"] = _call("/api/server/restart", {})
    return result


def _tracks(form: dict, meta: dict) -> list[dict]:
    race = "RACE_WEEKEND" in (form.get("event", {}).get("type") or "").upper()
    return meta["tracks"]["race_weekend" if race else "practice"]


# --- reading -----------------------------------------------------------------


@server.tool()
def status() -> dict:
    """Server state, connected drivers and their lap times."""
    return {"status": _call("/api/server/status"), "live": _call("/api/server/live")}


@server.tool()
def get_config() -> dict:
    """The full race configuration: server, event, sessions and car selection."""
    form = _form()
    cars = form.get("cars", [])
    return {
        "server": form.get("server"),
        "event": form.get("event"),
        "sessions": form.get("sessions"),
        "cars_selected": sum(1 for car in cars if car.get("is_selected")),
        "cars_total": len(cars),
    }


@server.tool()
def list_tracks(search: str = "") -> dict:
    """Tracks available in the current mode. Practice and race weekend differ —
    Nürburgring Touristenfahrten for instance only exists as a practice event."""
    meta = _call("/api/metadata")
    tracks = _tracks(_form(), meta)
    needle = search.strip().lower()
    names = [track["display"] for track in tracks if not needle or needle in track["display"].lower()]
    return {
        "mode": "race weekend" if "RACE_WEEKEND" in (_form()["event"]["type"] or "") else "practice",
        "count": len(names),
        "tracks": names,
    }


@server.tool()
def list_cars(only_selected: bool = False, search: str = "") -> dict:
    """Cars with their performance index and category."""
    meta = _call("/api/metadata")
    chosen = {car["name"]: car for car in _form().get("cars", [])}
    needle = search.strip().lower()
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


@server.tool()
def logs(tail: int = 100, contains: str = "") -> str:
    """Recent server log lines, optionally filtered."""
    lines = _call(f"/api/server/logs?tail={int(tail)}").get("lines", "").split("\n")
    if contains:
        lines = [line for line in lines if contains.lower() in line.lower()]
    return "\n".join(lines)


@server.tool()
def list_profiles() -> dict:
    """Saved configuration profiles."""
    return {"profiles": _call("/api/configs").get("profiles", [])}


@server.tool()
def list_results() -> dict:
    """Result deliveries the server has posted to the dashboard webhook."""
    return {"deliveries": _call("/api/results").get("deliveries", [])}


# --- changing ----------------------------------------------------------------


@server.tool()
def set_track(track: str, apply: bool = False) -> dict:
    """Pick a track by (partial) display name, e.g. "Laguna" or "Nordschleife"."""
    meta = _call("/api/metadata")
    form = _form()
    candidates = [t for t in _tracks(form, meta) if track.strip().lower() in t["display"].lower()]
    if not candidates:
        return {"error": f"no track matches {track!r} in this mode", "hint": "use list_tracks"}
    if len(candidates) > 1:
        exact = [t for t in candidates if t["display"].lower().startswith(track.strip().lower())]
        candidates = exact or candidates
    chosen = candidates[0]
    form["event"]["track"] = chosen["token"]
    limit = chosen.get("max_pit_slot", 50)
    form["server"]["max_players_limit"] = limit
    if form["server"].get("max_players", 0) > limit:
        form["server"]["max_players"] = limit
    return {"track": chosen["display"], "pit_limit": limit, **_save(form, apply)}


@server.tool()
def set_mode(mode: str, apply: bool = False) -> dict:
    """Switch between "practice" and "race" (race weekend). Keeps the same
    circuit where it exists in the target mode, and fills in session lengths if
    a race weekend would otherwise have nothing to drive."""
    meta = _call("/api/metadata")
    form = _form()
    race = mode.strip().lower().startswith("race")
    form["event"]["type"] = "GameModeType_RACE_WEEKEND" if race else "GameModeType_PRACTICE"

    previous = form["event"]["track"]
    target = meta["tracks"]["race_weekend" if race else "practice"]
    identity = "|".join(previous.split("|")[:2])
    match = next((t for t in target if "|".join(t["token"].split("|")[:2]) == identity), None)
    form["event"]["track"] = (match or target[0])["token"]

    if race and not form["sessions"]["race"]["length_sec"] and not form["sessions"]["qualify"]["length_sec"]:
        for name, seconds in (("practice", 1800), ("qualify", 900), ("warmup", 300), ("race", 2700)):
            form["sessions"][name]["length_sec"] = seconds

    return {
        "mode": "race weekend" if race else "practice",
        "track": (match or target[0])["display"],
        "track_kept": bool(match),
        **_save(form, apply),
    }


@server.tool()
def set_session(session: str, minutes: int, apply: bool = False) -> dict:
    """Set the length of "practice", "qualify", "warmup" or "race" in minutes."""
    form = _form()
    key = session.strip().lower()
    if key not in form.get("sessions", {}):
        return {"error": f"unknown session {session!r}", "known": sorted(form.get("sessions", {}))}
    form["sessions"][key]["length_sec"] = max(0, int(minutes) * 60)
    return {"session": key, "minutes": int(minutes), **_save(form, apply)}


@server.tool()
def set_server_options(
    name: str = "",
    max_players: int = 0,
    weather: str = "",
    apply: bool = False,
) -> dict:
    """Change the public server name, the slot count or the weather.
    Empty or zero arguments are left untouched."""
    meta = _call("/api/metadata")
    form = _form()
    if name:
        form["server"]["server_name"] = name
    if max_players:
        limit = form["server"].get("max_players_limit", 50)
        form["server"]["max_players"] = min(int(max_players), limit)
    if weather:
        options = meta["enums"]["weather"]
        hit = next((o for o in options if weather.strip().lower() in o["label"].lower()), None)
        if not hit:
            return {"error": f"unknown weather {weather!r}", "known": [o["label"] for o in options]}
        form["event"]["weather"] = hit["value"]
    return {"server": form["server"]["server_name"], **_save(form, apply)}


@server.tool()
def select_cars(cars: str, mode: str = "only", apply: bool = False) -> dict:
    """Choose the car field. `cars` is a class ("gt3", "gt2", "gt4", "formula",
    "cup", "road", "vintage", "electric", "all", "none") or a comma-separated
    list of name fragments. `mode` is "only" (replace) or "add"."""
    meta = _call("/api/metadata")
    form = _form()
    by_name = {car["internal_name"]: car for car in meta["cars"]}
    wanted = cars.strip().lower()

    def is_race(car):
        return car["type"] == "race"

    classes = {
        "all": lambda car: True,
        "none": lambda car: False,
        "gt3": lambda car: is_race(car) and "GT3" in car["display_name"] and "GT3 Cup" not in car["display_name"],
        "gt2": lambda car: is_race(car) and "GT2" in car["display_name"],
        "gt4": lambda car: is_race(car) and "GT4" in car["display_name"],
        "formula": lambda car: is_race(car) and any(k in car["display_name"] for k in ("SF-25", "F2004", "Formula")),
        "cup": lambda car: is_race(car) and any(k in car["display_name"] for k in ("Cup", "Challenge", "Trofeo")),
        "race": is_race,
        "road": lambda car: car["type"] == "road",
        "track": lambda car: car["type"] == "track",
        "vintage": lambda car: car["era"] == "vintage",
        "electric": lambda car: car["engine"] == "ev",
    }

    if wanted in classes:
        matches = classes[wanted]
    else:
        fragments = [part.strip().lower() for part in cars.split(",") if part.strip()]
        matches = lambda car: any(part in car["display_name"].lower() for part in fragments)  # noqa: E731

    count = 0
    for entry in form["cars"]:
        car = by_name.get(entry["name"])
        hit = bool(car and matches(car))
        if mode.strip().lower() == "add":
            if hit:
                entry["is_selected"] = True
        else:
            entry["is_selected"] = hit
        count += 1 if entry["is_selected"] else 0
    if count == 0 and wanted != "none":
        return {"error": f"{cars!r} matched no car", "hint": "use list_cars"}
    return {"selected": count, **_save(form, apply)}


@server.tool()
def balance_by_pi(per_pi_point: int = 10, apply: bool = False) -> dict:
    """Ballast the selected cars in proportion to how far their performance index
    sits above the slowest one. Ballast can only take performance away, so the
    slowest car is the target. The factor is a starting point, not physics —
    verify it on track."""
    meta = _call("/api/metadata")
    form = _form()
    by_name = {car["internal_name"]: car for car in meta["cars"]}
    selected = [
        (entry, by_name[entry["name"]])
        for entry in form["cars"]
        if entry.get("is_selected") and entry["name"] in by_name
    ]
    if len(selected) < 2:
        return {"error": "select at least two cars first"}
    slowest = min(car["pi"] for _entry, car in selected)
    applied = []
    for entry, car in selected:
        entry["ballast"] = round((car["pi"] - slowest) * per_pi_point)
        applied.append({"car": car["display_name"], "pi": car["pi"], "ballast": entry["ballast"]})
    return {"target_pi": slowest, "cars": applied, **_save(form, apply)}


@server.tool()
def apply_profile(name: str, apply: bool = False) -> dict:
    """Load a saved profile into the live configuration."""
    loaded = _call(f"/api/configs/get?name={urllib.parse.quote(name)}")
    if loaded.get("error") or "form" not in loaded:
        return loaded or {"error": "profile not found"}
    return {"profile": name, **_save(loaded["form"], apply)}


@server.tool()
def save_profile(name: str) -> dict:
    """Store the current configuration as a profile."""
    return _call("/api/configs/save", {"name": name, "form": _form()})


@server.tool()
def control(action: str) -> dict:
    """Run a server action: "start", "stop", "restart" or "update".
    "update" pulls a new build via SteamCMD and restarts."""
    verb = action.strip().lower()
    if verb not in {"start", "stop", "restart", "update"}:
        return {"error": f"unknown action {action!r}", "known": ["start", "stop", "restart", "update"]}
    return _call(f"/api/server/{verb}", {})


def main() -> None:
    """stdio for a desktop client, streamable-http when something like n8n has
    to reach the server over the network."""
    transport = os.environ.get("ACEVO_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        return server.run()
    server.run(
        transport,
        host=os.environ.get("ACEVO_MCP_HOST", "0.0.0.0"),
        port=int(os.environ.get("ACEVO_MCP_PORT", "3200")),
        streamable_http_path=os.environ.get("ACEVO_MCP_PATH", "/mcp"),
        # n8n opens a fresh connection per tool call; keeping no session state
        # avoids "session not found" on the second call.
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
