"""AI-assisted dynamic-object masking for reconstruction frames.

Uses a compact YOLOv4-tiny COCO detector through OpenCV DNN.  Detected people,
vehicles and animals are inpainted before feature extraction and dense stereo so
moving objects do not become persistent 3D geometry.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import time

import cv2
import numpy as np


DYNAMIC_CLASSES = {
    "person", "bicycle", "car", "motorbike", "bus", "truck", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe",
}


def _load_labels(path: Path) -> list[str]:
    labels = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(labels) < 20:
        raise ValueError(f"COCO label file is incomplete: {path}")
    return labels


def mask_frames(
    source_directory: Path,
    destination_directory: Path,
    *,
    config: Path,
    weights: Path,
    labels_path: Path,
    confidence_threshold: float = 0.50,
) -> dict[str, object]:
    started = time.perf_counter()
    labels = _load_labels(labels_path)
    network = cv2.dnn.readNetFromDarknet(str(config), str(weights))
    detector = cv2.dnn_DetectionModel(network)
    detector.setInputParams(size=(416, 416), scale=1 / 255.0, swapRB=True)
    destination_directory.mkdir(parents=True, exist_ok=True)
    frames = sorted(source_directory.glob("*.jpg"))
    if not frames:
        raise RuntimeError(f"No reconstruction frames found in {source_directory}")

    total_objects = 0
    affected_frames = 0
    masked_pixels = 0
    total_pixels = 0
    counts: dict[str, int] = {}
    frame_results: list[dict[str, object]] = []
    for source in frames:
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"Could not read frame: {source}")
        height, width = image.shape[:2]
        total_pixels += height * width
        class_ids, confidences, boxes = detector.detect(
            image,
            confThreshold=confidence_threshold,
            nmsThreshold=0.45,
        )
        mask = np.zeros((height, width), dtype=np.uint8)
        detections: list[dict[str, object]] = []
        for class_id, confidence, box in zip(class_ids, confidences, boxes, strict=False):
            index = int(class_id) - 1
            name = labels[index] if 0 <= index < len(labels) else f"class_{class_id}"
            if name not in DYNAMIC_CLASSES:
                continue
            x, y, box_width, box_height = map(int, box)
            padding_x = max(4, int(box_width * 0.08))
            padding_y = max(4, int(box_height * 0.08))
            x0, y0 = max(0, x - padding_x), max(0, y - padding_y)
            x1, y1 = min(width, x + box_width + padding_x), min(height, y + box_height + padding_y)
            cv2.rectangle(mask, (x0, y0), (x1, y1), 255, thickness=-1)
            confidence_value = float(np.asarray(confidence).reshape(-1)[0])
            detections.append({"class": name, "confidence": round(confidence_value, 4), "box": [x0, y0, x1, y1]})
            counts[name] = counts.get(name, 0) + 1
        dynamic_pixels = int(np.count_nonzero(mask))
        if dynamic_pixels:
            affected_frames += 1
            total_objects += len(detections)
            masked_pixels += dynamic_pixels
            radius = 5 if dynamic_pixels < height * width * 0.08 else 3
            image = cv2.inpaint(image, mask, radius, cv2.INPAINT_TELEA)
        destination = destination_directory / source.name
        if not cv2.imwrite(str(destination), image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise RuntimeError(f"Could not write AI-masked frame: {destination}")
        frame_results.append({
            "image": source.name,
            "dynamic_objects": detections,
            "masked_percent": round(dynamic_pixels / (height * width) * 100, 4),
        })

    return {
        "status": "ai_dynamic_masking_complete",
        "model": "YOLOv4-tiny COCO via OpenCV DNN",
        "policy": "Detected people, vehicles and animals are excluded from reconstruction imagery.",
        "frames_processed": len(frames),
        "frames_with_dynamic_objects": affected_frames,
        "dynamic_objects_detected": total_objects,
        "detections_by_class": counts,
        "masked_pixel_percent": round(masked_pixels / max(total_pixels, 1) * 100, 5),
        "processing_seconds": round(time.perf_counter() - started, 2),
        "frames": frame_results,
    }


def copy_without_ai(source_directory: Path, destination_directory: Path) -> dict[str, object]:
    destination_directory.mkdir(parents=True, exist_ok=True)
    frames = sorted(source_directory.glob("*.jpg"))
    for source in frames:
        shutil.copy2(source, destination_directory / source.name)
    return {
        "status": "ai_dynamic_masking_disabled",
        "model": None,
        "frames_processed": len(frames),
        "frames_with_dynamic_objects": 0,
        "dynamic_objects_detected": 0,
        "masked_pixel_percent": 0.0,
        "frames": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mask dynamic objects in drone reconstruction frames.")
    parser.add_argument("--source-directory", type=Path, required=True)
    parser.add_argument("--destination-directory", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--confidence", type=float, default=0.50)
    args = parser.parse_args()
    for required in (args.config, args.weights, args.labels):
        if not required.is_file():
            parser.error(f"AI model asset is missing: {required}")
    report = mask_frames(
        args.source_directory.resolve(),
        args.destination_directory.resolve(),
        config=args.config.resolve(),
        weights=args.weights.resolve(),
        labels_path=args.labels.resolve(),
        confidence_threshold=args.confidence,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "frames"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
