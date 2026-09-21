"""Command-line interface for media-distillation-toolkit."""

import argparse
import json
import sys
from pathlib import Path

from .manifest import validate_manifest
from .transcript import render_transcript


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read JSON from {path}: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="micio-distill")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate a playlist manifest")
    validate_parser.add_argument("manifest", type=Path)

    render_parser = subparsers.add_parser("render", help="render a transcript as Markdown")
    render_parser.add_argument("transcript", type=Path)
    render_parser.add_argument("--output", required=True, type=Path)

    args = parser.parse_args(argv)
    try:
        data = _read_json(args.manifest if args.command == "validate" else args.transcript)
        if args.command == "validate":
            errors = validate_manifest(data)
            if errors:
                for error in errors:
                    print(f"invalid: {error}", file=sys.stderr)
                return 1
            print(f"valid: {args.manifest}")
            return 0

        args.output.write_text(render_transcript(data), encoding="utf-8")
        print(f"rendered: {args.output}")
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
