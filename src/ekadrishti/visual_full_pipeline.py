"""Run EkaDrishti's complete visual 3D pipeline when no usable telemetry exists."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def stream(command: list[str], cwd: Path) -> None:
    process = subprocess.Popen(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert process.stdout is not None
    for line in process.stdout:
        print(line.rstrip(), flush=True)
    if process.wait() != 0:
        raise RuntimeError(f"Pipeline command failed with exit code {process.returncode}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a visual-only EkaDrishti model from an MP4.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    root, workspace, video = args.project_root.resolve(), args.workspace.resolve(), args.video.resolve()
    python = str(root / ".venv/bin/python") if (root / ".venv/bin/python").is_file() else sys.executable
    stream([
        python, "-u", "-m", "src.ekadrishti.reconstruct_visual_demo", "--video", str(video),
        "--workspace", str(workspace), "--project-root", str(root),
    ], root)
    sparse_report = json.loads((workspace / "outputs" / "visual_reconstruction_report.json").read_text(encoding="utf-8"))
    stream([
        python, "-u", "-m", "src.ekadrishti.build_dense_cuda", "--images", str(workspace / "frames"),
        "--sparse-model", sparse_report["model_directory"], "--workspace", str(workspace),
        "--project-root", str(root), "--max-image-size", "1280",
    ], root)
    dense = workspace / "dense"
    assets = root / "dashboard" / "dist" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    stream([
        python, "-m", "src.ekadrishti.prepare_viewer_cloud", "--input", str(dense / "fused.ply"),
        "--output", str(assets / "dense_point_cloud.ply"), "--max-points", "750000",
    ], root)
    shutil.copy2(dense / "textured" / "mesh.ply", assets / "dense_textured_mesh.ply")
    shutil.copy2(dense / "textured" / "texture.png", assets / "dense_texture.png")
    report = {
        **sparse_report,
        "status": "visual_textured_model_ready",
        "telemetry_status": "unavailable_or_unreadable",
        "measurement_status": "disabled_without_telemetry_or_ground_control",
        "dense_point_cloud": str(dense / "fused.ply"),
        "textured_mesh": str(dense / "textured" / "mesh.ply"),
        "dashboard": "http://127.0.0.1:4173/textured_viewer.html",
    }
    (workspace / "outputs" / "reconstruction_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("STEP: Visual-only textured 3D model ready", flush=True)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
