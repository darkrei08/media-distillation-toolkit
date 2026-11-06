"""Field-ownership reconciliation between the manifest and YTPTube.

Every fact has exactly one writer: YTPTube owns queue status and the artifact
facts, the manifest owns corpus membership. This pass reads YTPTube state and
writes only the YTPTube-owned fields, the two toolkit-owned freshness flags,
and the origin of an adopted record. It never deletes a record or a file.
"""

import copy
import hashlib
from collections.abc import Mapping, Sequence

from .ytptube import FAILED, FINISHED, QueueItem

DECLARED = "declared"
ADOPTED = "adopted"


def _apply_queue_facts(record: dict, item: QueueItem) -> None:
    record["queue_item_id"] = item.queue_id
    record["queue_status"] = item.status
    if item.attempts is not None:
        record["queue_attempts"] = item.attempts


def _apply_completed(record: dict, item: QueueItem) -> None:
    record.pop("stale", None)
    record.pop("unverified", None)
    record.pop("queue_error", None)
    _apply_queue_facts(record, item)
    if item.artifact_path is not None:
        record["artifact_path"] = item.artifact_path
    if item.artifact_bytes is not None:
        record["artifact_bytes"] = item.artifact_bytes
    if item.completed_at is not None:
        record["artifact_completed_at"] = item.completed_at


def _apply_failed(record: dict, item: QueueItem) -> None:
    record.pop("unverified", None)
    record["stale"] = True
    if item.error:
        record["queue_error"] = item.error
    _apply_queue_facts(record, item)


def _adopt(item: QueueItem) -> dict:
    record = {
        "id": hashlib.sha1(item.url.encode("utf-8")).hexdigest()[:16],
        "title": item.title or item.url,
        "url": item.url,
        "origin": ADOPTED,
    }
    _apply_completed(record, item)
    return record


def _newest_by_url(items: Sequence[QueueItem]) -> dict[str, QueueItem]:
    # YTPTube lists newest first, so the first item seen for a URL wins.
    by_url: dict[str, QueueItem] = {}
    for item in items:
        by_url.setdefault(item.url, item)
    return by_url


def reconcile(manifest: Mapping, items: Sequence[QueueItem]) -> dict:
    """Return a new manifest with YTPTube-owned facts applied, leaving the input untouched."""
    if not isinstance(manifest, Mapping):
        raise ValueError("manifest must be a JSON object")
    videos = manifest.get("videos")
    if not isinstance(videos, list):
        raise ValueError("manifest.videos must be a JSON array")

    result = copy.deepcopy(dict(manifest))
    videos = result["videos"]
    for index, record in enumerate(videos):
        if not isinstance(record, dict):
            raise ValueError(f"videos[{index}] must be a JSON object")

    by_id = {item.queue_id: item for item in items}
    by_url = _newest_by_url(items)
    matched_ids: set[str] = set()
    matched_urls: set[str] = set()

    for record in videos:
        queue_id = record.get("queue_item_id")
        item = by_id.get(queue_id) if isinstance(queue_id, str) else None
        if item is None:
            url = record.get("url")
            item = by_url.get(url) if isinstance(url, str) else None
        if item is None:
            record["unverified"] = True
            continue
        matched_ids.add(item.queue_id)
        matched_urls.add(item.url)
        if item.status == FINISHED:
            _apply_completed(record, item)
        elif item.status == FAILED:
            _apply_failed(record, item)
        # An in-flight item states no completed fact, so the record is left alone.

    for item in items:
        if item.status != FINISHED or item.queue_id in matched_ids or item.url in matched_urls:
            continue
        videos.append(_adopt(item))
        matched_ids.add(item.queue_id)
        matched_urls.add(item.url)

    return result
