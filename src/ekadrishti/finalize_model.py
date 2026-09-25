"""Geo-register and package an existing sparse reconstruction for presentation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import time

import cv2
from pyproj import CRS, Transformer

from .colmap_model import _project_records, export_model_ply, model_statistics, plan_as_dict, write_reference_file
from .metric_alignment import fit_metric_alignment, transform_model, verify_alignment
from .presentation import generate_presentation_artifacts
from .telemetry import parse_dji_srt


PUBLISHED_ARTIFACTS = [
    "georeferenced_point_cloud.ply", "confidence_point_cloud.ply", "presentation_mesh.ply",
    "presentation_mesh.obj", "presentation_mesh.glb", "georeferenced_point_cloud.las",
    "surface_model.tif", "presentation_report.json",
]


def _video_fps(path: Path) -> float:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video for timing metadata: {path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    capture.release()
    if fps <= 0:
        raise RuntimeError("Video does not contain a valid frame rate.")
    return fps


def _publish(source: Path, static_assets: Path) -> None:
    static_assets.mkdir(parents=True, exist_ok=True)
    for name in PUBLISHED_ARTIFACTS:
        candidate = source / name
        if candidate.is_file():
            shutil.copy2(candidate, static_assets / name)


def finalize(
    *,
    sparse_model: Path,
    video: Path,
    telemetry: Path,
    output_directory: Path,
    publish_directory: Path | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    output_directory.mkdir(parents=True, exist_ok=True)
    fps = _video_fps(video)
    print("STEP: Optimizing video and telemetry synchronization", flush=True)
    plan, records, similarity = fit_metric_alignment(sparse_model, telemetry, fps=fps)
    reference = output_directory / "gps_reference_calibrated.txt"
    write_reference_file(records, reference)

    aligned = output_directory / "aligned_model"
    print("STEP: Applying verified metric coordinate transformation", flush=True)
    alignment_run = transform_model(sparse_model, aligned, similarity)
    projected_records, _, _ = _project_records(parse_dji_srt(telemetry))
    alignment_verification = verify_alignment(aligned, records, origin_projected=projected_records)

    aligned_ply = output_directory / "aligned_point_cloud.ply"
    print("STEP: Exporting geo-referenced point cloud", flush=True)
    export_run = export_model_ply(aligned, aligned_ply)
    statistics = model_statistics(aligned)
    transformer = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(plan.utm_epsg), always_xy=True)
    east, north = transformer.transform(plan.origin_longitude, plan.origin_latitude)
    print("STEP: Reconstructing presentation surface and geospatial products", flush=True)
    artifact_report = generate_presentation_artifacts(
        aligned_ply,
        output_directory,
        utm_epsg=plan.utm_epsg,
        utm_origin=(east, north, plan.origin_altitude_m),
    )
    report: dict[str, object] = {
        **artifact_report,
        "video": str(video),
        "telemetry": str(telemetry),
        "alignment": {
            **plan_as_dict(plan),
            **alignment_verification,
            "rotation_matrix": similarity.rotation.tolist(),
            "translation_m": similarity.translation.tolist(),
        },
        "reconstruction": statistics,
        "stage_seconds": {
            "alignment": round(alignment_run.seconds, 2),
            "point_cloud_export": round(export_run.seconds, 2),
        },
        "total_finalization_seconds": round(time.perf_counter() - started, 2),
        "accuracy_status": "GPS consistency measured; independent checkpoints are still required for an absolute <=1 m claim.",
    }
    (output_directory / "presentation_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if publish_directory is not None:
        _publish(output_directory, publish_directory)
    print("STEP: Presentation artifacts ready", flush=True)
    print(json.dumps(report, indent=2), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a georeferenced EkaDrishti presentation model.")
    parser.add_argument("--sparse-model", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--publish-directory", type=Path)
    args = parser.parse_args()
    finalize(
        sparse_model=args.sparse_model.resolve(),
        video=args.video.resolve(),
        telemetry=args.telemetry.resolve(),
        output_directory=args.output_directory.resolve(),
        publish_directory=args.publish_directory.resolve() if args.publish_directory else None,
    )


if __name__ == "__main__":
    main()
