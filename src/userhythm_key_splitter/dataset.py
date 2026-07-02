from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .analyzer import AnalyzeOptions, analyze_to_file

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}
DATASET_FILE = "dataset.json"


@dataclass(frozen=True)
class DatasetPaths:
    root: Path

    @property
    def manifest(self) -> Path:
        return self.root / DATASET_FILE

    @property
    def analysis_dir(self) -> Path:
        return self.root / "analysis"

    @property
    def training_dir(self) -> Path:
        return self.root / "training"


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z가-힣]+", "-", value.strip().lower()).strip("-")
    return normalized or "untitled"


def _search_text(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\([^)]*\)|\[[^]]*\]", " ", value)
    value = re.sub(r"[^0-9a-zA-Z가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_manifest(dataset_root: Path) -> dict[str, Any]:
    paths = DatasetPaths(dataset_root.expanduser().resolve())
    if not paths.manifest.exists():
        raise FileNotFoundError(f"Dataset manifest not found: {paths.manifest}. Run dataset init first.")
    return _read_json(paths.manifest)


def _save_manifest(dataset_root: Path, manifest: dict[str, Any]) -> None:
    _write_json(DatasetPaths(dataset_root.expanduser().resolve()).manifest, manifest)


def init_dataset(dataset_root: Path) -> Path:
    paths = DatasetPaths(dataset_root.expanduser().resolve())
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.analysis_dir.mkdir(parents=True, exist_ok=True)
    paths.training_dir.mkdir(parents=True, exist_ok=True)

    if paths.manifest.exists():
        return paths.manifest

    _write_json(
        paths.manifest,
        {
            "version": 1,
            "charts": [],
            "audio": [],
            "pairs": [],
        },
    )
    return paths.manifest


def _extract_chart(raw: Any) -> dict[str, Any] | None:
    chart = raw.get("chart") if isinstance(raw, dict) and isinstance(raw.get("chart"), dict) else raw
    if not isinstance(chart, dict):
        return None
    notes = chart.get("notes")
    if not isinstance(notes, list):
        return None
    return chart


def scan_charts(dataset_root: Path, charts_dir: Path) -> int:
    manifest = _load_manifest(dataset_root)
    by_path = {item["path"]: item for item in manifest.get("charts", []) if isinstance(item, dict)}

    count = 0
    for path in sorted(charts_dir.expanduser().resolve().rglob("*.json")):
        try:
            chart = _extract_chart(_read_json(path))
        except Exception:
            continue
        if not chart:
            continue

        title = str(chart.get("chartTitle") or chart.get("title") or path.stem)
        author = str(chart.get("chartAuthor") or chart.get("author") or "")
        notes = chart.get("notes") if isinstance(chart.get("notes"), list) else []
        note_count = len(notes)
        hold_count = sum(1 for note in notes if isinstance(note, dict) and (note.get("type") == "hold" or float(note.get("duration") or 0) > 0))
        chart_id = _slugify(f"{title}-{path.stem}")
        item = {
            "id": chart_id,
            "title": title,
            "author": author,
            "path": str(path),
            "bpm": chart.get("bpm"),
            "youtubeUrl": chart.get("youtubeUrl"),
            "youtubeVideoId": chart.get("youtubeVideoId"),
            "noteCount": note_count,
            "holdCount": hold_count,
            "searchText": _search_text(f"{title} {author} {path.stem}"),
        }
        by_path[str(path)] = item
        count += 1

    manifest["charts"] = sorted(by_path.values(), key=lambda item: item["title"].lower())
    _save_manifest(dataset_root, manifest)
    return count


def scan_audio(dataset_root: Path, audio_dir: Path) -> int:
    manifest = _load_manifest(dataset_root)
    by_path = {item["path"]: item for item in manifest.get("audio", []) if isinstance(item, dict)}

    count = 0
    for path in sorted(audio_dir.expanduser().resolve().rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        title = path.stem
        item = {
            "id": _slugify(title),
            "title": title,
            "path": str(path),
            "extension": path.suffix.lower(),
            "searchText": _search_text(title),
        }
        by_path[str(path)] = item
        count += 1

    manifest["audio"] = sorted(by_path.values(), key=lambda item: item["title"].lower())
    _save_manifest(dataset_root, manifest)
    return count


def match_dataset(dataset_root: Path, accept_threshold: float = 0.68) -> list[dict[str, Any]]:
    manifest = _load_manifest(dataset_root)
    charts = manifest.get("charts", [])
    audios = manifest.get("audio", [])
    existing_by_chart = {item.get("chartId"): item for item in manifest.get("pairs", []) if isinstance(item, dict)}
    pairs: list[dict[str, Any]] = []

    for chart in charts:
        if not isinstance(chart, dict):
            continue
        best_audio = None
        best_score = 0.0
        chart_text = chart.get("searchText") or _search_text(chart.get("title", ""))
        for audio in audios:
            if not isinstance(audio, dict):
                continue
            audio_text = audio.get("searchText") or _search_text(audio.get("title", ""))
            score = SequenceMatcher(None, chart_text, audio_text).ratio()
            if chart_text and audio_text and (chart_text in audio_text or audio_text in chart_text):
                score = max(score, 0.88)
            if score > best_score:
                best_score = score
                best_audio = audio

        previous = existing_by_chart.get(chart.get("id"), {})
        pair_id = previous.get("id") or _slugify(str(chart.get("title") or chart.get("id") or "pair"))
        pair = {
            "id": pair_id,
            "chartId": chart.get("id"),
            "audioId": best_audio.get("id") if best_audio else None,
            "confidence": round(best_score, 4),
            "confirmed": bool(best_audio and best_score >= accept_threshold),
            "analysisPath": previous.get("analysisPath"),
        }
        pairs.append(pair)

    manifest["pairs"] = pairs
    _save_manifest(dataset_root, manifest)
    return pairs


def _find_by_id(items: list[Any], item_id: str | None) -> dict[str, Any] | None:
    if not item_id:
        return None
    for item in items:
        if isinstance(item, dict) and item.get("id") == item_id:
            return item
    return None


def analyze_dataset(
    dataset_root: Path,
    *,
    mode: str = "balanced",
    sensitivity: float = 0.65,
    min_gap_ms: float = 60.0,
    overwrite: bool = False,
) -> int:
    paths = DatasetPaths(dataset_root.expanduser().resolve())
    manifest = _load_manifest(paths.root)
    charts = manifest.get("charts", [])
    audios = manifest.get("audio", [])
    pairs = manifest.get("pairs", [])

    analyzed = 0
    for pair in pairs:
        if not isinstance(pair, dict) or not pair.get("confirmed"):
            continue
        chart = _find_by_id(charts, pair.get("chartId"))
        audio = _find_by_id(audios, pair.get("audioId"))
        if not chart or not audio:
            continue

        output_path = paths.analysis_dir / f"{pair['id']}.userhythm-analysis.json"
        if output_path.exists() and not overwrite:
            pair["analysisPath"] = str(output_path)
            continue

        bpm_value = chart.get("bpm")
        bpm = float(bpm_value) if isinstance(bpm_value, (int, float)) else None
        analyze_to_file(
            AnalyzeOptions(
                input_path=Path(audio["path"]),
                output_path=output_path,
                bpm=bpm,
                sensitivity=sensitivity,
                min_gap_ms=min_gap_ms,
                mode=mode,  # type: ignore[arg-type]
            )
        )
        pair["analysisPath"] = str(output_path)
        analyzed += 1

    manifest["pairs"] = pairs
    _save_manifest(paths.root, manifest)
    return analyzed


def _load_chart_notes(chart_path: Path) -> list[dict[str, Any]]:
    chart = _extract_chart(_read_json(chart_path))
    if not chart:
        return []
    return [note for note in chart.get("notes", []) if isinstance(note, dict)]


def export_training(dataset_root: Path, output_path: Path | None = None, hit_window_ms: float = 80.0) -> Path:
    paths = DatasetPaths(dataset_root.expanduser().resolve())
    manifest = _load_manifest(paths.root)
    charts = manifest.get("charts", [])
    pairs = manifest.get("pairs", [])
    output = output_path.expanduser().resolve() if output_path else paths.training_dir / "onset-note-labels.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)

    rows = 0
    with output.open("w", encoding="utf-8") as fp:
        for pair in pairs:
            if not isinstance(pair, dict) or not pair.get("analysisPath"):
                continue
            chart = _find_by_id(charts, pair.get("chartId"))
            if not chart:
                continue
            analysis_path = Path(pair["analysisPath"])
            if not analysis_path.exists():
                continue
            analysis = _read_json(analysis_path)
            notes = _load_chart_notes(Path(chart["path"]))
            note_times = [float(note.get("time") or 0) for note in notes]

            for onset in analysis.get("onsets", []) if isinstance(analysis, dict) else []:
                if not isinstance(onset, dict):
                    continue
                onset_time = float(onset.get("timeMs") or 0)
                nearest_note = None
                nearest_delta = None
                for note, note_time in zip(notes, note_times):
                    delta = abs(note_time - onset_time)
                    if nearest_delta is None or delta < nearest_delta:
                        nearest_delta = delta
                        nearest_note = note
                has_note = nearest_delta is not None and nearest_delta <= hit_window_ms
                row = {
                    "pairId": pair.get("id"),
                    "chartId": chart.get("id"),
                    "timeMs": onset_time,
                    "strength": onset.get("strength"),
                    "band": onset.get("band"),
                    "type": onset.get("type"),
                    "confidence": onset.get("confidence"),
                    "hasNote": has_note,
                    "nearestDeltaMs": round(float(nearest_delta), 3) if nearest_delta is not None else None,
                    "lane": nearest_note.get("lane") if has_note and nearest_note else None,
                    "noteType": nearest_note.get("type") if has_note and nearest_note else None,
                    "duration": nearest_note.get("duration") if has_note and nearest_note else None,
                }
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")
                rows += 1

    return output
