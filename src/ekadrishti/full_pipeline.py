"""Run the complete EkaDrishti video-to-presentation workflow."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
import subprocess
import sys

from .finalize_model import finalize


def _stream(command: list[str], *, cwd: Path) -> None:
    process = subprocess.Popen(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert process.stdout is not None
    for line in process.stdout:
        print(line.rstrip(), flush=True)
    if process.wait() != 0:
        raise RuntimeError(f"Pipeline command failed with exit code {process.returncode}: {' '.join(command)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and publish a complete EkaDrishti 3D mission.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=0.5)
    parser.add_argument("--use-gpu", action="store_true")
    parser.add_argument("--sparse-model", type=Path, help="Resume finalization from an existing COLMAP sparse model.")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    workspace = args.workspace.resolve()
    video = args.video.resolve()
    telemetry = args.telemetry.resolve()
    outputs = workspace / "outputs"
    report_path = outputs / "reconstruction_report.json"
    if args.sparse_model is None:
        command = [
            sys.executable, "-u", "-m", "src.ekadrishti.reconstruct",
            "--video", str(video), "--telemetry", str(telemetry),
            "--workspace", str(workspace), "--project-root", str(project_root),
            "--interval-seconds", str(args.interval_seconds),
        ]
        if args.use_gpu:
            command.append("--use-gpu")
        _stream(command, cwd=project_root)
        sparse_report = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        sparse_model = args.sparse_model.resolve()
        if not (sparse_model / "images.bin").is_file():
            parser.error(f"Sparse model is missing images.bin: {sparse_model}")
        manifest = json.loads((outputs / "frame_manifest.json").read_text(encoding="utf-8"))
        sparse_report = {"frames_selected": manifest["frames_selected"], "model_directory": str(sparse_model)}
    print("STEP: Creating final metric presentation package", flush=True)
    presentation = finalize(
        sparse_model=Path(sparse_report["model_directory"]),
        video=video,
        telemetry=telemetry,
        output_directory=outputs / "presentation",
        publish_directory=project_root / "dashboard" / "dist" / "assets",
    )
    print("STEP: Building dense photo-textured 3D model with GPU", flush=True)
    _stream(
        [
            sys.executable, "-u", "-m", "src.ekadrishti.build_dense_cuda",
            "--images", str(workspace / "frames" / "selected"),
            "--sparse-model", sparse_report["model_directory"],
            "--workspace", str(workspace), "--project-root", str(project_root),
            "--max-image-size", "1280",
        ],
        cwd=project_root,
    )
    dense = workspace / "dense"
    assets = project_root / "dashboard" / "dist" / "assets"
    _stream(
        [
            sys.executable, "-m", "src.ekadrishti.prepare_viewer_cloud",
            "--input", str(dense / "fused.ply"),
            "--output", str(assets / "dense_point_cloud.ply"), "--max-points", "750000",
        ],
        cwd=project_root,
    )
    shutil.copy2(dense / "textured" / "mesh.ply", assets / "dense_textured_mesh.ply")
    shutil.copy2(dense / "textured" / "texture.png", assets / "dense_texture.png")

    combined = {
        **presentation,
        "frames_selected": sparse_report["frames_selected"],
        "model_directory": sparse_report["model_directory"],
        "presentation_directory": str(outputs / "presentation"),
        "dense_point_cloud": str(dense / "fused.ply"),
        "textured_mesh": str(dense / "textured" / "mesh.ply"),
        "textured_viewer": "http://127.0.0.1:4173/textured_viewer.html",
        "dashboard": "http://127.0.0.1:4173/presentation.html",
    }
    report_path.write_text(json.dumps(combined, indent=2) + "\n", encoding="utf-8")
    print("STEP: Full 3D presentation ready", flush=True)
    print(json.dumps(combined, indent=2), flush=True)


if __name__ == "__main__":
    main()
