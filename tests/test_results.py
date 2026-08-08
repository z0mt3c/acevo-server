"""dashboard/results.py — capture whatever the server posts, before we know its shape."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard import results


class RecordTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "results"
        patcher = patch.object(results, "RESULTS_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def files(self) -> list[Path]:
        return sorted(self.dir.glob("*"))

    def test_stores_a_json_delivery(self) -> None:
        payload = json.dumps({"session": "race", "drivers": []}).encode()
        outcome = results.record(payload, "application/json")
        self.assertTrue(outcome["ok"])
        self.assertEqual(len(self.files()), 1)
        self.assertEqual(self.files()[0].read_bytes(), payload)
        self.assertIn(".json", self.files()[0].name)

    def test_stores_a_body_that_is_not_json(self) -> None:
        """Rejecting an unparseable body would lose the very thing we are trying
        to learn about."""
        outcome = results.record(b"<xml/>", "text/xml")
        self.assertTrue(outcome["ok"])
        self.assertEqual(len(self.files()), 1)
        self.assertIn("not JSON", outcome["summary"])

    def test_creates_the_directory(self) -> None:
        self.assertFalse(self.dir.exists())
        results.record(b"{}", "application/json")
        self.assertTrue(self.dir.is_dir())

    def test_summary_names_the_keys(self) -> None:
        outcome = results.record(json.dumps({"b": 1, "a": 2}).encode(), "application/json")
        self.assertIn("['a', 'b']", outcome["summary"])

    def test_echoes_into_the_server_log(self) -> None:
        written = []
        results.record(b'{"x": 1}', "application/json", log_writer=written.append)
        self.assertEqual(len(written), 1)
        self.assertIn("results webhook", written[0])
        self.assertIn('{"x": 1}', written[0])

    def test_headers_are_logged_for_diagnosis(self) -> None:
        """An empty JSON body is ambiguous — the headers say whether it arrived
        chunked or was genuinely empty."""
        written = []
        results.record(b"", "application/json", log_writer=written.append, headers={"Transfer-Encoding": "chunked"})
        self.assertIn("Transfer-Encoding: chunked", written[0])

    def test_empty_body_is_still_recorded(self) -> None:
        outcome = results.record(b"", "")
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["bytes"], 0)

    def test_deliveries_are_listed_newest_first(self) -> None:
        results.record(b'{"first": 1}', "application/json")
        results.record(b'{"second": 2}', "application/json")
        listing = results.stored()
        self.assertEqual(len(listing), 2)
        self.assertGreaterEqual(listing[0]["modified"], listing[1]["modified"])

    def test_listing_is_empty_without_a_directory(self) -> None:
        self.assertEqual(results.stored(), [])


if __name__ == "__main__":
    unittest.main()
