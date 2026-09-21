"""Validation for the documented playlist manifest format."""

from collections.abc import Mapping
from urllib.parse import urlparse


def _valid_url(value: object) -> bool:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_manifest(manifest: object) -> list[str]:
    """Return validation errors for a manifest, or an empty list when valid."""
    errors: list[str] = []
    if not isinstance(manifest, Mapping):
        return ["manifest must be a JSON object"]

    source_url = manifest.get("source_url")
    if not _valid_url(source_url):
        errors.append("source_url must be a valid HTTP(S) URL")

    videos = manifest.get("videos")
    if not isinstance(videos, list) or not videos:
        errors.append("videos must be a non-empty JSON array")
        return errors

    seen_ids: set[str] = set()
    for index, video in enumerate(videos):
        prefix = f"videos[{index}]"
        if not isinstance(video, Mapping):
            errors.append(f"{prefix} must be a JSON object")
            continue

        video_id = video.get("id")
        if not isinstance(video_id, str) or not video_id.strip():
            errors.append(f"{prefix}.id must be a non-empty string")
        elif video_id in seen_ids:
            errors.append(f"{prefix}.id duplicates video id {video_id!r}")
        else:
            seen_ids.add(video_id)

        if not isinstance(video.get("title"), str) or not video["title"].strip():
            errors.append(f"{prefix}.title must be a non-empty string")
        if not _valid_url(video.get("url")):
            errors.append(f"{prefix}.url must be a valid HTTP(S) URL")

    return errors
