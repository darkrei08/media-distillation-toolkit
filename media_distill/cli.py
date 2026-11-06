"""Command-line interface for media-distillation-toolkit."""

import argparse
import json
import sys
from pathlib import Path

from .manifest import validate_manifest
from .reconcile import reconcile
from .transcript import render_transcript
from .ytptube import HISTORY, QUEUE, YTPTubeClient, YTPTubeError


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read JSON from {path}: {error}") from error


def _write_manifest(manifest: object, path: Path) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _emit(message: str, *, err: bool = False) -> None:
    stream = sys.stderr if err else sys.stdout
    stream.write(f"{message}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="micio-distill")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate a playlist manifest")
    validate_parser.add_argument("manifest", type=Path)

    render_parser = subparsers.add_parser("render", help="render a transcript as Markdown")
    render_parser.add_argument("transcript", type=Path)
    render_parser.add_argument("--output", required=True, type=Path)

    enqueue_parser = subparsers.add_parser("enqueue", help="enqueue URLs in YTPTube")
    enqueue_parser.add_argument("urls", nargs="+", metavar="URL")

    reconcile_parser = subparsers.add_parser("reconcile", help="apply YTPTube history to a manifest")
    reconcile_parser.add_argument("manifest", type=Path)
    reconcile_parser.add_argument("--output", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "enqueue":
            _emit(f"enqueued: {YTPTubeClient().submit(args.urls)}")
            return 0

        if args.command == "reconcile":
            manifest = _read_json(args.manifest)
            if not isinstance(manifest, dict):
                _emit("invalid: manifest must be a JSON object", err=True)
                return 1
            errors = validate_manifest(manifest)
            if errors:
                for error in errors:
                    _emit(f"invalid: {error}", err=True)
                return 1
            client = YTPTubeClient()
            # Both stores: an item in flight is neither a completion nor an absence.
            items = client.list_items(QUEUE) + client.list_items(HISTORY)
            result = reconcile(manifest, items)
            output = args.output or args.manifest
            _write_manifest(result, output)
            _emit(f"reconciled: {output}")
            return 0

        data = _read_json(args.manifest if args.command == "validate" else args.transcript)
        if args.command == "validate":
            errors = validate_manifest(data)
            if errors:
                for error in errors:
                    _emit(f"invalid: {error}", err=True)
                return 1
            _emit(f"valid: {args.manifest}")
            return 0

        args.output.write_text(render_transcript(data), encoding="utf-8")
        _emit(f"rendered: {args.output}")
        return 0
    except (OSError, ValueError, YTPTubeError) as error:
        _emit(f"error: {error}", err=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
