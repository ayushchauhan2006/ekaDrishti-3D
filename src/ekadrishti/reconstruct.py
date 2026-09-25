"""Build a sparse 3D point cloud from one drone video and DJI telemetry."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def _run(command: list[str], *, cwd: Path, label: str) -> None:
    """Run one reconstruction command and make pipeline progress visible."""
    print(f"STEP: {label}", flush=True)
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if completed.returncode:
        details = (completed.stdout + "\n" + completed.stderr).strip()
        raise RuntimeError(f"{label} failed.\n{details[-4000:]}")
    if completed.stdout.strip():
        print(completed.stdout.strip()[-1000:], flush=True)


def _find_model(sparse_directory: Path) -> Path:
    candidates = sorted(
        (path for path in sparse_directory.iterdir() if path.is_dir() and (path / "images.bin").is_file()),
        key=lambda path: path.name,
    )
    if not candidates:
        raise RuntimeError("COLMAP finished without producing a registered sparse model.")
    return candidates[-1]


def _write_gps_reference(manifest_path: Path, output_path: Path) -> int:
    """Save usable drone GPS values for the later calibration stage."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lines: list[str] = []
    for frame in manifest["frames"]:
        telemetry = frame.get("telemetry") or {}
        image = frame.get("image_path")
        latitude = telemetry.get("latitude")
        longitude = telemetry.get("longitude")
        altitude = telemetry.get("absolute_altitude_m")
        if frame.get("selected") and image and None not in (latitude, longitude, altitude):
            lines.append(f"{Path(image).name} {latitude} {longitude} {altitude}")
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run EkaDrishti's sparse 3D reconstruction pipeline.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True, help="Empty per-mission output folder")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=0.5)
    parser.add_argument("--use-gpu", action="store_true", help="Use a CUDA-enabled COLMAP build when available")
    args = parser.parse_args()

    video = args.video.resolve()
    telemetry = args.telemetry.resolve()
    workspace = args.workspace.resolve()
    project_root = args.project_root.resolve()
    if not video.is_file() or not telemetry.is_file():
        parser.error("Video and telemetry must be existing files.")
    cuda_colmap = project_root / "tools" / "colmap-cuda" / "build" / "src" / "colmap" / "exe" / "colmap"
    colmap = str(cuda_colmap) if args.use_gpu and cuda_colmap.is_file() else "colmap"
    if args.use_gpu and not cuda_colmap.is_file():
        parser.error(f"CUDA COLMAP build is missing: {cuda_colmap}")
    if shutil.which(colmap) is None and not Path(colmap).is_file():
        parser.error("COLMAP is not installed or is not available on PATH.")

    outputs = workspace / "outputs"
    frames = workspace / "frames" / "selected"
    manifest = outputs / "frame_manifest.json"
    report = outputs / "mission_report.json"
    database = outputs / "database.db"
    sparse = outputs / "sparse"
    export = outputs / "export"
    outputs.mkdir(parents=True, exist_ok=True)
    sparse.mkdir(exist_ok=True)

    _run(
        [
            "python3", "-m", "src.ekadrishti.inspect_mission", "--video", str(video),
            "--telemetry", str(telemetry), "--output", str(report),
        ],
        cwd=project_root,
        label="Inspecting video and flight telemetry",
    )
    _run(
        [
            "python3", "-m", "src.ekadrishti.extract_frames", "--video", str(video),
            "--telemetry", str(telemetry), "--output-directory", str(frames), "--manifest", str(manifest),
            "--interval-seconds", str(args.interval_seconds),
        ],
        cwd=project_root,
        label="Selecting sharp reconstruction frames",
    )

    frame_report = json.loads(manifest.read_text(encoding="utf-8"))
    if frame_report["frames_selected"] < 8:
        raise RuntimeError("Fewer than eight usable frames were found; this video cannot produce a stable 3D model.")
    gpu_flag = "1" if args.use_gpu else "0"
    _run(
        [
            colmap, "feature_extractor", "--database_path", str(database), "--image_path", str(frames),
            "--ImageReader.single_camera", "1", "--FeatureExtraction.use_gpu", gpu_flag,
            "--FeatureExtraction.max_image_size", "1600",
        ],
        cwd=project_root,
        label="Finding visual features across frames",
    )
    _run(
        [
            colmap, "sequential_matcher", "--database_path", str(database),
            "--FeatureMatching.use_gpu", gpu_flag, "--FeatureMatching.num_threads", "1",
            "--SequentialMatching.overlap", "10",
        ],
        cwd=project_root,
        label="Matching overlapping video frames",
    )
    _run(
        [
            colmap, "mapper", "--database_path", str(database), "--image_path", str(frames),
            "--output_path", str(sparse),
        ],
        cwd=project_root,
        label="Building the sparse 3D point cloud",
    )
    model = _find_model(sparse)
    export.mkdir(parents=True, exist_ok=True)
    point_cloud = export / "sparse_point_cloud.ply"
    _run(
        [colmap, "model_converter", "--input_path", str(model), "--output_path", str(point_cloud), "--output_type", "PLY"],
        cwd=project_root,
        label="Exporting the 3D point cloud",
    )
    gps_reference = outputs / "gps_reference.txt"
    gps_images = _write_gps_reference(manifest, gps_reference)
    reconstruction_report = {
        "status": "sparse_model_ready",
        "frames_selected": frame_report["frames_selected"],
        "model_directory": str(model),
        "point_cloud": str(point_cloud),
        "gps_reference_images": gps_images,
        "georeferencing": "pending_calibration",
        "next_step": "Calibrate camera and GPS timing before metric measurements; then create a dense model and mesh.",
    }
    (outputs / "reconstruction_report.json").write_text(
        json.dumps(reconstruction_report, indent=2) + "\n", encoding="utf-8"
    )
    print("STEP: Sparse 3D reconstruction complete", flush=True)
    print(json.dumps(reconstruction_report, indent=2), flush=True)


if __name__ == "__main__":
    main()
