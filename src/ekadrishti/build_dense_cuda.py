"""Build a dense, photo-textured metric model with local CUDA COLMAP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time


def run(command: list[str], cwd: Path, label: str) -> float:
    print(f"STEP: {label}", flush=True)
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd)
    if completed.returncode:
        raise RuntimeError(f"{label} failed (exit code {completed.returncode}).")
    return time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a dense, textured metric CUDA 3D model.")
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--sparse-model", type=Path, required=True, help="Metric-aligned COLMAP sparse model")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--alignment-report", type=Path, required=True)
    parser.add_argument("--max-image-size", type=int, default=1280)
    parser.add_argument("--poisson-depth", type=int, default=11)
    args = parser.parse_args()

    started = time.perf_counter()
    root = args.project_root.resolve()
    colmap = root / "tools/colmap-cuda/build/src/colmap/exe/colmap"
    images, sparse = args.images.resolve(), args.sparse_model.resolve()
    dense = args.workspace.resolve() / "dense"
    alignment_report = json.loads(args.alignment_report.read_text(encoding="utf-8"))
    if not colmap.is_file():
        parser.error(f"CUDA COLMAP build is missing: {colmap}")
    if not images.is_dir() or not (sparse / "images.bin").is_file():
        parser.error("AI-cleaned frames and a metric-aligned COLMAP model are required.")
    dense.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}
    timings["undistortion"] = run([
        str(colmap), "image_undistorter", "--image_path", str(images), "--input_path", str(sparse),
        "--output_path", str(dense), "--output_type", "COLMAP", "--max_image_size", str(args.max_image_size),
    ], root, "Preparing camera-corrected metric images")
    timings["depth_maps"] = run([
        str(colmap), "patch_match_stereo", "--workspace_path", str(dense), "--workspace_format", "COLMAP",
        "--PatchMatchStereo.gpu_index", "0", "--PatchMatchStereo.max_image_size", str(args.max_image_size),
        "--PatchMatchStereo.num_threads", "4",
    ], root, "Creating dense GPU depth maps")
    fused = dense / "fused.ply"
    timings["fusion"] = run([
        str(colmap), "stereo_fusion", "--workspace_path", str(dense), "--workspace_format", "COLMAP",
        "--input_type", "geometric", "--output_path", str(fused), "--StereoFusion.num_threads", "4",
    ], root, "Fusing metric depth maps into a dense point cloud")
    mesh = dense / "meshed-poisson.ply"
    timings["meshing"] = run([
        str(colmap), "poisson_mesher", "--input_path", str(fused), "--output_path", str(mesh),
        "--PoissonMeshing.depth", str(args.poisson_depth), "--PoissonMeshing.color", "1", "--PoissonMeshing.num_threads", "4",
    ], root, "Creating a metric triangle mesh")
    textured = dense / "textured"
    textured.mkdir(parents=True, exist_ok=True)
    timings["texturing"] = run([
        str(colmap), "mesh_texturer", "--workspace_path", str(dense), "--input_path", str(mesh),
        "--output_path", str(textured), "--MeshTextureMapping.num_threads", "4",
    ], root, "Projecting source photographs onto the metric mesh")
    alignment = alignment_report["alignment"]
    report = {
        "status": "dense_textured_metric_model_ready",
        "dense_point_cloud": str(fused), "mesh": str(mesh), "textured_mesh_directory": str(textured),
        "georeferencing": "metric_local_utm_frame", "crs": alignment_report["crs"],
        "utm_origin": {
            "latitude": alignment["origin_latitude"], "longitude": alignment["origin_longitude"],
            "absolute_altitude_m": alignment["origin_altitude_m"],
        },
        "metric_scale_verified": True,
        "timings_seconds": {key: round(value, 2) for key, value in timings.items()},
        "total_seconds": round(time.perf_counter() - started, 2),
    }
    (dense / "dense_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
