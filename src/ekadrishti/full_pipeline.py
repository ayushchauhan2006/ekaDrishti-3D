"""Run the complete AI-assisted, metric EkaDrishti presentation workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import cv2

from .accuracy_validation import pending_report, validate_csv
from .finalize_model import finalize


PROFILES = {
    "rapid": {"dense_max_image_size": 960, "poisson_depth": 9},
    "precision": {"dense_max_image_size": 1600, "poisson_depth": 11},
}


def _stream(command: list[str], *, cwd: Path) -> float:
    started = time.perf_counter()
    process = subprocess.Popen(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert process.stdout is not None
    for line in process.stdout:
        print(line.rstrip(), flush=True)
    if process.wait() != 0:
        raise RuntimeError(f"Pipeline command failed with exit code {process.returncode}: {' '.join(command)}")
    return time.perf_counter() - started


def _video_duration(path: Path) -> float:
    capture = cv2.VideoCapture(str(path))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frames = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    capture.release()
    return frames / fps if fps > 0 else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and publish a complete SIH-ready EkaDrishti mission.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--publish-directory", type=Path, help="Directory where this profile's browser assets are published")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="precision")
    parser.add_argument("--interval-seconds", type=float)
    parser.add_argument("--use-gpu", action="store_true")
    parser.add_argument("--disable-ai-masking", action="store_true")
    parser.add_argument("--sparse-model", type=Path, help="Resume finalization from an existing COLMAP sparse model")
    parser.add_argument("--checkpoints", type=Path, help="Independent checkpoints or reference dimensions CSV")
    args = parser.parse_args()

    started = time.perf_counter()
    project_root, workspace = args.project_root.resolve(), args.workspace.resolve()
    publish_directory = (args.publish_directory or (project_root / "dashboard/dist/assets")).resolve()
    video, telemetry = args.video.resolve(), args.telemetry.resolve()
    outputs = workspace / "outputs"
    report_path = outputs / "reconstruction_report.json"
    timings: dict[str, float] = {}
    if args.sparse_model is None:
        command = [
            sys.executable, "-u", "-m", "src.ekadrishti.reconstruct", "--video", str(video),
            "--telemetry", str(telemetry), "--workspace", str(workspace), "--project-root", str(project_root),
            "--profile", args.profile,
        ]
        if args.interval_seconds is not None:
            command.extend(["--interval-seconds", str(args.interval_seconds)])
        if args.use_gpu:
            command.append("--use-gpu")
        if args.disable_ai_masking:
            command.append("--disable-ai-masking")
        timings["sparse_pipeline"] = _stream(command, cwd=project_root)
        sparse_report = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        sparse_model = args.sparse_model.resolve()
        if not (sparse_model / "images.bin").is_file():
            parser.error(f"Sparse model is missing images.bin: {sparse_model}")
        manifest = json.loads((outputs / "frame_manifest.json").read_text(encoding="utf-8"))
        masked = workspace / "frames/ai_masked"
        selected = workspace / "frames/selected"
        sparse_report = {
            "frames_selected": manifest["frames_selected"], "model_directory": str(sparse_model),
            "reconstruction_frames": str(masked if masked.is_dir() else selected),
            "ai_dynamic_masking": {"status": "not_recorded_for_resumed_model"},
        }

    print("STEP: Creating verified metric presentation package", flush=True)
    finalization_started = time.perf_counter()
    presentation_directory = outputs / "presentation"
    presentation = finalize(
        sparse_model=Path(sparse_report["model_directory"]), video=video, telemetry=telemetry,
        output_directory=presentation_directory, publish_directory=publish_directory,
    )
    timings["metric_finalization"] = time.perf_counter() - finalization_started

    print(f"STEP: Building {args.profile} dense photo-textured metric model with GPU", flush=True)
    profile = PROFILES[args.profile]
    timings["dense_pipeline"] = _stream([
        sys.executable, "-u", "-m", "src.ekadrishti.build_dense_cuda",
        "--images", sparse_report["reconstruction_frames"],
        "--sparse-model", str(presentation_directory / "aligned_model"),
        "--workspace", str(workspace), "--project-root", str(project_root),
        "--alignment-report", str(presentation_directory / "presentation_report.json"),
        "--max-image-size", str(profile["dense_max_image_size"]), "--poisson-depth", str(profile["poisson_depth"]),
    ], cwd=project_root)

    dense = workspace / "dense"
    assets = publish_directory
    timings["browser_cloud_export"] = _stream([
        sys.executable, "-m", "src.ekadrishti.prepare_viewer_cloud", "--input", str(dense / "fused.ply"),
        "--output", str(assets / "dense_point_cloud.ply"), "--max-points", "750000",
    ], cwd=project_root)
    shutil.copy2(dense / "textured/mesh.ply", assets / "dense_textured_mesh.ply")
    shutil.copy2(dense / "textured/texture.png", assets / "dense_texture.png")
    shutil.copy2(dense / "dense_report.json", assets / "dense_report.json")

    accuracy = validate_csv(args.checkpoints.resolve()) if args.checkpoints else pending_report()
    (outputs / "accuracy_validation.json").write_text(json.dumps(accuracy, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(outputs / "accuracy_validation.json", assets / "accuracy_validation.json")
    dense_report = json.loads((dense / "dense_report.json").read_text(encoding="utf-8"))
    total_seconds = time.perf_counter() - started
    duration = _video_duration(video)
    benchmark = {
        "profile": args.profile, "video_duration_seconds": round(duration, 2),
        "pipeline_seconds": round(total_seconds, 2),
        "processing_to_video_ratio": round(total_seconds / duration, 2) if duration else None,
        "near_real_time": bool(duration and total_seconds <= duration * 2),
        "stages_seconds": {key: round(value, 2) for key, value in timings.items()},
    }
    combined = {
        **presentation, "status": "full_metric_textured_model_ready", "profile": args.profile,
        "frames_selected": sparse_report["frames_selected"], "ai_dynamic_masking": sparse_report.get("ai_dynamic_masking", {}),
        "model_directory": sparse_report["model_directory"], "metric_sparse_model": str(presentation_directory / "aligned_model"),
        "presentation_directory": str(presentation_directory), "dense": dense_report,
        "dense_point_cloud": str(dense / "fused.ply"), "textured_mesh": str(dense / "textured/mesh.ply"),
        "accuracy_validation": accuracy, "benchmark": benchmark,
        "textured_viewer": "http://127.0.0.1:4173/textured_viewer.html",
        "dashboard": "http://127.0.0.1:4173/",
    }
    report_path.write_text(json.dumps(combined, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(report_path, assets / "mission_report.json")
    print("STEP: Full AI-assisted metric 3D presentation ready", flush=True)
    print(json.dumps(combined, indent=2), flush=True)


if __name__ == "__main__":
    main()
