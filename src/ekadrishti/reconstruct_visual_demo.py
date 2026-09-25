"""Create a visual-only sparse reconstruction from an MP4 without telemetry."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def run(command: list[str], cwd: Path, step: str) -> None:
    print(f"STEP: {step}", flush=True)
    completed = subprocess.run(command, cwd=cwd)
    if completed.returncode:
        raise RuntimeError(f"{step} failed (exit code {completed.returncode}).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a visual-only sparse model from a video.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--frames-per-second", type=float, default=4)
    parser.add_argument("--max-image-width", type=int, default=1600)
    args = parser.parse_args()
    root, video, workspace = args.project_root.resolve(), args.video.resolve(), args.workspace.resolve()
    colmap = root / "tools/colmap-cuda/build/src/colmap/exe/colmap"
    if not video.is_file() or not colmap.is_file():
        parser.error("The source video and local CUDA COLMAP build are required.")
    frames, output = workspace / "frames", workspace / "outputs"
    database, sparse, export = output / "database.db", output / "sparse", output / "export"
    frames.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    sparse.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vf",
        f"fps={args.frames_per_second},scale={args.max_image_width}:-2", "-q:v", "2", str(frames / "frame_%05d.jpg"),
    ], root, "Selecting overlapping city frames")
    run([
        str(colmap), "feature_extractor", "--database_path", str(database), "--image_path", str(frames),
        "--ImageReader.single_camera", "1", "--FeatureExtraction.use_gpu", "1", "--FeatureExtraction.gpu_index", "0", "--FeatureExtraction.max_image_size", str(args.max_image_width),
    ], root, "Finding building features with the GPU")
    run([
        str(colmap), "sequential_matcher", "--database_path", str(database), "--FeatureMatching.use_gpu", "1", "--FeatureMatching.gpu_index", "0", "--FeatureMatching.num_threads", "4",
        "--SequentialMatching.overlap", "15",
    ], root, "Matching neighbouring city frames")
    run([
        str(colmap), "mapper", "--database_path", str(database), "--image_path", str(frames), "--output_path", str(sparse),
    ], root, "Building the city sparse 3D model")
    models = sorted(path for path in sparse.iterdir() if path.is_dir() and (path / "images.bin").is_file())
    if not models:
        raise RuntimeError("The video did not produce a registered sparse model.")
    model = models[-1]
    export.mkdir(parents=True, exist_ok=True)
    cloud = export / "sparse_point_cloud.ply"
    run([str(colmap), "model_converter", "--input_path", str(model), "--output_path", str(cloud), "--output_type", "PLY"], root, "Exporting the city point cloud")
    report = {
        "status": "visual_sparse_model_ready", "video": str(video), "point_cloud": str(cloud),
        "model_directory": str(model), "georeferencing": "unavailable_without_telemetry",
    }
    (output / "visual_reconstruction_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
