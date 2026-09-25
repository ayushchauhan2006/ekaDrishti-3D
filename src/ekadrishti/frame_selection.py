"""Quality-aware video frame selection for 3D reconstruction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import cv2


@dataclass(frozen=True)
class FrameCandidate:
    frame_index: int
    timestamp_seconds: float
    blur_score: float
    mean_brightness: float
    selected: bool
    image_path: str | None


def _quality_scores(frame: object) -> tuple[float, float]:
    """Return a sharpness score and mean brightness for a BGR OpenCV frame."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    return sharpness, brightness


def select_reconstruction_frames(
    video_path: Path,
    output_directory: Path,
    interval_seconds: float = 1.0,
    minimum_blur_score: float = 60.0,
    minimum_brightness: float = 20.0,
    maximum_brightness: float = 235.0,
) -> list[FrameCandidate]:
    """Sample a video and save frames suitable for feature matching."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero")

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0 or frame_count <= 0:
        capture.release()
        raise RuntimeError("Video has no readable frame-rate or frame-count metadata")

    output_directory.mkdir(parents=True, exist_ok=True)
    step = max(1, round(fps * interval_seconds))
    candidates: list[FrameCandidate] = []

    for frame_index in range(0, frame_count, step):
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok:
            continue
        blur_score, mean_brightness = _quality_scores(frame)
        selected = (
            blur_score >= minimum_blur_score
            and minimum_brightness <= mean_brightness <= maximum_brightness
        )
        image_path: Path | None = None
        if selected:
            image_path = output_directory / f"frame_{frame_index + 1:06d}.jpg"
            if not cv2.imwrite(str(image_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                capture.release()
                raise RuntimeError(f"Could not save frame: {image_path}")
        candidates.append(
            FrameCandidate(
                frame_index=frame_index,
                timestamp_seconds=frame_index / fps,
                blur_score=round(blur_score, 3),
                mean_brightness=round(mean_brightness, 3),
                selected=selected,
                image_path=str(image_path) if image_path else None,
            )
        )

    capture.release()
    return candidates


def candidate_as_dict(candidate: FrameCandidate) -> dict[str, object]:
    return asdict(candidate)
