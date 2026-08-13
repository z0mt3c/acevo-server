"""dashboard/history.py — lap history, leaderboards and session records.

The recorder is fed through a real log file on disk, because offset handling
(incremental reads, truncation, laps that predate the recorder) is exactly the
part that breaks silently.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard import history, server_control

CONNECT = (
    "[2026-08-09 10:00:0{i}.000] [server] [info] connecting gamecar {car_id} ({name} | {steam_id})\n"
    "[2026-08-09 10:00:0{i}.001] [gameplay] [info] {steam_id} connected (true) on car {car}, with new carId {car_id}\n"
)
LAP = "[2026-08-09 10:1{i}:00.000] [gameplay] [info] New lap carId {car_id}: {time}\n"


class HistoryBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.log = base / "server.log"
        self.log.write_text("", encoding="utf-8")
        for target, attribute, value in (
            (history, "DB_PATH", base / "history.db"),
            (server_control, "LOG_FILE", self.log),
        ):
            patcher = patch.object(target, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        track_patch = patch.object(history, "_current_track", return_value=("Laguna Seca GP", "practice"))
        track_patch.start()
        self.addCleanup(track_patch.stop)
        history.reset_state()

    def drive(
        self,
        car_id="aaaa1111bbbb2222-cccc3333dddd4444",
        name="Max",
        steam_id="765611",
        car="ks_ferrari_296_gt3",
        times=("01:40.000",),
    ):
        text = CONNECT.format(i=1, car_id=car_id, name=name, steam_id=steam_id, car=car)
        for index, lap in enumerate(times):
            text += LAP.format(i=index, car_id=car_id, time=lap)
        with open(self.log, "a", encoding="utf-8") as handle:
            handle.write(text)


class RecorderTest(HistoryBase):
    def test_laps_before_the_recorder_started_are_skipped(self) -> None:
        """After a dashboard restart the log may already contain a finished
        session — replaying it would duplicate every lap already stored."""
        self.drive(times=("01:40.000",))
        history.poll()  # first poll only positions the offset
        self.assertEqual(history.poll(), 0)

    def test_records_laps_with_driver_and_car(self) -> None:
        history.poll()
        history.notify_server_start()
        self.drive(times=("01:40.000", "01:38.500"))
        self.assertEqual(history.poll(), 2)
        detail = history.session_detail(history.sessions(include_empty=True)[0]["id"])
        self.assertEqual(detail["session"]["track"], "Laguna Seca GP")
        self.assertEqual(detail["standings"][0]["driver"], "Max")
        self.assertEqual(detail["standings"][0]["best_ms"], 98500)
        self.assertEqual(detail["standings"][0]["laps"], 2)

    def test_polling_twice_does_not_duplicate(self) -> None:
        history.poll()
        history.notify_server_start()
        self.drive()
        self.assertEqual(history.poll(), 1)
        self.assertEqual(history.poll(), 0)

    def test_server_restart_starts_a_new_session(self) -> None:
        history.poll()
        history.notify_server_start()
        self.drive(times=("01:40.000",))
        history.poll()
        # start() truncates the log before launching the server
        self.log.write_text("", encoding="utf-8")
        history.notify_server_start()
        self.drive(name="Zoe", steam_id="765622", times=("01:39.000",))
        history.poll()
        sessions = history.sessions()
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0]["laps"], 1)

    def test_laps_without_a_session_are_dropped(self) -> None:
        history.poll()
        self.drive()
        self.assertEqual(history.poll(), 0)

    def test_snapshot_backup_is_a_readable_copy(self) -> None:
        import sqlite3

        history.poll()
        history.notify_server_start()
        self.drive()
        history.poll()
        target = history.snapshot_backup()
        self.assertTrue(target.exists())
        with sqlite3.connect(target) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM laps").fetchone()[0], 1)


class RecordEventTest(HistoryBase):
    """A lap that takes P1 fires a webhook — that is what ends up in Discord."""

    def setUp(self) -> None:
        super().setUp()
        self.events = []
        for patcher in (
            patch.object(history, "WEBHOOK_URL", "http://n8n.test/webhook"),
            patch.object(history, "_post_webhook", side_effect=self.events.append),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        history.poll()
        history.notify_server_start()

    def test_first_lap_on_a_track_is_a_track_record(self) -> None:
        self.drive(times=("01:40.000",))
        history.poll()
        self.assertEqual(len(self.events), 1)
        event = self.events[0]
        self.assertEqual(event["event"], "track_record")
        self.assertEqual(event["driver"], "Max")
        self.assertEqual(event["lap_time"], "1:40.000")
        self.assertEqual(event["previous_driver"], "")

    def test_a_slower_lap_fires_nothing(self) -> None:
        self.drive(times=("01:40.000",))
        history.poll()
        self.events.clear()
        self.drive(car_id="c" * 16 + "-" + "d" * 16, name="Rob", steam_id="9", times=("01:45.000",))
        history.poll()
        self.assertEqual(self.events, [])

    def test_beating_the_overall_best_is_a_track_record_with_the_previous_holder(self) -> None:
        self.drive(times=("01:40.000",))
        history.poll()
        self.events.clear()
        self.drive(car_id="c" * 16 + "-" + "d" * 16, name="Zoe", steam_id="2", times=("01:38.000",))
        history.poll()
        self.assertEqual(self.events[0]["event"], "track_record")
        self.assertEqual(self.events[0]["previous_driver"], "Max")
        self.assertEqual(self.events[0]["previous_time"], "1:40.000")

    def test_fastest_in_a_slower_car_is_a_car_record(self) -> None:
        self.drive(times=("01:40.000",))
        history.poll()
        self.events.clear()
        self.drive(
            car_id="c" * 16 + "-" + "d" * 16, name="Zoe", steam_id="2", car="ks_bmw_m4_gt3", times=("01:42.000",)
        )
        history.poll()
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["event"], "car_record")

    def test_no_webhook_url_means_no_events(self) -> None:
        with patch.object(history, "WEBHOOK_URL", ""):
            self.drive(times=("01:40.000",))
            history.poll()
        self.assertEqual(self.events, [])


class LeaderboardTest(HistoryBase):
    def seed(self) -> None:
        history.poll()
        history.notify_server_start()
        self.drive(
            car_id="a" * 16 + "-" + "b" * 16,
            name="Max",
            steam_id="1",
            car="ks_ferrari_296_gt3",
            times=("01:40.000", "01:36.369"),
        )
        self.drive(
            car_id="c" * 16 + "-" + "d" * 16, name="Zoe", steam_id="2", car="ks_bmw_m4_gt3", times=("01:35.100",)
        )
        self.drive(
            car_id="e" * 16 + "-" + "f" * 16, name="Rob", steam_id="3", car="ks_ferrari_296_gt3", times=("01:41.000",)
        )
        history.poll()

    def test_leaderboard_ranks_each_drivers_personal_best(self) -> None:
        self.seed()
        board = history.leaderboard("Laguna")
        self.assertEqual([row["driver"] for row in board], ["Zoe", "Max", "Rob"])
        self.assertEqual(board[0]["best_ms"], 95100)
        self.assertEqual(board[1]["car"], "ks_ferrari_296_gt3")

    def test_leaderboard_can_be_narrowed_to_one_car(self) -> None:
        self.seed()
        board = history.leaderboard("Laguna", car="ferrari")
        self.assertEqual([row["driver"] for row in board], ["Max", "Rob"])

    def test_records_hold_one_row_per_track_and_car(self) -> None:
        self.seed()
        rows = history.bests()
        combos = {(row["track"], row["car"]) for row in rows}
        self.assertEqual(len(rows), len(combos))
        ferrari = next(row for row in rows if row["car"] == "ks_ferrari_296_gt3")
        self.assertEqual(ferrari["driver"], "Max")
        self.assertEqual(ferrari["best_ms"], 96369)

    def test_a_faster_lap_in_a_later_session_takes_the_record(self) -> None:
        self.seed()
        self.log.write_text("", encoding="utf-8")
        history.notify_server_start()
        self.drive(
            car_id="1" * 16 + "-" + "2" * 16, name="Rob", steam_id="3", car="ks_ferrari_296_gt3", times=("01:30.000",)
        )
        history.poll()
        ferrari = next(row for row in history.bests() if row["car"] == "ks_ferrari_296_gt3")
        self.assertEqual(ferrari["driver"], "Rob")
        self.assertEqual(ferrari["best_ms"], 90000)

    def test_sessions_hide_empty_runs_by_default(self) -> None:
        self.seed()
        self.log.write_text("", encoding="utf-8")
        history.notify_server_start()  # deploy restart, nobody drove
        self.assertEqual(len(history.sessions()), 1)
        self.assertEqual(len(history.sessions(include_empty=True)), 2)


if __name__ == "__main__":
    unittest.main()
