"""dashboard/live.py — driver state reconstructed from the server log.

The fixture lines are verbatim from a real session; the parser is the fragile
part of the live view, so the log format is pinned here on purpose. If an AC EVO
update changes the wording, these tests fail instead of the dashboard silently
showing an empty grid.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard import live

SESSION_LOG = """\
[2026-08-07 21:01:07.767] [server] [info] Listening to TCP 9700
[2026-08-07 21:34:07.403] [server] [info] assigning pit slot 1 competitor_id 7656119820008539047efe85b7c69e844-6d27cbdfe96760ab car_number 20
[2026-08-07 21:34:07.404] [gameplay] [info] 76561198200085390 connected (true) on car ks_maserati_mc20_gt2, with new carId 47efe85b7c69e844-6d27cbdfe96760ab
[2026-08-07 21:34:07.404] [server] [info] connecting gamecar 47efe85b7c69e844-6d27cbdfe96760ab (Max Bearman | 76561198200085390)
[2026-08-07 21:34:07.404] [server] [info] Car [47efe85b7c69e844-6d27cbdfe96760ab] #20 for driver Max Bearman [76561198200085390]
[2026-08-07 21:34:42.763] [gameplay] [info] [SERVER][47efe85b7c69e844-6d27cbdfe96760ab] Received pit_state: pit_slot: 1 total_pit_time_ms: 30000
[2026-08-07 21:41:12.100] [gameplay] [info] New lap carId 47efe85b7c69e844-6d27cbdfe96760ab: 01:38.500
[2026-08-07 21:43:06.729] [gameplay] [info] New lap carId 47efe85b7c69e844-6d27cbdfe96760ab: 01:36.369
[2026-08-07 21:44:00.000] [server] [info] Server updated: 1 players
"""

DISCONNECT_LOG = (
    SESSION_LOG
    + "[2026-08-07 21:45:08.126] [server] [info] Removing disconnected remote_car 47efe85b-7c69-e844-6d27-cbdfe96760ab\n"
    "[2026-08-07 21:45:08.130] [server] [info] Server updated: 0 players\n"
)


class ParseDriversTest(unittest.TestCase):
    def drivers(self, text: str) -> list[dict]:
        return live.parse_log(text)["drivers"]

    def test_identifies_the_driver(self) -> None:
        driver = self.drivers(SESSION_LOG)[0]
        self.assertEqual(driver["name"], "Max Bearman")
        self.assertEqual(driver["steam_id"], "76561198200085390")
        self.assertEqual(driver["car"], "ks_maserati_mc20_gt2")
        self.assertEqual(driver["number"], 20)
        self.assertTrue(driver["connected"])

    def test_collects_lap_times(self) -> None:
        driver = self.drivers(SESSION_LOG)[0]
        self.assertEqual(driver["laps"], 2)
        self.assertEqual(driver["last_lap_ms"], 96369)
        self.assertEqual(driver["best_lap_ms"], 96369)

    def test_best_lap_is_the_fastest_not_the_latest(self) -> None:
        log = (
            SESSION_LOG
            + "[2026-08-07 21:44:10.000] [gameplay] [info] New lap carId 47efe85b7c69e844-6d27cbdfe96760ab: 01:41.000\n"
        )
        driver = self.drivers(log)[0]
        self.assertEqual(driver["last_lap_ms"], 101000)
        self.assertEqual(driver["best_lap_ms"], 96369)

    def test_disconnect_marks_the_driver_gone(self) -> None:
        """The disconnect line writes the car id dashed, the connect line does not."""
        drivers = self.drivers(DISCONNECT_LOG)
        self.assertEqual(len(drivers), 1)
        self.assertFalse(drivers[0]["connected"])

    def test_player_count_comes_from_the_last_update_line(self) -> None:
        self.assertEqual(live.parse_log(SESSION_LOG)["players"], 1)
        self.assertEqual(live.parse_log(DISCONNECT_LOG)["players"], 0)

    def test_unknown_lines_are_ignored(self) -> None:
        result = live.parse_log("total garbage\n[2026-01-01 00:00:00.000] [server] [info] whatever\n")
        self.assertEqual(result["drivers"], [])
        self.assertEqual(result["players"], 0)

    def test_empty_log(self) -> None:
        self.assertEqual(live.parse_log("")["drivers"], [])

    def test_connected_drivers_sort_before_disconnected(self) -> None:
        log = DISCONNECT_LOG + (
            "[2026-08-07 21:50:00.000] [server] [info] connecting gamecar aaaa1111bbbb2222-cccc3333dddd4444 (Zoe | 7656119800000000)\n"
        )
        drivers = self.drivers(log)
        self.assertTrue(drivers[0]["connected"])
        self.assertEqual(drivers[0]["name"], "Zoe")


class SnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "server.log"

    def test_snapshot_merges_log_and_listing(self) -> None:
        self.log.write_text(SESSION_LOG, encoding="utf-8")
        with (
            patch.object(live.server_control, "LOG_FILE", self.log),
            patch.object(live, "fetch_listing", return_value={"clients": 3, "version": 6}),
        ):
            snap = live.snapshot()
        self.assertEqual(len(snap["drivers"]), 1)
        self.assertEqual(snap["clients"], 3)
        self.assertEqual(snap["players"], 1)

    def test_snapshot_survives_an_unreachable_listing(self) -> None:
        self.log.write_text(SESSION_LOG, encoding="utf-8")
        with (
            patch.object(live.server_control, "LOG_FILE", self.log),
            patch.object(live, "fetch_listing", return_value=None),
        ):
            snap = live.snapshot()
        self.assertIsNone(snap["clients"])
        self.assertEqual(len(snap["drivers"]), 1)

    def test_snapshot_without_a_log_file(self) -> None:
        with (
            patch.object(live.server_control, "LOG_FILE", self.log / "missing.log"),
            patch.object(live, "fetch_listing", return_value=None),
        ):
            snap = live.snapshot()
        self.assertEqual(snap["drivers"], [])


class LapFormatTest(unittest.TestCase):
    def test_parses_minutes_seconds_millis(self) -> None:
        self.assertEqual(live.lap_to_ms("01:36.369"), 96369)
        self.assertEqual(live.lap_to_ms("12:00.000"), 720000)

    def test_rejects_nonsense(self) -> None:
        self.assertIsNone(live.lap_to_ms("--:--.---"))
        self.assertIsNone(live.lap_to_ms(""))


if __name__ == "__main__":
    unittest.main()
