"""CLI for selecting useful reconstruction frames from a DJI mission video."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .frame_selection import candidate_as_dict, select_reconstruction_frames
from .telemetry import parse_dji_srt, record_as_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Select quality frames for EkaDrishti reconstruction.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, default=Path("data/frames/selected"))
    parser.add_argument("--manifest", type=Path, default=Path("outputs/frame_manifest.json"))
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--minimum-blur-score", type=float, default=60.0)
    args = parser.parse_args()

    if not args.video.is_file() or not args.telemetry.is_file():
        parser.error("Both --video and --telemetry must point to existing files.")

    candidates = select_reconstruction_frames(
        video_path=args.video,
        output_directory=args.output_directory,
        interval_seconds=args.interval_seconds,
        minimum_blur_score=args.minimum_blur_score,
    )
    telemetry_by_frame = {record.frame: record for record in parse_dji_srt(args.telemetry)}
    frames = []
    for candidate in candidates:
        item = candidate_as_dict(candidate)
        telemetry = telemetry_by_frame.get(candidate.frame_index + 1)
        item["telemetry"] = record_as_dict(telemetry) if telemetry else None
        frames.append(item)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "video": str(args.video),
        "sampling_interval_seconds": args.interval_seconds,
        "candidates_examined": len(frames),
        "frames_selected": sum(item["selected"] for item in frames),
        "frames": frames,
    }
    args.manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"Selected {report['frames_selected']} of {report['candidates_examined']} sampled frames.\n"
        f"Manifest: {args.manifest}\nFrames: {args.output_directory}"
    )


if __name__ == "__main__":
    main()
