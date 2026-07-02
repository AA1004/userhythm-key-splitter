from __future__ import annotations

import argparse
from pathlib import Path

from .analyzer import AnalyzeOptions, analyze_to_file
from .dataset import (
    analyze_dataset,
    export_training,
    init_dataset,
    match_dataset,
    scan_audio,
    scan_charts,
)


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

    dataset_parser = subparsers.add_parser("dataset", help="Build chart/audio datasets for future model training.")
    dataset_subparsers = dataset_parser.add_subparsers(dest="dataset_command", required=True)

    dataset_init = dataset_subparsers.add_parser("init", help="Create a dataset workspace.")
    dataset_init.add_argument("dataset", type=Path, help="Dataset directory.")

    dataset_scan_charts = dataset_subparsers.add_parser("scan-charts", help="Scan Userhythm chart JSON files.")
    dataset_scan_charts.add_argument("dataset", type=Path, help="Dataset directory.")
    dataset_scan_charts.add_argument("charts_dir", type=Path, help="Directory containing chart JSON files.")

    dataset_scan_audio = dataset_subparsers.add_parser("scan-audio", help="Scan local audio files.")
    dataset_scan_audio.add_argument("dataset", type=Path, help="Dataset directory.")
    dataset_scan_audio.add_argument("audio_dir", type=Path, help="Directory containing local audio files.")

    dataset_match = dataset_subparsers.add_parser("match", help="Match charts to scanned local audio files.")
    dataset_match.add_argument("dataset", type=Path, help="Dataset directory.")
    dataset_match.add_argument("--accept-threshold", type=float, default=0.68, help="Auto-confirm threshold, 0.0~1.0.")

    dataset_analyze = dataset_subparsers.add_parser("analyze", help="Analyze confirmed chart/audio pairs.")
    dataset_analyze.add_argument("dataset", type=Path, help="Dataset directory.")
    dataset_analyze.add_argument("--mode", choices=["fast", "balanced", "detailed"], default="balanced")
    dataset_analyze.add_argument("--sensitivity", type=float, default=0.65, help="0.05~0.95. Higher means more onsets.")
    dataset_analyze.add_argument("--min-gap-ms", type=float, default=60.0, help="Minimum gap between onset markers.")
    dataset_analyze.add_argument("--overwrite", action="store_true", help="Re-analyze even if analysis JSON already exists.")

    dataset_export = dataset_subparsers.add_parser("export-training", help="Export onset-to-note labels as JSONL.")
    dataset_export.add_argument("dataset", type=Path, help="Dataset directory.")
    dataset_export.add_argument("--output", "-o", type=Path, default=None, help="Output JSONL path.")
    dataset_export.add_argument("--hit-window-ms", type=float, default=80.0, help="Nearest-note label window.")

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

    if args.command == "dataset":
        if args.dataset_command == "init":
            manifest = init_dataset(args.dataset)
            print(f"Dataset ready: {manifest}")
            return
        if args.dataset_command == "scan-charts":
            count = scan_charts(args.dataset, args.charts_dir)
            print(f"Scanned {count} chart file(s).")
            return
        if args.dataset_command == "scan-audio":
            count = scan_audio(args.dataset, args.audio_dir)
            print(f"Scanned {count} audio file(s).")
            return
        if args.dataset_command == "match":
            pairs = match_dataset(args.dataset, accept_threshold=args.accept_threshold)
            confirmed = sum(1 for pair in pairs if pair.get("confirmed"))
            print(f"Matched {len(pairs)} pair(s), auto-confirmed {confirmed}.")
            return
        if args.dataset_command == "analyze":
            count = analyze_dataset(
                args.dataset,
                mode=args.mode,
                sensitivity=args.sensitivity,
                min_gap_ms=args.min_gap_ms,
                overwrite=args.overwrite,
            )
            print(f"Analyzed {count} confirmed pair(s).")
            return
        if args.dataset_command == "export-training":
            output = export_training(args.dataset, output_path=args.output, hit_window_ms=args.hit_window_ms)
            print(f"Wrote training labels: {output}")
            return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
