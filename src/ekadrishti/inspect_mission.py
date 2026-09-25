"""Create a small, human-readable mission report from video and SRT inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .telemetry import parse_dji_srt, record_as_dict


def _range(values: list[float | None]) -> dict[str, float] | None:
    available = [value for value in values if value is not None]
    if not available:
        return None
    return {"min": min(available), "max": max(available)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect an EkaDrishti drone mission.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("outputs/mission_report.json"))
    args = parser.parse_args()

    if not args.video.is_file():
        parser.error(f"Video not found: {args.video}")
    if not args.telemetry.is_file():
        parser.error(f"Telemetry not found: {args.telemetry}")

    records = parse_dji_srt(args.telemetry)
    if not records:
        parser.error("No DJI FrameCnt entries were found in the telemetry file.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "input": {
            "video": str(args.video),
            "video_size_bytes": args.video.stat().st_size,
            "telemetry": str(args.telemetry),
        },
        "telemetry": {
            "records": len(records),
            "first_timestamp": records[0].recorded_at,
            "last_timestamp": records[-1].recorded_at,
            "latitude": _range([record.latitude for record in records]),
            "longitude": _range([record.longitude for record in records]),
            "relative_altitude_m": _range([record.relative_altitude_m for record in records]),
            "absolute_altitude_m": _range([record.absolute_altitude_m for record in records]),
            "sample": record_as_dict(records[0]),
        },
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nMission report written to {args.output}")


if __name__ == "__main__":
    main()
