"""Create dense points and a vertex-coloured mesh from a COLMAP sparse model."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def _run(command: list[str], *, cwd: Path, label: str) -> None:
    print(f"STEP: {label}", flush=True)
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if completed.returncode:
        detail = (completed.stdout + "\n" + completed.stderr).strip()
        raise RuntimeError(f"{label} failed.\n{detail[-4000:]}")


def _require_cuda_colmap() -> None:
    """Fail early with an actionable message when the distro COLMAP is installed."""
    check = subprocess.run(["colmap", "patch_match_stereo", "--help"], text=True, capture_output=True)
    output = check.stdout + check.stderr
    if "requires CUDA" in output or "without CUDA" in output:
        raise RuntimeError(
            "Dense reconstruction needs a CUDA-enabled COLMAP build. "
            "The currently installed Ubuntu COLMAP package is CPU-only."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dense points and a coloured mesh for EkaDrishti.")
    parser.add_argument("--images", type=Path, required=True, help="Selected reconstruction frames")
    parser.add_argument("--sparse-model", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--max-image-size", type=int, default=1600)
    parser.add_argument("--poisson-depth", type=int, default=11)
    args = parser.parse_args()

    images = args.images.resolve()
    sparse_model = args.sparse_model.resolve()
    workspace = args.workspace.resolve()
    project_root = args.project_root.resolve()
    if not images.is_dir() or not (sparse_model / "images.bin").is_file():
        parser.error("Images and a binary COLMAP sparse model are required.")
    _require_cuda_colmap()

    dense = workspace / "dense"
    dense.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "colmap", "image_undistorter", "--image_path", str(images), "--input_path", str(sparse_model),
            "--output_path", str(dense), "--output_type", "COLMAP", "--max_image_size", str(args.max_image_size),
        ],
        cwd=project_root,
        label="Preparing camera-corrected images for dense 3D",
    )
    _run(
        [
            "colmap", "patch_match_stereo", "--workspace_path", str(dense), "--workspace_format", "COLMAP",
            "--PatchMatchStereo.geom_consistency", "1", "--PatchMatchStereo.max_image_size", str(args.max_image_size),
        ],
        cwd=project_root,
        label="Creating dense GPU depth maps",
    )
    fused = dense / "fused.ply"
    _run(
        [
            "colmap", "stereo_fusion", "--workspace_path", str(dense), "--workspace_format", "COLMAP",
            "--input_type", "geometric", "--output_path", str(fused),
        ],
        cwd=project_root,
        label="Fusing dense depth maps into a point cloud",
    )
    mesh = dense / "meshed-poisson.ply"
    _run(
        [
            "colmap", "poisson_mesher", "--input_path", str(fused), "--output_path", str(mesh),
            "--PoissonMeshing.depth", str(args.poisson_depth), "--PoissonMeshing.color", "32",
        ],
        cwd=project_root,
        label="Creating the solid vertex-coloured 3D mesh",
    )
    report = {
        "status": "dense_mesh_ready",
        "dense_point_cloud": str(fused),
        "mesh": str(mesh),
        "appearance": "vertex_coloured_mesh",
        "texture_status": "requires_a_texture_projection_backend",
        "next_step": "Project photographs onto the mesh to create an image texture atlas.",
    }
    (dense / "dense_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("STEP: Dense mesh reconstruction complete", flush=True)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
