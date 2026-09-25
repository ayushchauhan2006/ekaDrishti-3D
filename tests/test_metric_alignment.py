from __future__ import annotations

import numpy as np

from src.ekadrishti.colmap_model import _quaternion_rotation
from src.ekadrishti.metric_alignment import SimilarityTransform, _fit_similarity, _transform_images, _transform_points


def test_similarity_fit_recovers_known_metric_transform() -> None:
    source = np.array([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 2.0, 0.0],
        [0.0, 0.0, 3.0], [2.0, 3.0, 4.0], [-1.0, 2.0, 1.0],
    ])
    angle = np.deg2rad(31.0)
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0.0], [np.sin(angle), np.cos(angle), 0.0], [0.0, 0.0, 1.0]])
    target = (7.5 * (rotation @ source.T)).T + np.array([120.0, -45.0, 8.0])
    fitted, predicted = _fit_similarity(source, target)
    np.testing.assert_allclose(fitted.scale, 7.5, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(fitted.rotation, rotation, atol=1e-10)
    np.testing.assert_allclose(fitted.translation, [120.0, -45.0, 8.0], atol=1e-10)
    np.testing.assert_allclose(predicted, target, atol=1e-10)


def test_camera_center_and_points_receive_same_world_transform() -> None:
    transform = SimilarityTransform(
        3.0,
        np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
        np.array([10.0, 20.0, 30.0]),
    )
    image_lines = [
        "# Image list",
        "1 1 0 0 0 -1 -2 -3 1 frame_000001.jpg",
        "12.0 13.0 -1",
    ]
    transformed = _transform_images(image_lines, transform)
    fields = transformed[1].split()
    world_to_camera = _quaternion_rotation(*map(float, fields[1:5]))
    translation = np.array(list(map(float, fields[5:8])))
    center = -world_to_camera.T @ translation
    np.testing.assert_allclose(center, transform.apply(np.array([[1.0, 2.0, 3.0]]))[0], atol=1e-10)

    point_lines = ["# points", "7 1 2 3 10 20 30 0.5 1 4"]
    point = np.array(list(map(float, _transform_points(point_lines, transform)[1].split()[1:4])))
    np.testing.assert_allclose(point, center, atol=1e-10)
