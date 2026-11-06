"""Parse WebVTT and SRT subtitle files into the transcript JSON format."""

import re


_TIMING_RE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2})[.,]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[.,]\d{3}"
)
# NOTE: MM:SS.mmm without an hour field is legal WebVTT and is rejected here;
# add it when a non-YouTube source needs it.
_TAG_RE = re.compile(r"<[^>]+>")
_HEADER_LINE_RE = re.compile(
    r"^(WEBVTT|Kind:|Language:|X-TIMESTAMP-MAP|NOTE)( |$)", re.IGNORECASE
)
_CUE_INDEX_RE = re.compile(r"^\d+$")
_WHITESPACE_RE = re.compile(r"\s+")


def parse_subtitles(text: str) -> dict[str, list[dict[str, str]]]:
    """Parse WebVTT or SRT text into ``{"segments": [{"start": ..., "text": ...}]}``."""
    if not isinstance(text, str):
        raise ValueError("input must be a string")

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    segments: list[dict[str, str]] = []
    prev_text: str | None = None
    i = 0

    # Skip leading header lines and NOTE blocks.
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if _HEADER_LINE_RE.match(line):
            # NOTE blocks span until the next blank line.
            if line.startswith("NOTE"):
                i += 1
                while i < len(lines) and lines[i].strip():
                    i += 1
            else:
                i += 1
            continue
        break

    while i < len(lines):
        line = lines[i].strip()

        # Skip blank lines and standalone cue index lines.
        if not line:
            i += 1
            continue
        if _CUE_INDEX_RE.match(line):
            i += 1
            continue

        # Expect a timing line.
        m = _TIMING_RE.match(line)
        if not m:
            raise ValueError(f"malformed timing line: {line!r}")

        raw_start = m.group(1)
        # Normalize to HH:MM:SS with zero padding.
        parts = raw_start.split(":")
        start = ":".join(p.zfill(2) for p in parts)

        i += 1

        # Collect payload lines until blank line or end.
        payload_parts: list[str] = []
        while i < len(lines) and lines[i].strip():
            payload_parts.append(lines[i].strip())
            i += 1

        payload = " ".join(payload_parts)
        # Strip markup tags.
        payload = _TAG_RE.sub("", payload)
        # Collapse whitespace.
        payload = _WHITESPACE_RE.sub(" ", payload).strip()

        if not payload:
            continue

        # Deduplicate rolling auto-caption repetition.
        if prev_text is not None:
            if payload == prev_text:
                continue
            if payload.startswith(prev_text + " "):
                payload = payload[len(prev_text) + 1:]
                if not payload:
                    continue

        segments.append({"start": start, "text": payload})
        prev_text = payload

    if not segments:
        raise ValueError("no cues found in subtitle input")

    return {"segments": segments}
