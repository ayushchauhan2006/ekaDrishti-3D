"""Create a browser-friendly sampled PLY while preserving the full dense model."""

from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path


TYPE_CODES = {
    "char": ("b", 1), "int8": ("b", 1), "uchar": ("B", 1), "uint8": ("B", 1),
    "short": ("h", 2), "int16": ("h", 2), "ushort": ("H", 2), "uint16": ("H", 2),
    "int": ("i", 4), "int32": ("i", 4), "uint": ("I", 4), "uint32": ("I", 4),
    "float": ("f", 4), "float32": ("f", 4), "double": ("d", 8), "float64": ("d", 8),
}


def header_details(source: Path) -> tuple[int, list[tuple[str, str]], int]:
    lines: list[str] = []
    with source.open("rb") as file:
        while True:
            line = file.readline()
            if not line:
                raise ValueError("PLY header ended unexpectedly.")
            text = line.decode("ascii").strip()
            lines.append(text)
            if text == "end_header":
                break
        offset = file.tell()
    if "format binary_little_endian 1.0" not in lines:
        raise ValueError("Only binary little-endian PLY files are supported.")
    count = next((int(line.split()[-1]) for line in lines if line.startswith("element vertex ")), 0)
    properties = [(part[1], part[2]) for line in lines if line.startswith("property ") for part in [line.split()]]
    if not count or not properties or any(kind not in TYPE_CODES for kind, _ in properties):
        raise ValueError("PLY is missing supported vertex properties.")
    return count, properties, offset


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample a dense PLY for the web viewer.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-points", type=int, default=750_000)
    args = parser.parse_args()
    count, properties, start = header_details(args.input)
    step = max(1, math.ceil(count / args.max_points))
    selected = math.ceil(count / step)
    indices = {name: index for index, (_, name) in enumerate(properties)}
    for name in ("x", "y", "z"):
        if name not in indices:
            raise ValueError(f"PLY has no {name} coordinate.")
    code = "<" + "".join(TYPE_CODES[kind][0] for kind, _ in properties)
    stride = sum(TYPE_CODES[kind][1] for kind, _ in properties)
    output_header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {selected}\nproperty float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
    ).encode("ascii")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.input.open("rb") as source, args.output.open("wb") as target:
        source.seek(start)
        target.write(output_header)
        for index in range(count):
            record = source.read(stride)
            if len(record) != stride:
                raise ValueError("PLY vertex data ended unexpectedly.")
            if index % step:
                continue
            values = struct.unpack(code, record)
            color = [values[indices[name]] if name in indices else 180 for name in ("red", "green", "blue")]
            target.write(struct.pack(
                "<fffBBB", values[indices["x"]], values[indices["y"]], values[indices["z"]],
                *(max(0, min(255, int(value))) for value in color),
            ))
    print(f"Wrote {selected:,} of {count:,} points to {args.output}")


if __name__ == "__main__":
    main()
