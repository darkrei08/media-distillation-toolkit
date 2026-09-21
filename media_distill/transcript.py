"""Deterministic Markdown rendering for a small transcript JSON format."""

from collections.abc import Mapping


def _segments(transcript: object) -> list[object]:
    if isinstance(transcript, list):
        return transcript
    if isinstance(transcript, Mapping) and isinstance(transcript.get("segments"), list):
        return transcript["segments"]
    raise ValueError("transcript must be a JSON array or an object with a segments array")


def render_transcript(transcript: object) -> str:
    """Render transcript segments without adding text that is absent from the input."""
    lines = ["# Transcript", ""]
    for index, segment in enumerate(_segments(transcript)):
        if not isinstance(segment, Mapping):
            raise ValueError(f"segments[{index}] must be a JSON object")
        text = segment.get("text")
        if not isinstance(text, str):
            raise ValueError(f"segments[{index}].text must be a string")

        label = ""
        if "timestamp" in segment:
            label = f"[{segment['timestamp']}] "
        elif "start" in segment:
            label = f"[{segment['start']}] "
        speaker = segment.get("speaker")
        if speaker is not None:
            if not isinstance(speaker, str):
                raise ValueError(f"segments[{index}].speaker must be a string")
            label += f"**{speaker}:** "
        lines.append(f"- {label}{text}")

    return "\n".join(lines) + "\n"
