"""Build a dense, photo-textured model with EkaDrishti's local CUDA COLMAP build."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def run(command: list[str], cwd: Path, label: str) -> None:
    print(f"STEP: {label}", flush=True)
    completed = subprocess.run(command, cwd=cwd)
    if completed.returncode:
        raise RuntimeError(f"{label} failed (exit code {completed.returncode}).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a dense, textured CUDA 3D model.")
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--sparse-model", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--max-image-size", type=int, default=1280)
    parser.add_argument("--poisson-depth", type=int, default=11)
    args = parser.parse_args()

    root = args.project_root.resolve()
    colmap = root / "tools/colmap-cuda/build/src/colmap/exe/colmap"
    images = args.images.resolve()
    sparse = args.sparse_model.resolve()
    dense = args.workspace.resolve() / "dense"
    if not colmap.is_file():
        parser.error(f"CUDA COLMAP build is missing: {colmap}")
    if not images.is_dir() or not (sparse / "images.bin").is_file():
        parser.error("Selected frames and a COLMAP sparse model are required.")

    run([
        str(colmap), "image_undistorter", "--image_path", str(images),
        "--input_path", str(sparse), "--output_path", str(dense),
        "--output_type", "COLMAP", "--max_image_size", str(args.max_image_size),
    ], root, "Preparing camera-corrected images")
    run([
        str(colmap), "patch_match_stereo", "--workspace_path", str(dense),
        "--workspace_format", "COLMAP", "--PatchMatchStereo.gpu_index", "0",
        "--PatchMatchStereo.max_image_size", str(args.max_image_size),
        "--PatchMatchStereo.num_threads", "4",
    ], root, "Creating dense GPU depth maps")
    fused = dense / "fused.ply"
    run([
        str(colmap), "stereo_fusion", "--workspace_path", str(dense),
        "--workspace_format", "COLMAP", "--input_type", "geometric",
        "--output_path", str(fused), "--StereoFusion.num_threads", "4",
    ], root, "Fusing depth maps into a dense point cloud")
    mesh = dense / "meshed-poisson.ply"
    run([
        str(colmap), "poisson_mesher", "--input_path", str(fused),
        "--output_path", str(mesh), "--PoissonMeshing.depth", str(args.poisson_depth),
        "--PoissonMeshing.color", "1", "--PoissonMeshing.num_threads", "4",
    ], root, "Creating a solid triangle mesh")
    textured = dense / "textured"
    run([
        str(colmap), "mesh_texturer", "--workspace_path", str(dense),
        "--input_path", str(mesh), "--output_path", str(textured),
        "--MeshTextureMapping.num_threads", "4",
    ], root, "Projecting photographs onto the mesh")
    report = {
        "status": "dense_textured_model_ready",
        "dense_point_cloud": str(fused),
        "mesh": str(mesh),
        "textured_mesh_directory": str(textured),
        "georeferencing": "pending_calibration",
    }
    (dense / "dense_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
