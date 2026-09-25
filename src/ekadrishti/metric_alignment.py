"""Reliable metric alignment for COLMAP 3.9 models.

COLMAP 3.9.1 packages affected by upstream pose-transform regressions can report
successful alignment without applying the requested Sim(3).  This module fits
the similarity transform independently and rewrites the text model explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
import time

import numpy as np
from scipy.spatial.transform import Rotation

from .colmap_model import (
    AlignmentPlan,
    CommandResult,
    FRAME_NUMBER,
    _project_records,
    _quaternion_rotation,
    camera_centers,
    convert_model_to_text,
    run,
)
from .telemetry import FrameTelemetry, parse_dji_srt


@dataclass(frozen=True)
class SimilarityTransform:
    """A world-coordinate transform: target = scale * rotation @ source + translation."""

    scale: float
    rotation: np.ndarray
    translation: np.ndarray

    def apply(self, coordinates: np.ndarray) -> np.ndarray:
        return (self.scale * (self.rotation @ coordinates.T)).T + self.translation


def _fit_similarity(source: np.ndarray, target: np.ndarray) -> tuple[SimilarityTransform, np.ndarray]:
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    centered_source = source - source_mean
    centered_target = target - target_mean
    left, singular, right_t = np.linalg.svd(centered_target.T @ centered_source / len(source))
    correction = np.eye(3)
    correction[-1, -1] = np.sign(np.linalg.det(left @ right_t))
    rotation = left @ correction @ right_t
    variance = float(np.sum(centered_source * centered_source) / len(source))
    scale = float(np.trace(np.diag(singular) @ correction) / variance)
    translation = target_mean - scale * rotation @ source_mean
    transform = SimilarityTransform(scale, rotation, translation)
    return transform, transform.apply(source)


def fit_metric_alignment(
    model_path: Path,
    telemetry_path: Path,
    *,
    fps: float,
    maximum_shift_frames: int = 30,
) -> tuple[AlignmentPlan, dict[str, FrameTelemetry], SimilarityTransform]:
    """Fit a Sim(3) between reconstructed camera centers and metric UTM offsets."""
    centers = camera_centers(model_path)
    records = parse_dji_srt(telemetry_path)
    by_frame = {item.frame: item for item in records}
    projected, epsg, origin = _project_records(records)
    numbered_images: list[tuple[str, int]] = []
    for name in centers:
        match = FRAME_NUMBER.search(Path(name).stem)
        if match:
            numbered_images.append((name, int(match.group(1))))

    best: tuple[float, int, SimilarityTransform, float, float, int] | None = None
    for shift in range(-maximum_shift_frames, maximum_shift_frames + 1):
        pairs = [(name, frame + shift) for name, frame in numbered_images if frame + shift in projected]
        if len(pairs) < 8:
            continue
        source = np.array([centers[name] for name, _ in pairs])
        target = np.array([projected[frame] for _, frame in pairs])
        transform, predicted = _fit_similarity(source, target)
        errors = np.linalg.norm(predicted - target, axis=1)
        horizontal = np.linalg.norm(predicted[:, :2] - target[:, :2], axis=1)
        candidate = (
            float(np.sqrt(np.mean(errors**2))),
            shift,
            transform,
            float(np.sqrt(np.mean(horizontal**2))),
            float(np.median(horizontal)),
            len(pairs),
        )
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        raise RuntimeError("Could not associate reconstructed images with telemetry frames.")

    rmse, shift, transform, horizontal_rmse, horizontal_median, count = best
    selected_records: dict[str, FrameTelemetry] = {}
    for name, frame in numbered_images:
        record = by_frame.get(frame + shift)
        if record and None not in (record.latitude, record.longitude, record.absolute_altitude_m):
            selected_records[name] = record
    plan = AlignmentPlan(
        shift,
        shift / fps,
        transform.scale,
        rmse,
        horizontal_rmse,
        horizontal_median,
        count,
        epsg,
        origin[0],
        origin[1],
        origin[2],
    )
    return plan, selected_records, transform


def _transform_images(lines: list[str], transform: SimilarityTransform) -> list[str]:
    transformed: list[str] = []
    pose_row = True
    for line in lines:
        if not line or line.startswith("#"):
            transformed.append(line)
            continue
        if not pose_row:
            transformed.append(line)
            pose_row = True
            continue
        fields = line.split()
        qw, qx, qy, qz = map(float, fields[1:5])
        translation = np.array(list(map(float, fields[5:8])), dtype=np.float64)
        world_to_camera = _quaternion_rotation(qw, qx, qy, qz)
        center = -world_to_camera.T @ translation
        transformed_center = transform.scale * (transform.rotation @ center) + transform.translation
        transformed_rotation = world_to_camera @ transform.rotation.T
        transformed_translation = -transformed_rotation @ transformed_center
        qx2, qy2, qz2, qw2 = Rotation.from_matrix(transformed_rotation).as_quat()
        values = [
            fields[0],
            f"{qw2:.17g}", f"{qx2:.17g}", f"{qy2:.17g}", f"{qz2:.17g}",
            f"{transformed_translation[0]:.17g}",
            f"{transformed_translation[1]:.17g}",
            f"{transformed_translation[2]:.17g}",
            *fields[8:],
        ]
        transformed.append(" ".join(values))
        pose_row = False
    return transformed


def _transform_points(lines: list[str], transform: SimilarityTransform) -> list[str]:
    transformed: list[str] = []
    for line in lines:
        if not line or line.startswith("#"):
            transformed.append(line)
            continue
        fields = line.split()
        coordinate = np.array(list(map(float, fields[1:4])), dtype=np.float64)
        coordinate = transform.scale * (transform.rotation @ coordinate) + transform.translation
        fields[1:4] = [f"{value:.17g}" for value in coordinate]
        transformed.append(" ".join(fields))
    return transformed


def transform_model(
    model_path: Path,
    destination: Path,
    transform: SimilarityTransform,
) -> CommandResult:
    """Apply a metric similarity transform without COLMAP's buggy pose helper."""
    started = time.perf_counter()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ekadrishti-metric-model-") as directory:
        text_model = Path(directory)
        convert_model_to_text(model_path, text_model)
        images_path = text_model / "images.txt"
        points_path = text_model / "points3D.txt"
        images = _transform_images(images_path.read_text(encoding="utf-8").splitlines(), transform)
        points = _transform_points(points_path.read_text(encoding="utf-8").splitlines(), transform)
        images_path.write_text("\n".join(images) + "\n", encoding="utf-8")
        points_path.write_text("\n".join(points) + "\n", encoding="utf-8")
        for old_file in destination.glob("*"):
            if old_file.is_file() or old_file.is_symlink():
                old_file.unlink()
            elif old_file.is_dir():
                shutil.rmtree(old_file)
        converted = run(
            [
                "colmap", "model_converter",
                "--input_path", str(text_model),
                "--output_path", str(destination),
                "--output_type", "BIN",
            ],
            label="Writing explicitly transformed metric COLMAP model",
        )
    return CommandResult(
        label="Applying verified metric similarity transform",
        seconds=time.perf_counter() - started,
        output=converted.output,
    )


def verify_alignment(
    model_path: Path,
    records: dict[str, FrameTelemetry],
    *,
    origin_projected: dict[int, np.ndarray],
) -> dict[str, float | int]:
    """Measure transformed camera centers against their assigned telemetry samples."""
    centers = camera_centers(model_path)
    errors: list[float] = []
    horizontal: list[float] = []
    for name, record in records.items():
        if name not in centers or record.frame not in origin_projected:
            continue
        delta = centers[name] - origin_projected[record.frame]
        errors.append(float(np.linalg.norm(delta)))
        horizontal.append(float(np.linalg.norm(delta[:2])))
    if not errors:
        raise RuntimeError("Metric alignment verification found no common cameras.")
    return {
        "verified_camera_count": len(errors),
        "verified_3d_rmse_m": round(float(np.sqrt(np.mean(np.square(errors)))), 4),
        "verified_horizontal_rmse_m": round(float(np.sqrt(np.mean(np.square(horizontal)))), 4),
        "verified_horizontal_median_m": round(float(np.median(horizontal)), 4),
        "verified_maximum_3d_error_m": round(float(np.max(errors)), 4),
    }
