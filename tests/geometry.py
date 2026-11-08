"""Measurements of generated files, used to compare them with stored golden values."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import numpy as np


def stl_triangles(path: Path) -> np.ndarray:
    """Triangles of a binary STL as an (n, 3, 3) array of vertex coordinates (mm)."""
    data = Path(path).read_bytes()
    (n,) = struct.unpack_from("<I", data, 80)
    if len(data) != 84 + 50 * n:
        raise ValueError(f"{path} is not a binary STL with {n} triangles")
    rec = np.frombuffer(data, dtype=np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]),
                        count=n, offset=84)
    return rec["v"].astype(np.float64)


def stl_summary(path: Path) -> dict:
    tri = stl_triangles(path)
    pts = tri.reshape(-1, 3)
    volume = float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)
    return {"triangles": int(len(tri)), "min": pts.min(axis=0).round(4).tolist(),
            "max": pts.max(axis=0).round(4).tolist(), "volume": round(volume, 3)}


def svg_body_hash(path: Path) -> str:
    """Hash of an SVG template without its comment lines, which name the product."""
    lines = [ln for ln in Path(path).read_text(encoding="utf-8").splitlines() if "<!--" not in ln]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
