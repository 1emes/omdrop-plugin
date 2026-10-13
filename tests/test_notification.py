"""The toast for a received file: its thumbnail, and what a click opens.

An iPhone sends photos as HEIC, which the notification daemon cannot decode,
so the toast gets a JPEG preview. A click shows the file in the file manager
rather than handing it to whatever xdg-open picks, which can be the browser.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OMDROP = ROOT / "bin" / "omdrop"


class NotificationFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "log"
        self.stub("uwsm-app", 'shift; exec "$@"')
        self.stub("nautilus", 'printf "nautilus|%s\\n" "$*" >> "$LOG"')
        self.stub("xdg-open", 'printf "xdg-open|%s\\n" "$*" >> "$LOG"')
        self.stub("wl-copy", "cat >/dev/null")
        self.stub("omarchy-notification-send", 'printf "notify|%s\\n" "$*" >> "$LOG"')
        self.env = os.environ.copy()
        self.env.update(
            PATH=f"{self.bin}:{self.env['PATH']}",
            LOG=str(self.log),
            XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_DATA_HOME=str(self.root / "data"),
            XDG_CACHE_HOME=str(self.root / "cache"),
        )

    def stub(self, name, body):
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}\n")
        path.chmod(0o755)

    def run_omdrop(self, *args):
        return subprocess.run([OMDROP, *args], env=self.env, capture_output=True, text=True)

    def logged(self):
        return self.log.read_text().splitlines() if self.log.exists() else []


class ClickTests(NotificationFixture):
    def test_a_click_shows_the_file_in_the_file_manager(self):
        photo = self.root / "photo.jpg"
        photo.write_bytes(b"jpeg")

        result = self.run_omdrop("act", "open", str(photo))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.logged(), [f"nautilus|--select {photo}"])


class PreviewTests(NotificationFixture):
    def test_a_heic_toast_carries_a_jpeg_preview(self):
        # heif-convert SRC DEST: write something to DEST.
        self.stub("heif-convert", 'for a; do d=$a; done; printf jpeg > "$d"')
        photo = self.root / "IMG_1.heic"
        photo.write_bytes(b"heic")

        result = self.run_omdrop("handle", str(photo))

        self.assertEqual(result.returncode, 0, result.stderr)
        preview = self.root / "cache" / "omdrop" / "IMG_1.preview.jpg"
        notify = [line for line in self.logged() if line.startswith("notify|")]
        self.assertEqual(len(notify), 1, notify)
        self.assertIn(f"--image {preview}", notify[0])
        self.assertTrue(preview.exists())

    def test_a_heic_toast_still_appears_when_the_conversion_fails(self):
        self.stub("heif-convert", "exit 1")
        photo = self.root / "IMG_2.heic"
        photo.write_bytes(b"heic")

        result = self.run_omdrop("handle", str(photo))

        self.assertEqual(result.returncode, 0, result.stderr)
        notify = [line for line in self.logged() if line.startswith("notify|")]
        self.assertEqual(len(notify), 1, notify)
        self.assertNotIn("--image", notify[0])

    def test_a_jpeg_toast_uses_the_file_itself(self):
        photo = self.root / "photo.jpg"
        photo.write_bytes(b"jpeg")

        self.run_omdrop("handle", str(photo))

        notify = [line for line in self.logged() if line.startswith("notify|")]
        self.assertIn(f"--image {photo}", notify[0])


if __name__ == "__main__":
    unittest.main()
