"""COLMAP model inspection and GPS alignment helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

import numpy as np
from pyproj import CRS, Transformer

from .telemetry import FrameTelemetry, parse_dji_srt


FRAME_NUMBER = re.compile(r"(\d+)")


@dataclass(frozen=True)
class CommandResult:
    label: str
    seconds: float
    output: str


@dataclass(frozen=True)
class AlignmentPlan:
    frame_shift: int
    time_shift_seconds: float
    scale: float
    three_dimensional_rmse_m: float
    horizontal_rmse_m: float
    horizontal_median_m: float
    reference_count: int
    utm_epsg: int
    origin_latitude: float
    origin_longitude: float
    origin_altitude_m: float


def run(command: list[str], *, label: str, cwd: Path | None = None) -> CommandResult:
    """Run one external command and return its duration and combined output."""
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    output = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode:
        raise RuntimeError(f"{label} failed.\n{output[-6000:]}")
    return CommandResult(label=label, seconds=time.perf_counter() - started, output=output)


def _quaternion_rotation(qw: float, qx: float, qy: float, qz: float) -> np.ndarray:
    return np.array(
        [
            [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
            [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
            [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
        ],
        dtype=np.float64,
    )


def convert_model_to_text(model_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    run(
        ["colmap", "model_converter", "--input_path", str(model_path), "--output_path", str(destination), "--output_type", "TXT"],
        label="Exporting COLMAP model metadata",
    )


def camera_centers(model_path: Path) -> dict[str, np.ndarray]:
    """Return image camera centers keyed by image filename."""
    with tempfile.TemporaryDirectory(prefix="ekadrishti-colmap-") as directory:
        text_model = Path(directory)
        convert_model_to_text(model_path, text_model)
        rows = [line for line in (text_model / "images.txt").read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    centers: dict[str, np.ndarray] = {}
    for line in rows[::2]:
        fields = line.split()
        qw, qx, qy, qz = map(float, fields[1:5])
        translation = np.array(list(map(float, fields[5:8])), dtype=np.float64)
        centers[fields[9]] = -_quaternion_rotation(qw, qx, qy, qz).T @ translation
    return centers


def _utm_epsg(latitude: float, longitude: float) -> int:
    zone = int((longitude + 180) // 6) + 1
    return (32600 if latitude >= 0 else 32700) + zone


def _project_records(records: list[FrameTelemetry]) -> tuple[dict[int, np.ndarray], int, tuple[float, float, float]]:
    usable = [item for item in records if None not in (item.latitude, item.longitude, item.absolute_altitude_m)]
    if not usable:
        raise ValueError("Telemetry contains no complete latitude, longitude and altitude records.")
    first = usable[0]
    assert first.latitude is not None and first.longitude is not None and first.absolute_altitude_m is not None
    epsg = _utm_epsg(first.latitude, first.longitude)
    transformer = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(epsg), always_xy=True)
    east0, north0 = transformer.transform(first.longitude, first.latitude)
    projected: dict[int, np.ndarray] = {}
    for item in usable:
        assert item.latitude is not None and item.longitude is not None and item.absolute_altitude_m is not None
        east, north = transformer.transform(item.longitude, item.latitude)
        projected[item.frame] = np.array([east - east0, north - north0, item.absolute_altitude_m - first.absolute_altitude_m])
    return projected, epsg, (first.latitude, first.longitude, first.absolute_altitude_m)


def _umeyama(source: np.ndarray, target: np.ndarray) -> tuple[float, np.ndarray]:
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
    predicted = (scale * (rotation @ source.T)).T + translation
    return scale, predicted


def plan_alignment(model_path: Path, telemetry_path: Path, *, fps: float, maximum_shift_frames: int = 30) -> tuple[AlignmentPlan, dict[str, FrameTelemetry]]:
    """Find the telemetry time shift that best agrees with the visual trajectory."""
    centers = camera_centers(model_path)
    records = parse_dji_srt(telemetry_path)
    by_frame = {item.frame: item for item in records}
    projected, epsg, origin = _project_records(records)
    numbered_images: list[tuple[str, int]] = []
    for name in centers:
        match = FRAME_NUMBER.search(Path(name).stem)
        if match:
            numbered_images.append((name, int(match.group(1))))
    best: tuple[float, int, float, float, float, int] | None = None
    for shift in range(-maximum_shift_frames, maximum_shift_frames + 1):
        pairs = [(name, frame + shift) for name, frame in numbered_images if frame + shift in projected]
        if len(pairs) < 8:
            continue
        source = np.array([centers[name] for name, _ in pairs])
        target = np.array([projected[frame] for _, frame in pairs])
        scale, predicted = _umeyama(source, target)
        errors = np.linalg.norm(predicted - target, axis=1)
        horizontal = np.linalg.norm(predicted[:, :2] - target[:, :2], axis=1)
        result = (float(np.sqrt(np.mean(errors**2))), shift, scale, float(np.sqrt(np.mean(horizontal**2))), float(np.median(horizontal)), len(pairs))
        if best is None or result[0] < best[0]:
            best = result
    if best is None:
        raise RuntimeError("Could not associate reconstructed images with telemetry frames.")
    rmse, shift, scale, horizontal_rmse, horizontal_median, count = best
    selected_records: dict[str, FrameTelemetry] = {}
    for name, frame in numbered_images:
        record = by_frame.get(frame + shift)
        if record and None not in (record.latitude, record.longitude, record.absolute_altitude_m):
            selected_records[name] = record
    plan = AlignmentPlan(shift, shift / fps, scale, rmse, horizontal_rmse, horizontal_median, count, epsg, origin[0], origin[1], origin[2])
    return plan, selected_records


def write_reference_file(records: dict[str, FrameTelemetry], path: Path) -> None:
    lines = [f"{name} {record.latitude} {record.longitude} {record.absolute_altitude_m}" for name, record in sorted(records.items())]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def align_model(model_path: Path, reference_path: Path, destination: Path, *, maximum_error_m: float = 5.0) -> CommandResult:
    if shutil.which("colmap") is None:
        raise RuntimeError("COLMAP is required for metric alignment.")
    destination.mkdir(parents=True, exist_ok=True)
    return run(
        ["colmap", "model_aligner", "--input_path", str(model_path), "--output_path", str(destination), "--ref_images_path", str(reference_path), "--ref_is_gps", "1", "--alignment_type", "enu", "--alignment_max_error", str(maximum_error_m)],
        label="Aligning the reconstruction to GPS/ENU coordinates",
    )


def export_model_ply(model_path: Path, destination: Path) -> CommandResult:
    destination.parent.mkdir(parents=True, exist_ok=True)
    return run(["colmap", "model_converter", "--input_path", str(model_path), "--output_path", str(destination), "--output_type", "PLY"], label="Exporting georeferenced point cloud")


def model_statistics(model_path: Path) -> dict[str, float | int]:
    result = run(["colmap", "model_analyzer", "--path", str(model_path)], label="Inspecting aligned model")
    patterns: dict[str, tuple[str, type]] = {
        "registered_images": (r"Registered images:\s+(\d+)", int),
        "points": (r"Points:\s+(\d+)", int),
        "observations": (r"Observations:\s+(\d+)", int),
        "mean_track_length": (r"Mean track length:\s+([0-9.]+)", float),
        "mean_reprojection_error_px": (r"Mean reprojection error:\s+([0-9.]+)px", float),
    }
    report: dict[str, float | int] = {}
    for key, (pattern, cast) in patterns.items():
        match = re.search(pattern, result.output)
        if match:
            report[key] = cast(match.group(1))
    return report


def plan_as_dict(plan: AlignmentPlan) -> dict[str, float | int]:
    return json.loads(json.dumps(asdict(plan)))
