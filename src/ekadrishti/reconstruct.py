"""Build a quality-filtered sparse 3D model from one drone video and telemetry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .dynamic_masking import copy_without_ai, mask_frames


PROFILES = {
    "rapid": {"interval_seconds": 1.0, "feature_size": 1280, "overlap": 8},
    "precision": {"interval_seconds": 0.5, "feature_size": 2000, "overlap": 15},
}


def _run(command: list[str], *, cwd: Path, label: str) -> float:
    print(f"STEP: {label}", flush=True)
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if completed.returncode:
        details = (completed.stdout + "\n" + completed.stderr).strip()
        raise RuntimeError(f"{label} failed.\n{details[-4000:]}")
    if completed.stdout.strip():
        print(completed.stdout.strip()[-1000:], flush=True)
    return time.perf_counter() - started


def _find_model(sparse_directory: Path) -> Path:
    candidates = sorted(
        (path for path in sparse_directory.iterdir() if path.is_dir() and (path / "images.bin").is_file()),
        key=lambda path: path.name,
    )
    if not candidates:
        raise RuntimeError("COLMAP finished without producing a registered sparse model.")
    return candidates[-1]


def _write_gps_reference(manifest_path: Path, output_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lines: list[str] = []
    for frame in manifest["frames"]:
        telemetry = frame.get("telemetry") or {}
        image = frame.get("image_path")
        values = (telemetry.get("latitude"), telemetry.get("longitude"), telemetry.get("absolute_altitude_m"))
        if frame.get("selected") and image and None not in values:
            lines.append(f"{Path(image).name} {values[0]} {values[1]} {values[2]}")
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run EkaDrishti's AI-assisted sparse reconstruction pipeline.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="precision")
    parser.add_argument("--interval-seconds", type=float, help="Override the selected profile's sampling interval")
    parser.add_argument("--use-gpu", action="store_true")
    parser.add_argument("--disable-ai-masking", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    video, telemetry = args.video.resolve(), args.telemetry.resolve()
    workspace, project_root = args.workspace.resolve(), args.project_root.resolve()
    if not video.is_file() or not telemetry.is_file():
        parser.error("Video and telemetry must be existing files.")
    profile = dict(PROFILES[args.profile])
    interval = args.interval_seconds if args.interval_seconds is not None else float(profile["interval_seconds"])
    cuda_colmap = project_root / "tools/colmap-cuda/build/src/colmap/exe/colmap"
    colmap = str(cuda_colmap) if args.use_gpu and cuda_colmap.is_file() else "colmap"
    if args.use_gpu and not cuda_colmap.is_file():
        parser.error(f"CUDA COLMAP build is missing: {cuda_colmap}")
    if shutil.which(colmap) is None and not Path(colmap).is_file():
        parser.error("COLMAP is not installed or is not available on PATH.")

    outputs = workspace / "outputs"
    selected_frames = workspace / "frames/selected"
    reconstruction_frames = workspace / "frames/ai_masked"
    manifest = outputs / "frame_manifest.json"
    mission_report = outputs / "mission_report.json"
    database = outputs / "database.db"
    sparse, export = outputs / "sparse", outputs / "export"
    outputs.mkdir(parents=True, exist_ok=True)
    sparse.mkdir(exist_ok=True)
    timings: dict[str, float] = {}

    timings["mission_inspection"] = _run(
        [sys.executable, "-m", "src.ekadrishti.inspect_mission", "--video", str(video), "--telemetry", str(telemetry), "--output", str(mission_report)],
        cwd=project_root, label="Inspecting video and flight telemetry",
    )
    timings["frame_selection"] = _run(
        [sys.executable, "-m", "src.ekadrishti.extract_frames", "--video", str(video), "--telemetry", str(telemetry),
         "--output-directory", str(selected_frames), "--manifest", str(manifest), "--interval-seconds", str(interval)],
        cwd=project_root, label="Selecting sharp reconstruction frames",
    )
    frame_report = json.loads(manifest.read_text(encoding="utf-8"))
    if frame_report["frames_selected"] < 8:
        raise RuntimeError("Fewer than eight usable frames were found; this video cannot produce a stable 3D model.")

    print("STEP: AI masking people, vehicles and animals", flush=True)
    ai_started = time.perf_counter()
    if args.disable_ai_masking:
        ai_report = copy_without_ai(selected_frames, reconstruction_frames)
    else:
        model_root = project_root / "assets/ai"
        ai_report = mask_frames(
            selected_frames, reconstruction_frames,
            config=model_root / "yolov4-tiny.cfg", weights=model_root / "yolov4-tiny.weights",
            labels_path=model_root / "coco.names",
        )
    timings["ai_dynamic_masking"] = time.perf_counter() - ai_started
    (outputs / "ai_mask_report.json").write_text(json.dumps(ai_report, indent=2) + "\n", encoding="utf-8")

    gpu_flag = "1" if args.use_gpu else "0"
    timings["feature_extraction"] = _run(
        [colmap, "feature_extractor", "--database_path", str(database), "--image_path", str(reconstruction_frames),
         "--ImageReader.single_camera", "1", "--FeatureExtraction.use_gpu", gpu_flag,
         "--FeatureExtraction.max_image_size", str(profile["feature_size"])],
        cwd=project_root, label="Finding visual features across AI-cleaned frames",
    )
    timings["feature_matching"] = _run(
        [colmap, "sequential_matcher", "--database_path", str(database), "--FeatureMatching.use_gpu", gpu_flag,
         "--FeatureMatching.num_threads", "1", "--SequentialMatching.overlap", str(profile["overlap"])],
        cwd=project_root, label="Matching overlapping video frames",
    )
    timings["sparse_mapping"] = _run(
        [colmap, "mapper", "--database_path", str(database), "--image_path", str(reconstruction_frames), "--output_path", str(sparse)],
        cwd=project_root, label="Building the sparse 3D point cloud",
    )
    model = _find_model(sparse)
    export.mkdir(parents=True, exist_ok=True)
    point_cloud = export / "sparse_point_cloud.ply"
    timings["sparse_export"] = _run(
        [colmap, "model_converter", "--input_path", str(model), "--output_path", str(point_cloud), "--output_type", "PLY"],
        cwd=project_root, label="Exporting the sparse 3D point cloud",
    )
    gps_images = _write_gps_reference(manifest, outputs / "gps_reference.txt")
    timings = {key: round(value, 2) for key, value in timings.items()}
    report = {
        "status": "sparse_model_ready", "profile": args.profile, "frames_selected": frame_report["frames_selected"],
        "reconstruction_frames": str(reconstruction_frames), "model_directory": str(model), "point_cloud": str(point_cloud),
        "gps_reference_images": gps_images, "ai_dynamic_masking": {key: value for key, value in ai_report.items() if key != "frames"},
        "timings_seconds": timings, "total_seconds": round(time.perf_counter() - started, 2),
        "georeferencing": "pending_metric_alignment",
    }
    (outputs / "reconstruction_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("STEP: Sparse 3D reconstruction complete", flush=True)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
