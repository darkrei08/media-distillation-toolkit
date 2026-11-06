"""Standard-library client for the YTPTube download queue API."""

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

API_URL_ENV = "YTPTUBE_URL"
API_KEY_ENV = "YTPTUBE_API_KEY"
DEFAULT_API_URL = "http://127.0.0.1:8010"

QUEUE = "queue"
HISTORY = "done"
FINISHED = "finished"
FAILED = "error"

PAGE_SIZE = 200
MAX_PAGES = 100


class YTPTubeError(RuntimeError):
    """YTPTube is unreachable or answered with an unexpected shape."""


@dataclass(frozen=True)
class QueueItem:
    """The YTPTube-owned facts about one queue or history item."""

    queue_id: str
    url: str
    title: str
    status: str
    error: str | None = None
    artifact_path: str | None = None
    artifact_bytes: int | None = None
    completed_at: str | None = None
    attempts: int | None = None


def _string(raw: Mapping, key: str, *, required: bool) -> str | None:
    value = raw.get(key)
    if value is None:
        if required:
            raise YTPTubeError(f"item field {key!r} is missing")
        return None
    if not isinstance(value, str):
        raise YTPTubeError(f"item field {key!r} must be a string")
    if required and not value.strip():
        raise YTPTubeError(f"item field {key!r} must be a non-empty string")
    return value


def _count(raw: Mapping, key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise YTPTubeError(f"item field {key!r} must be a non-negative integer")
    return value


def _attempts(raw: Mapping) -> int | None:
    extras = raw.get("extras")
    if extras is None:
        return None
    if not isinstance(extras, Mapping):
        raise YTPTubeError("item field 'extras' must be a JSON object")
    value = extras.get("retry_attempt")
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise YTPTubeError("item field 'extras.retry_attempt' must be a non-negative integer")
    return value


def parse_item(raw: object) -> QueueItem:
    """Build a QueueItem from one API item, refusing anything malformed."""
    if not isinstance(raw, Mapping):
        raise YTPTubeError("history item must be a JSON object")
    status = _string(raw, "status", required=True) or ""
    return QueueItem(
        queue_id=_string(raw, "_id", required=True) or "",
        url=_string(raw, "url", required=True) or "",
        title=_string(raw, "title", required=False) or "",
        status=status,
        error=_string(raw, "error", required=False),
        artifact_path=_string(raw, "filename", required=False),
        artifact_bytes=_count(raw, "file_size"),
        completed_at=_string(raw, "datetime", required=False) if status == FINISHED else None,
        attempts=_attempts(raw),
    )


class YTPTubeClient:
    """The narrow YTPTube surface the toolkit depends on."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 30.0) -> None:
        self._base_url = (base_url or os.environ.get(API_URL_ENV) or DEFAULT_API_URL).rstrip("/")
        self._api_key = api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")
        self._timeout = timeout

    def submit(self, urls: Sequence[str]) -> int:
        """Enqueue one or more URLs and return how many were accepted."""
        payload = [{"url": url} for url in urls]
        if not payload:
            raise ValueError("at least one URL is required")
        result = self._request("POST", "/api/history/", body=payload)
        if isinstance(result, list):
            return len(result)
        if not isinstance(result, Mapping):
            raise YTPTubeError("unexpected response from /api/history/: expected a JSON object")
        if result.get("status") != "accepted":
            raise YTPTubeError("unexpected response from /api/history/: the queue did not accept the items")
        count = result.get("count")
        if not isinstance(count, int) or isinstance(count, bool):
            raise YTPTubeError("unexpected response from /api/history/: 'count' must be an integer")
        return count

    def list_items(self, kind: str = HISTORY) -> list[QueueItem]:
        """Read every item of one store, following pagination."""
        if kind not in (QUEUE, HISTORY):
            raise ValueError(f"kind must be {QUEUE!r} or {HISTORY!r}")
        items: list[QueueItem] = []
        for page in range(1, MAX_PAGES + 1):
            payload = self._request(
                "GET",
                "/api/history/",
                query={"type": kind, "page": page, "per_page": PAGE_SIZE, "order": "DESC"},
            )
            if not isinstance(payload, Mapping) or not isinstance(payload.get("items"), list):
                raise YTPTubeError("unexpected response from /api/history/: missing 'items' array")
            items.extend(parse_item(raw) for raw in payload["items"])
            pagination = payload.get("pagination")
            if not isinstance(pagination, Mapping):
                raise YTPTubeError("unexpected response from /api/history/: missing 'pagination' object")
            if not pagination.get("has_next"):
                return items
        raise YTPTubeError(f"/api/history/ pagination exceeded {MAX_PAGES} pages")

    def get_item(self, item_id: str) -> QueueItem:
        """Inspect a single queue or history item."""
        return parse_item(self._request("GET", f"/api/history/{quote(item_id, safe='')}"))

    def start(self, item_ids: Sequence[str]) -> dict:
        return self._action("start", item_ids)

    def pause(self, item_ids: Sequence[str]) -> dict:
        return self._action("pause", item_ids)

    def cancel(self, item_ids: Sequence[str]) -> dict:
        return self._action("cancel", item_ids)

    def retry(self, item_ids: Sequence[str]) -> dict:
        return self._action("retry", item_ids)

    def _action(self, action: str, item_ids: Sequence[str]) -> dict:
        ids = list(item_ids)
        if not ids:
            raise ValueError("at least one queue item id is required")
        payload = self._request("POST", f"/api/history/{action}", body={"ids": ids})
        if not isinstance(payload, Mapping):
            raise YTPTubeError(f"unexpected response from /api/history/{action}: expected a JSON object")
        return dict(payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        body: object | None = None,
    ) -> object:
        url = f"{self._base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        # NOTE: the API key lives only in the request header, never in a message.
        if not self._api_key:
            raise YTPTubeError(f"{API_KEY_ENV} is not set; YTPTube requires authentication")
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self._api_key}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        try:
            with urlopen(Request(url, data=data, headers=headers, method=method), timeout=self._timeout) as response:
                raw = response.read()
        except HTTPError as error:
            raise YTPTubeError(f"{method} {path} failed with HTTP {error.code}") from None
        except (URLError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise YTPTubeError(f"{method} {path} failed: {reason}") from None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise YTPTubeError(f"{method} {path} returned invalid JSON") from None
