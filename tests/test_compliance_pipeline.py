from __future__ import annotations

import csv
import struct
from pathlib import Path

import cv2
import numpy as np

from src.ekadrishti.accuracy_validation import pending_report, validate_csv
from src.ekadrishti.dynamic_masking import copy_without_ai
from src.ekadrishti.full_pipeline import PROFILES as DENSE_PROFILES
from src.ekadrishti.reconstruct import PROFILES as SPARSE_PROFILES
from src.ekadrishti.transform_ply import transform_binary_ply


def test_reference_dimension_accuracy_statistics(tmp_path: Path) -> None:
    source = tmp_path / "dimensions.csv"
    with source.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=["name", "model_distance_m", "reference_distance_m"])
        writer.writeheader()
        writer.writerows([
            {"name": "wall", "model_distance_m": 10.1, "reference_distance_m": 10.0},
            {"name": "road", "model_distance_m": 19.8, "reference_distance_m": 20.0},
        ])
    report = validate_csv(source)
    assert report["status"] == "independently_validated"
    assert report["distance_error"]["count"] == 2
    assert report["distance_error"]["rmse_m"] == 0.1581
    assert pending_report()["claim_allowed"] is False


def test_copy_without_ai_preserves_reconstruction_frames(tmp_path: Path) -> None:
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.mkdir()
    image = np.full((16, 24, 3), 127, dtype=np.uint8)
    assert cv2.imwrite(str(source / "frame_000001.jpg"), image)
    report = copy_without_ai(source, destination)
    assert report["frames_processed"] == 1
    assert (destination / "frame_000001.jpg").read_bytes() == (source / "frame_000001.jpg").read_bytes()


def test_binary_ply_metric_transform_preserves_non_vertex_payload(tmp_path: Path) -> None:
    header = (
        b"ply\nformat binary_little_endian 1.0\n"
        b"element vertex 3\nproperty float x\nproperty float y\nproperty float z\n"
        b"element face 1\nproperty list uchar int vertex_indices\nend_header\n"
    )
    vertices = b"".join(struct.pack("<fff", *point) for point in [(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    face = struct.pack("<Biii", 3, 0, 1, 2)
    source, destination = tmp_path / "source.ply", tmp_path / "metric.ply"
    source.write_bytes(header + vertices + face)
    report = transform_binary_ply(
        source,
        destination,
        scale=2.0,
        rotation=np.eye(3),
        translation=np.array([10.0, 20.0, 30.0]),
    )
    output = destination.read_bytes()
    offset = len(header)
    assert struct.unpack_from("<fff", output, offset) == (10.0, 20.0, 30.0)
    assert struct.unpack_from("<fff", output, offset + 12) == (12.0, 20.0, 30.0)
    assert output[-len(face):] == face
    assert report["extent_m"] == [2.0, 2.0, 0.0]


def test_rapid_and_precision_profiles_are_ordered() -> None:
    assert SPARSE_PROFILES["rapid"]["interval_seconds"] > SPARSE_PROFILES["precision"]["interval_seconds"]
    assert SPARSE_PROFILES["rapid"]["feature_size"] < SPARSE_PROFILES["precision"]["feature_size"]
    assert DENSE_PROFILES["rapid"]["dense_max_image_size"] < DENSE_PROFILES["precision"]["dense_max_image_size"]
