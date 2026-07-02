from __future__ import annotations

import argparse
from pathlib import Path

from .analyzer import AnalyzeOptions, analyze_to_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="userhythm-key-splitter",
        description="Local audio analysis and key-sound candidate extraction for Userhythm.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Create .userhythm-analysis.json from an audio file.")
    analyze_parser.add_argument("input", type=Path, help="Audio file path, e.g. mp3/wav/flac.")
    analyze_parser.add_argument("--output", "-o", type=Path, default=None, help="Output JSON path.")
    analyze_parser.add_argument("--bpm", type=float, default=None, help="Manual BPM override.")
    analyze_parser.add_argument("--offset-ms", type=float, default=0.0, help="Shift analysis markers by milliseconds.")
    analyze_parser.add_argument("--sensitivity", type=float, default=0.65, help="0.05~0.95. Higher means more onsets.")
    analyze_parser.add_argument("--min-gap-ms", type=float, default=60.0, help="Minimum gap between onset markers.")
    analyze_parser.add_argument("--mode", choices=["fast", "balanced", "detailed"], default="balanced")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        output_path = analyze_to_file(
            AnalyzeOptions(
                input_path=args.input,
                output_path=args.output,
                bpm=args.bpm,
                offset_ms=args.offset_ms,
                sensitivity=args.sensitivity,
                min_gap_ms=args.min_gap_ms,
                mode=args.mode,
            )
        )
        print(f"Wrote {output_path}")
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
