from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Mode = Literal["fast", "balanced", "detailed"]

ANALYZER_VERSION = "0.1.0"


@dataclass(frozen=True)
class AnalyzeOptions:
    input_path: Path
    output_path: Path | None = None
    bpm: float | None = None
    offset_ms: float = 0.0
    sensitivity: float = 0.65
    min_gap_ms: float = 60.0
    mode: Mode = "balanced"


def _load_dependencies():
    try:
        import librosa  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependencies. Run: pip install -e ."
        ) from exc
    return librosa, np


def _normalize(values: Any):
    max_value = float(values.max()) if values.size else 0.0
    if max_value <= 0:
        return values
    return values / max_value


def _classify_band(low: float, mid: float, high: float) -> str:
    values = {"low": low, "mid": mid, "high": high}
    best = max(values, key=values.get)
    if values[best] <= 0:
        return "unknown"
    if max(values.values()) - min(values.values()) < 0.08:
        return "wide"
    return best


def _thin_onsets(candidates: list[dict[str, Any]], min_gap_ms: float) -> list[dict[str, Any]]:
    if min_gap_ms <= 0:
        return candidates

    result: list[dict[str, Any]] = []
    for onset in sorted(candidates, key=lambda item: item["timeMs"]):
        if not result:
            result.append(onset)
            continue

        previous = result[-1]
        if onset["timeMs"] - previous["timeMs"] >= min_gap_ms:
            result.append(onset)
            continue

        if onset.get("strength", 0) > previous.get("strength", 0):
            result[-1] = onset

    return result


def _resolve_output_path(input_path: Path, output_path: Path | None) -> Path:
    if output_path is not None:
        return output_path.expanduser().resolve()
    return input_path.with_name(f"{input_path.stem}.userhythm-analysis.json")


def analyze(options: AnalyzeOptions) -> dict[str, Any]:
    librosa, np = _load_dependencies()

    input_path = options.input_path.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    hop_length = 256 if options.mode == "detailed" else 512
    y, sr = librosa.load(str(input_path), sr=None, mono=True)
    duration_ms = len(y) / sr * 1000

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    onset_env_norm = _normalize(onset_env)

    estimated_tempo, beat_frames = librosa.beat.beat_track(
        y=y,
        sr=sr,
        hop_length=hop_length,
        start_bpm=options.bpm if options.bpm else 120,
        tightness=100,
        trim=False,
    )
    if isinstance(estimated_tempo, np.ndarray):
        estimated_tempo = float(estimated_tempo[0]) if estimated_tempo.size else 0.0
    estimated_tempo = float(options.bpm if options.bpm else estimated_tempo)

    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length) * 1000 + options.offset_ms
    beats: list[dict[str, Any]] = []
    for index, time_ms in enumerate(beat_times):
        if time_ms < 0:
            continue
        frame = int(beat_frames[index])
        strength = float(onset_env_norm[frame]) if 0 <= frame < len(onset_env_norm) else 0.0
        beats.append(
            {
                "timeMs": round(float(time_ms), 3),
                "measure": int(index // 4 + 1),
                "beatInMeasure": int(index % 4 + 1),
                "strength": round(strength, 4),
                "confidence": round(min(1.0, 0.45 + strength * 0.55), 4),
            }
        )

    stft = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    low_mask = (freqs >= 20) & (freqs < 250)
    mid_mask = (freqs >= 250) & (freqs < 2500)
    high_mask = freqs >= 2500

    low_energy = _normalize(stft[low_mask].mean(axis=0)) if low_mask.any() else np.zeros(stft.shape[1])
    mid_energy = _normalize(stft[mid_mask].mean(axis=0)) if mid_mask.any() else np.zeros(stft.shape[1])
    high_energy = _normalize(stft[high_mask].mean(axis=0)) if high_mask.any() else np.zeros(stft.shape[1])

    onset_threshold = max(0.05, min(0.95, 1.0 - options.sensitivity))
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env,
        sr=sr,
        hop_length=hop_length,
        units="frames",
        backtrack=False,
        delta=onset_threshold,
    )

    onsets: list[dict[str, Any]] = []
    for frame in onset_frames:
        if frame < 0 or frame >= len(onset_env_norm):
            continue
        time_ms = float(librosa.frames_to_time(frame, sr=sr, hop_length=hop_length) * 1000 + options.offset_ms)
        if time_ms < 0:
            continue
        low = float(low_energy[min(frame, len(low_energy) - 1)])
        mid = float(mid_energy[min(frame, len(mid_energy) - 1)])
        high = float(high_energy[min(frame, len(high_energy) - 1)])
        strength = float(onset_env_norm[frame])
        band = _classify_band(low, mid, high)
        onsets.append(
            {
                "timeMs": round(time_ms, 3),
                "strength": round(strength, 4),
                "band": band,
                "type": "percussive" if strength >= 0.55 else "unknown",
                "confidence": round(min(1.0, 0.3 + strength * 0.7), 4),
            }
        )

    onsets = _thin_onsets(onsets, options.min_gap_ms)

    bands = []
    frame_step = 4 if options.mode == "fast" else 2
    frame_times = librosa.frames_to_time(np.arange(len(low_energy)), sr=sr, hop_length=hop_length) * 1000 + options.offset_ms
    for idx in range(0, len(frame_times), frame_step):
        start = float(frame_times[idx])
        if start < 0:
            continue
        end_idx = min(len(frame_times) - 1, idx + frame_step)
        bands.append(
            {
                "startMs": round(start, 3),
                "endMs": round(float(frame_times[end_idx]), 3),
                "low": round(float(low_energy[idx]), 4),
                "mid": round(float(mid_energy[idx]), 4),
                "high": round(float(high_energy[idx]), 4),
            }
        )

    section_ms = 8000
    sections = []
    section_count = max(1, math.ceil(duration_ms / section_ms))
    for section_index in range(section_count):
        start = section_index * section_ms
        end = min(duration_ms, start + section_ms)
        section_onsets = [item for item in onsets if start <= item["timeMs"] < end]
        density = len(section_onsets) / max(1, (end - start) / 1000)
        energy = sum(item.get("strength", 0) for item in section_onsets) / max(1, len(section_onsets))
        sections.append(
            {
                "startMs": round(start + options.offset_ms, 3),
                "endMs": round(end + options.offset_ms, 3),
                "label": "section",
                "energy": round(float(min(1, energy)), 4),
                "density": round(float(min(1, density / 8)), 4),
            }
        )

    return {
        "metadata": {
            "version": 1,
            "sourceFile": input_path.name,
            "durationMs": round(duration_ms, 3),
            "sampleRate": int(sr),
            "analyzer": "userhythm-key-splitter",
            "analyzerVersion": ANALYZER_VERSION,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "mode": options.mode,
        },
        "timing": {
            "estimatedBpm": round(float(estimated_tempo), 4),
            "bpmConfidence": 0.75 if options.bpm else 0.62,
            "firstBeatMs": beats[0]["timeMs"] if beats else None,
            "offsetMs": round(options.offset_ms, 3),
            "beatsPerMeasure": 4,
        },
        "beats": beats,
        "onsets": onsets,
        "bands": bands,
        "sections": sections,
    }


def analyze_to_file(options: AnalyzeOptions) -> Path:
    input_path = options.input_path.expanduser().resolve()
    output_path = _resolve_output_path(input_path, options.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = analyze(options)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
