"""Independent checkpoint and reference-dimension accuracy evaluation."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


CHECKPOINT_COLUMNS = {"name", "model_x_m", "model_y_m", "model_z_m", "reference_x_m", "reference_y_m", "reference_z_m"}
DISTANCE_COLUMNS = {"name", "model_distance_m", "reference_distance_m"}


def _statistics(errors: np.ndarray) -> dict[str, float]:
    return {
        "count": int(len(errors)),
        "rmse_m": round(float(np.sqrt(np.mean(errors**2))), 4),
        "mae_m": round(float(np.mean(np.abs(errors))), 4),
        "median_m": round(float(np.median(np.abs(errors))), 4),
        "p95_m": round(float(np.percentile(np.abs(errors), 95)), 4),
        "maximum_m": round(float(np.max(np.abs(errors))), 4),
    }


def validate_csv(path: Path) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        rows = list(reader)
    if not rows:
        raise ValueError("Accuracy CSV contains no observations.")
    if CHECKPOINT_COLUMNS <= columns:
        model = np.array([[float(row[f"model_{axis}_m"]) for axis in "xyz"] for row in rows])
        reference = np.array([[float(row[f"reference_{axis}_m"]) for axis in "xyz"] for row in rows])
        delta = model - reference
        horizontal = np.linalg.norm(delta[:, :2], axis=1)
        vertical = delta[:, 2]
        three_dimensional = np.linalg.norm(delta, axis=1)
        return {
            "status": "independently_validated", "validation_type": "survey_checkpoints", "source": str(path),
            "horizontal": _statistics(horizontal), "vertical": _statistics(vertical),
            "three_dimensional": _statistics(three_dimensional),
            "observations": [
                {"name": row["name"], "horizontal_error_m": round(float(horizontal[index]), 4),
                 "vertical_error_m": round(float(vertical[index]), 4), "error_3d_m": round(float(three_dimensional[index]), 4)}
                for index, row in enumerate(rows)
            ],
        }
    if DISTANCE_COLUMNS <= columns:
        model = np.array([float(row["model_distance_m"]) for row in rows])
        reference = np.array([float(row["reference_distance_m"]) for row in rows])
        errors = model - reference
        relative = np.abs(errors) / np.maximum(np.abs(reference), 1e-9) * 100
        return {
            "status": "independently_validated", "validation_type": "reference_dimensions", "source": str(path),
            "distance_error": _statistics(errors),
            "mean_relative_error_percent": round(float(np.mean(relative)), 3),
            "observations": [
                {"name": row["name"], "model_distance_m": round(float(model[index]), 4),
                 "reference_distance_m": round(float(reference[index]), 4), "error_m": round(float(errors[index]), 4),
                 "relative_error_percent": round(float(relative[index]), 3)} for index, row in enumerate(rows)
            ],
        }
    raise ValueError(
        "Accuracy CSV must contain either checkpoint columns "
        f"{sorted(CHECKPOINT_COLUMNS)} or distance columns {sorted(DISTANCE_COLUMNS)}."
    )


def pending_report() -> dict[str, object]:
    return {
        "status": "awaiting_independent_checkpoints",
        "claim_allowed": False,
        "message": "Internal GPS consistency is available, but independent checkpoint or reference-dimension observations have not been supplied.",
        "accepted_schemas": [sorted(CHECKPOINT_COLUMNS), sorted(DISTANCE_COLUMNS)],
        "templates": ["docs/checkpoints_template.csv", "docs/reference_dimensions_template.csv"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate EkaDrishti against independent survey checkpoints or dimensions.")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = validate_csv(args.input.resolve()) if args.input else pending_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
