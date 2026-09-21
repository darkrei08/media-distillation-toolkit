import json
import subprocess
import sys
import unittest
from pathlib import Path

from media_distill import render_transcript, validate_manifest


ROOT = Path(__file__).parents[1]


class ToolkitTests(unittest.TestCase):
    def test_valid_manifest_has_no_errors(self):
        manifest = json.loads((ROOT / "examples/playlist-manifest.json").read_text())
        self.assertEqual(validate_manifest(manifest), [])

    def test_manifest_rejects_duplicate_ids_and_bad_urls(self):
        manifest = {
            "source_url": "not-a-url",
            "videos": [
                {"id": "same", "title": "One", "url": "https://example.test/1"},
                {"id": "same", "title": "Two", "url": "https://"},
            ],
        }
        errors = validate_manifest(manifest)
        self.assertTrue(any("source_url" in error for error in errors))
        self.assertTrue(any("duplicates" in error for error in errors))
        self.assertTrue(any("videos[1].url" in error for error in errors))

    def test_render_preserves_present_fields_without_inventing_timestamps(self):
        rendered = render_transcript(
            {"segments": [
                {"timestamp": "00:01", "speaker": "Ada", "text": "Hello"},
                {"text": "No timestamp"},
            ]}
        )
        self.assertEqual(
            rendered,
            "# Transcript\n\n- [00:01] **Ada:** Hello\n- No timestamp\n",
        )

    def test_module_cli_validates_and_renders(self):
        manifest = ROOT / "examples/playlist-manifest.json"
        validate = subprocess.run(
            [sys.executable, "-m", "media_distill", "validate", str(manifest)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        render = subprocess.run(
            [sys.executable, "-m", "media_distill", "render", str(ROOT / "examples/transcript.json"), "--output", "/dev/null"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(validate.returncode, 0, validate.stderr)
        self.assertEqual(render.returncode, 0, render.stderr)


if __name__ == "__main__":
    unittest.main()
