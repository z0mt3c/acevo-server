"""scripts/update.sh: Login-Strategie gegen ein vorgetaeuschtes steamcmd geprueft.

Das Fake-steamcmd protokolliert jeden Aufruf und liefert pro Aufruf einen
vorgegebenen Exit-Code, damit auch der Fallback-Pfad (abgelaufenes Token)
getestet werden kann und nicht nur der Happy Path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UPDATE_SH = REPO_ROOT / "scripts" / "update.sh"


def _bash_with_case_conversion() -> str | None:
    """update.sh nutzt ${VAR,,} — das gibt es erst ab bash 4 (macOS liefert 3.2)."""
    for candidate in ("bash", "/opt/homebrew/bin/bash", "/usr/local/bin/bash", "/bin/bash"):
        path = shutil.which(candidate) if "/" not in candidate else candidate
        if not path or not os.access(path, os.X_OK):
            continue
        probe = subprocess.run([path, "-c", 'v=A; echo "${v,,}"'], capture_output=True, text=True)
        if probe.returncode == 0 and probe.stdout.strip() == "a":
            return path
    return None


BASH = _bash_with_case_conversion()

FAKE_STEAMCMD = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "${CALL_LOG}"
call_no=$(wc -l < "${CALL_LOG}" | tr -d ' ')
code=$(sed -n "${call_no}p" "${EXIT_CODES}")
exit "${code:-0}"
"""


@unittest.skipIf(BASH is None, "needs bash >= 4 (macOS ships 3.2)")
class UpdateScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "steamcmd"
        fake.write_text(FAKE_STEAMCMD, encoding="utf-8")
        fake.chmod(0o755)

        self.bin_dir = bin_dir
        self.call_log = tmp / "calls.txt"
        self.call_log.write_text("", encoding="utf-8")
        self.exit_codes = tmp / "codes.txt"
        self.install_dir = tmp / "server"

    def run_update(self, exit_codes: list[int], **env_overrides) -> subprocess.CompletedProcess:
        self.exit_codes.write_text("\n".join(str(code) for code in exit_codes) + "\n", encoding="utf-8")
        env = {
            "PATH": f"{self.bin_dir}:{os.environ.get('PATH', '')}",
            "HOME": str(self.tmp.name),
            "CALL_LOG": str(self.call_log),
            "EXIT_CODES": str(self.exit_codes),
            "SERVER_INSTALL_DIR": str(self.install_dir),
            "STEAM_USERNAME": "racer",
            "STEAM_PASSWORD": "hunter2",
        }
        env.update(env_overrides)
        return subprocess.run(
            [BASH, str(UPDATE_SH)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def calls(self) -> list[str]:
        return [line for line in self.call_log.read_text(encoding="utf-8").splitlines() if line]

    def test_uses_cached_token_without_password(self) -> None:
        result = self.run_update([0])
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 1, f"erwartet ein steamcmd-Aufruf, war: {calls}")
        self.assertIn("+login racer", calls[0])
        self.assertNotIn("hunter2", calls[0])

    def test_falls_back_to_password_when_token_expired(self) -> None:
        result = self.run_update([5, 0])
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 2, f"erwartet Fallback-Aufruf, war: {calls}")
        self.assertNotIn("hunter2", calls[0])
        self.assertIn("+login racer hunter2", calls[1])

    def test_auth_code_appended_to_fallback_only(self) -> None:
        result = self.run_update([5, 0], STEAM_AUTH_CODE="ABC42")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertNotIn("ABC42", calls[0])
        self.assertIn("+login racer hunter2 ABC42", calls[1])

    def test_no_retry_without_password(self) -> None:
        result = self.run_update([5], STEAM_PASSWORD="")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), 1, "ohne Passwort darf kein zweiter Versuch laufen")

    def test_empty_password_is_allowed_when_token_works(self) -> None:
        result = self.run_update([0], STEAM_PASSWORD="")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_username_still_required(self) -> None:
        result = self.run_update([0], STEAM_USERNAME="")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_validate_flag_reaches_steamcmd(self) -> None:
        self.run_update([0], STEAM_VALIDATE="true")
        self.assertIn("+app_update 4564210 validate", self.calls()[0])


if __name__ == "__main__":
    unittest.main()
