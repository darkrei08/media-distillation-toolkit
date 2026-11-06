import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from media_distill import QueueItem, YTPTubeClient, YTPTubeError, reconcile, validate_manifest
from media_distill.ytptube import FAILED, FINISHED, HISTORY, QUEUE

ROOT = Path(__file__).parents[1]
URL_A = "https://example.test/watch?v=alpha"
URL_B = "https://example.test/watch?v=beta"
KEY = "ytp_test_key_that_must_not_leak"


class _Recorder(BaseHTTPRequestHandler):
    """Loopback stand-in for the YTPTube API, answering from a scripted responder."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self._respond()

    def do_POST(self):
        self._respond()

    def _respond(self):
        parsed = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        request = {
            "method": self.command,
            "path": parsed.path,
            "query": dict(parse_qsl(parsed.query)),
            "authorization": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type"),
            "body": json.loads(body) if body else None,
        }
        self.server.requests.append(request)
        status, payload = self.server.responder(request)
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class FakeYTPTube(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
        self.server.daemon_threads = True
        self.server.requests = []
        self.server.responder = lambda request: (200, {})
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def client(self, api_key=KEY):
        return YTPTubeClient(self.base_url, api_key, timeout=5)


def history_page(items: list[dict[str, Any]], *, page: int = 1, has_next: bool = False) -> dict[str, Any]:
    return {
        "type": HISTORY,
        "pagination": {
            "page": page,
            "per_page": 200,
            "total": len(items),
            "total_pages": page,
            "has_next": has_next,
            "has_prev": page > 1,
        },
        "items": items,
    }


def finished_item(**overrides: Any) -> dict[str, Any]:
    item = {
        "_id": "q-alpha",
        "id": "alpha",
        "url": URL_A,
        "title": "Alpha",
        "status": FINISHED,
        "error": None,
        "filename": "alpha.mp4",
        "file_size": 1024,
        "datetime": "Mon, 06 Nov 2025 10:00:00 GMT",
        "extras": {"retry_attempt": 0},
    }
    item.update(overrides)
    return item


class ClientTests(FakeYTPTube):
    def test_submit_sends_the_expected_request_shape(self):
        self.server.responder = lambda request: (202, {"status": "accepted", "count": 2})

        accepted = self.client().submit([URL_A, URL_B])

        self.assertEqual(accepted, 2)
        request = self.server.requests[-1]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["path"], "/api/history/")
        self.assertEqual(request["authorization"], f"Bearer {KEY}")
        self.assertEqual(request["content_type"], "application/json")
        self.assertEqual(request["body"], [{"url": URL_A}, {"url": URL_B}])

    def test_list_items_parses_a_history_page(self):
        self.server.responder = lambda request: (200, history_page([finished_item()]))

        items = self.client().list_items(HISTORY)

        self.assertEqual(
            items,
            [
                QueueItem(
                    queue_id="q-alpha",
                    url=URL_A,
                    title="Alpha",
                    status=FINISHED,
                    error=None,
                    artifact_path="alpha.mp4",
                    artifact_bytes=1024,
                    completed_at="Mon, 06 Nov 2025 10:00:00 GMT",
                    attempts=0,
                )
            ],
        )
        self.assertEqual(self.server.requests[-1]["query"]["type"], HISTORY)

    def test_list_items_follows_pagination(self):
        pages = {
            1: history_page([finished_item()], page=1, has_next=True),
            2: history_page([finished_item(_id="q-beta", url=URL_B)], page=2),
        }
        self.server.responder = lambda request: (200, pages[int(request["query"]["page"])])

        items = self.client().list_items(HISTORY)

        self.assertEqual([item.queue_id for item in items], ["q-alpha", "q-beta"])
        self.assertEqual([request["query"]["page"] for request in self.server.requests], ["1", "2"])

    def test_queue_actions_send_the_item_ids(self):
        self.server.responder = lambda request: (200, {"status": "ok"})
        client = self.client()

        for action in ("start", "pause", "cancel", "retry"):
            getattr(client, action)(["q-alpha"])

        paths = [request["path"] for request in self.server.requests]
        self.assertEqual(
            paths,
            [f"/api/history/{action}" for action in ("start", "pause", "cancel", "retry")],
        )
        for request in self.server.requests:
            self.assertEqual(request["body"], {"ids": ["q-alpha"]})

    def test_get_item_refuses_a_response_without_an_item_id(self):
        self.server.responder = lambda request: (200, {"url": URL_A, "status": FINISHED})

        with self.assertRaises(YTPTubeError) as caught:
            self.client().get_item("q-alpha")

        self.assertIn("_id", str(caught.exception))

    def test_client_refuses_a_malformed_history_page(self):
        self.server.responder = lambda request: (200, {"type": HISTORY, "items": "not-a-list"})

        with self.assertRaises(YTPTubeError):
            self.client().list_items(HISTORY)

    def test_client_refuses_invalid_json(self):
        self.server.responder = lambda request: (200, b"<html>not json</html>")

        with self.assertRaises(YTPTubeError) as caught:
            self.client().list_items(HISTORY)

        self.assertIn("invalid JSON", str(caught.exception))

    def test_error_messages_never_contain_the_api_key(self):
        for responder in (
            lambda request: (401, {"error": "authentication required"}),
            lambda request: (200, b"not json"),
            lambda request: (200, {"items": "not-a-list"}),
        ):
            self.server.responder = responder
            with self.assertRaises(YTPTubeError) as caught:
                self.client().list_items(HISTORY)
            self.assertNotIn(KEY, str(caught.exception))


def declared_manifest(**record_overrides: Any) -> dict[str, Any]:
    record = {"id": "alpha", "title": "Alpha", "url": URL_A}
    record.update(record_overrides)
    return {"source_url": "https://example.test/playlist", "videos": [record]}


def completed(
    queue_id: str = "q-alpha", url: str = URL_A, title: str = "Alpha", **overrides: Any
) -> dict[str, Any]:
    facts = {
        "artifact_path": "alpha.mp4",
        "artifact_bytes": 1024,
        "completed_at": "Mon, 06 Nov 2025 10:00:00 GMT",
        "attempts": 0,
    }
    facts.update(overrides)
    return QueueItem(queue_id=queue_id, url=url, title=title, status=FINISHED, **facts)


class ReconcileTests(unittest.TestCase):
    def test_adopts_an_unknown_completed_item(self):
        result = reconcile(declared_manifest(), [completed(queue_id="q-beta", url=URL_B, title="Beta")])

        adopted = {
            "id": hashlib.sha1(URL_B.encode("utf-8")).hexdigest()[:16],
            "title": "Beta",
            "url": URL_B,
            "origin": "adopted",
            "queue_item_id": "q-beta",
            "queue_status": FINISHED,
            "queue_attempts": 0,
            "artifact_path": "alpha.mp4",
            "artifact_bytes": 1024,
            "artifact_completed_at": "Mon, 06 Nov 2025 10:00:00 GMT",
        }
        self.assertEqual(
            result,
            {
                "source_url": "https://example.test/playlist",
                "videos": [
                    {"id": "alpha", "title": "Alpha", "url": URL_A, "unverified": True},
                    adopted,
                ],
            },
        )

    def test_completed_item_updates_only_ytptube_owned_facts(self):
        manifest = declared_manifest(transcript_path="artifacts/alpha.md", retention="keep")

        result = reconcile(manifest, [completed()])

        self.assertEqual(
            result["videos"][0],
            {
                "id": "alpha",
                "title": "Alpha",
                "url": URL_A,
                "transcript_path": "artifacts/alpha.md",
                "retention": "keep",
                "queue_item_id": "q-alpha",
                "queue_status": FINISHED,
                "queue_attempts": 0,
                "artifact_path": "alpha.mp4",
                "artifact_bytes": 1024,
                "artifact_completed_at": "Mon, 06 Nov 2025 10:00:00 GMT",
            },
        )
        self.assertEqual(
            manifest["videos"][0],
            {
                "id": "alpha",
                "title": "Alpha",
                "url": URL_A,
                "transcript_path": "artifacts/alpha.md",
                "retention": "keep",
            },
        )

    def test_failed_item_marks_the_record_stale_and_keeps_the_artifact(self):
        manifest = declared_manifest(artifact_path="alpha.mp4", artifact_bytes=1024)
        failure = QueueItem(
            queue_id="q-alpha", url=URL_A, title="Alpha", status=FAILED, error="extractor gave up", attempts=2
        )

        result = reconcile(manifest, [failure])

        self.assertEqual(
            result["videos"][0],
            {
                "id": "alpha",
                "title": "Alpha",
                "url": URL_A,
                "artifact_path": "alpha.mp4",
                "artifact_bytes": 1024,
                "queue_item_id": "q-alpha",
                "queue_status": FAILED,
                "queue_attempts": 2,
                "queue_error": "extractor gave up",
                "stale": True,
            },
        )

    def test_absent_item_marks_the_record_unverified_without_deleting_it(self):
        manifest = declared_manifest(artifact_path="alpha.mp4", artifact_bytes=1024)

        result = reconcile(manifest, [])

        self.assertEqual(
            result["videos"][0],
            {
                "id": "alpha",
                "title": "Alpha",
                "url": URL_A,
                "artifact_path": "alpha.mp4",
                "artifact_bytes": 1024,
                "unverified": True,
            },
        )

    def test_a_later_success_clears_the_flags(self):
        manifest = declared_manifest(stale=True, unverified=True, queue_error="extractor gave up")

        result = reconcile(manifest, [completed()])

        self.assertEqual(
            result["videos"][0],
            {
                "id": "alpha",
                "title": "Alpha",
                "url": URL_A,
                "queue_item_id": "q-alpha",
                "queue_status": FINISHED,
                "queue_attempts": 0,
                "artifact_path": "alpha.mp4",
                "artifact_bytes": 1024,
                "artifact_completed_at": "Mon, 06 Nov 2025 10:00:00 GMT",
            },
        )

    def test_running_the_pass_twice_produces_identical_bytes(self):
        items = [completed(), completed(queue_id="q-beta", url=URL_B, title="Beta")]

        first = json.dumps(reconcile(declared_manifest(), items), indent=2, sort_keys=True, ensure_ascii=False)
        second = json.dumps(reconcile(json.loads(first), items), indent=2, sort_keys=True, ensure_ascii=False)

        self.assertEqual(first + "\n", second + "\n")


class ManifestFieldTests(unittest.TestCase):
    def test_existing_manifest_shape_still_validates(self):
        self.assertEqual(validate_manifest(declared_manifest()), [])

    def test_new_facts_validate(self):
        manifest = declared_manifest(
            origin="adopted",
            queue_item_id="q-alpha",
            queue_status=FINISHED,
            queue_error="",
            queue_attempts=2,
            artifact_path="alpha.mp4",
            artifact_bytes=1024,
            artifact_completed_at="Mon, 06 Nov 2025 10:00:00 GMT",
            stale=True,
            unverified=False,
        )

        self.assertEqual(validate_manifest(manifest), [])

    def test_malformed_new_facts_are_rejected(self):
        manifest = declared_manifest(origin="invented", queue_attempts=True, artifact_bytes=-1, stale="yes")

        errors = validate_manifest(manifest)

        self.assertTrue(any("origin" in error for error in errors))
        self.assertTrue(any("queue_attempts" in error for error in errors))
        self.assertTrue(any("artifact_bytes" in error for error in errors))
        self.assertTrue(any("stale" in error for error in errors))


class CliTests(FakeYTPTube):
    def test_reconcile_subcommand_updates_the_manifest_through_the_entry_point(self):
        def responder(request):
            if request["query"]["type"] == QUEUE:
                return 200, history_page([])
            return 200, history_page([finished_item()])

        self.server.responder = responder
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(declared_manifest()), encoding="utf-8")
            env = {**os.environ, "YTPTUBE_URL": self.base_url, "YTPTUBE_API_KEY": KEY}

            run = subprocess.run(
                [sys.executable, "-m", "media_distill", "reconcile", str(path)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(run.returncode, 0, run.stderr)
            written = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(written["videos"][0]["queue_item_id"], "q-alpha")
        self.assertEqual(written["videos"][0]["artifact_path"], "alpha.mp4")


if __name__ == "__main__":
    unittest.main()
