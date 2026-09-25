"""Apply a metric Sim(3) to binary PLY vertices without changing face/UV data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import struct

import numpy as np


TYPE_FORMATS = {
    "char": "b", "uchar": "B", "int8": "b", "uint8": "B", "short": "h", "ushort": "H",
    "int16": "h", "uint16": "H", "int": "i", "uint": "I", "int32": "i", "uint32": "I",
    "float": "f", "float32": "f", "double": "d", "float64": "d",
}


def transform_binary_ply(source: Path, destination: Path, *, scale: float, rotation: np.ndarray, translation: np.ndarray) -> dict[str, object]:
    data = bytearray(source.read_bytes())
    marker = b"end_header\n"
    header_end = data.find(marker)
    if header_end < 0:
        raise ValueError(f"PLY header is incomplete: {source}")
    header = bytes(data[:header_end]).decode("ascii")
    if "format binary_little_endian 1.0" not in header:
        raise ValueError("Only binary little-endian PLY files are supported.")
    vertex_count = 0
    properties: list[tuple[str, str]] = []
    current_element = ""
    for line in header.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == "element":
            current_element = fields[1]
            if current_element == "vertex":
                vertex_count = int(fields[2])
        elif len(fields) == 3 and fields[0] == "property" and current_element == "vertex":
            properties.append((fields[1], fields[2]))
    if not vertex_count or not properties:
        raise ValueError("PLY is missing a vertex element.")
    formats = [TYPE_FORMATS[item[0]] for item in properties]
    record = struct.Struct("<" + "".join(formats))
    names = [item[1] for item in properties]
    indices = {name: names.index(name) for name in ("x", "y", "z")}
    normal_indices = {name: names.index(name) for name in ("nx", "ny", "nz")} if all(name in names for name in ("nx", "ny", "nz")) else None
    offset = header_end + len(marker)
    minimum = np.full(3, np.inf)
    maximum = np.full(3, -np.inf)
    for vertex in range(vertex_count):
        position = offset + vertex * record.size
        values = list(record.unpack_from(data, position))
        xyz = np.array([values[indices["x"]], values[indices["y"]], values[indices["z"]]], dtype=np.float64)
        xyz = scale * (rotation @ xyz) + translation
        for axis, name in enumerate(("x", "y", "z")):
            values[indices[name]] = float(xyz[axis])
        if normal_indices:
            normal = np.array([values[normal_indices["nx"]], values[normal_indices["ny"]], values[normal_indices["nz"]]], dtype=np.float64)
            normal = rotation @ normal
            length = np.linalg.norm(normal)
            if length:
                normal /= length
            for axis, name in enumerate(("nx", "ny", "nz")):
                values[normal_indices[name]] = float(normal[axis])
        record.pack_into(data, position, *values)
        minimum = np.minimum(minimum, xyz)
        maximum = np.maximum(maximum, xyz)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return {
        "source": str(source), "destination": str(destination), "vertices": vertex_count,
        "extent_m": (maximum - minimum).round(4).tolist(),
        "minimum_local_m": minimum.round(4).tolist(), "maximum_local_m": maximum.round(4).tolist(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a saved EkaDrishti metric transform to PLY geometry.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True, help="Presentation report containing alignment transform")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    alignment = report["alignment"]
    result = transform_binary_ply(
        args.input.resolve(), args.output.resolve(), scale=float(alignment["scale"]),
        rotation=np.asarray(alignment["rotation_matrix"], dtype=np.float64),
        translation=np.asarray(alignment["translation_m"], dtype=np.float64),
    )
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
