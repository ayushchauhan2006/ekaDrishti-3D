"""Parse per-frame DJI SRT flight telemetry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class FrameTelemetry:
    frame: int
    recorded_at: str | None
    latitude: float | None
    longitude: float | None
    relative_altitude_m: float | None
    absolute_altitude_m: float | None
    drone_yaw_deg: float | None
    drone_pitch_deg: float | None
    drone_roll_deg: float | None
    gimbal_yaw_deg: float | None
    gimbal_pitch_deg: float | None
    gimbal_roll_deg: float | None


def _number(block: str, name: str) -> float | None:
    match = re.search(rf"\b{re.escape(name)}:\s*(-?\d+(?:\.\d+)?)", block)
    return float(match.group(1)) if match else None


def _triplet(block: str, name: str) -> tuple[float | None, float | None, float | None]:
    """Read DJI attitude values such as ``F.PRY (1.0°, 2.0°, 3.0°)``."""
    match = re.search(
        rf"\b{re.escape(name)}\s*\(\s*(-?\d+(?:\.\d+)?)°?\s*,\s*"
        rf"(-?\d+(?:\.\d+)?)°?\s*,\s*(-?\d+(?:\.\d+)?)°?\s*\)",
        block,
    )
    return tuple(map(float, match.groups())) if match else (None, None, None)


def _srt_seconds(timestamp: str) -> float:
    hours, minutes, seconds = timestamp.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _parse_rtk_srt(text: str) -> list[FrameTelemetry]:
    """Parse DJI Phantom RTK-style SRT files, which contain one row per second."""
    blocks = re.finditer(
        r"(?ms)^\s*\d+\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->.*?\n(.*?)(?=\n\s*\d+\s*\n|\Z)",
        text,
    )
    records: list[FrameTelemetry] = []
    for block in blocks:
        recorded_at, payload = block.groups()
        rtk = re.search(
            r"\b(?:RTK|GPS)\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*"
            r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)",
            payload,
        )
        if not rtk:
            continue
        drone_pitch, drone_roll, drone_yaw = _triplet(payload, "F.PRY")
        gimbal_pitch, gimbal_roll, gimbal_yaw = _triplet(payload, "G.PRY")
        height = re.search(r"\bH\s+(-?\d+(?:\.\d+)?)m", payload)
        # DJI RTK SRT timestamps are second-based. Their source video is 29.97/30 fps.
        frame = round(_srt_seconds(recorded_at) * 29.97) + 1
        records.append(
            FrameTelemetry(
                frame=frame, recorded_at=recorded_at,
                latitude=float(rtk.group(2)), longitude=float(rtk.group(1)),
                relative_altitude_m=float(height.group(1)) if height else None,
                absolute_altitude_m=float(rtk.group(3)),
                drone_yaw_deg=drone_yaw, drone_pitch_deg=drone_pitch, drone_roll_deg=drone_roll,
                gimbal_yaw_deg=gimbal_yaw, gimbal_pitch_deg=gimbal_pitch, gimbal_roll_deg=gimbal_roll,
            )
        )
    return records


def parse_dji_srt(path: Path) -> list[FrameTelemetry]:
    """Return per-frame telemetry from a DJI subtitle/telemetry file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    frame_starts = list(re.finditer(r"FrameCnt:\s*(\d+)", text))
    records: list[FrameTelemetry] = []
    if not frame_starts:
        return _parse_rtk_srt(text)

    for index, start in enumerate(frame_starts):
        end = frame_starts[index + 1].start() if index + 1 < len(frame_starts) else len(text)
        block = text[start.start() : end]
        timestamp = re.search(r"\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?", block)
        altitudes = re.search(
            r"\[latitude:.*?\[rel_alt:\s*(-?\d+(?:\.\d+)?)\s+abs_alt:\s*(-?\d+(?:\.\d+)?)\]",
            block,
            flags=re.DOTALL,
        )
        records.append(
            FrameTelemetry(
                frame=int(start.group(1)),
                recorded_at=timestamp.group(0) if timestamp else None,
                latitude=_number(block, "latitude"),
                longitude=_number(block, "longitude"),
                relative_altitude_m=float(altitudes.group(1)) if altitudes else None,
                absolute_altitude_m=float(altitudes.group(2)) if altitudes else None,
                drone_yaw_deg=_number(block, "drone_yaw"),
                drone_pitch_deg=_number(block, "drone_pitch"),
                drone_roll_deg=_number(block, "drone_roll"),
                gimbal_yaw_deg=_number(block, "gb_yaw"),
                gimbal_pitch_deg=_number(block, "gb_pitch"),
                gimbal_roll_deg=_number(block, "gb_roll"),
            )
        )
    return records


def record_as_dict(record: FrameTelemetry) -> dict[str, object]:
    """Serialize a telemetry record for JSON output."""
    return asdict(record)
