import csv
import json
import math
import re

import numpy as np
import pytest

from conftest import DATA, row
from geometry import stl_summary, stl_triangles, svg_body_hash
from laser_jig import base
from laser_jig.stl import make_jig, pocket_depth
from laser_jig.svg import generate_svg

GOLDEN = json.loads((DATA / "golden.json").read_text(encoding="utf-8"))
CASES = list(csv.DictReader((DATA / "all_pocket_types.csv").open(encoding="utf-8")))


@pytest.mark.parametrize("case", CASES, ids=[c["product"] for c in CASES])
def test_matches_golden_output(case, tmp_path):
    """Every pocket type must still produce the recorded reference geometry in golden.json."""
    want = GOLDEN[case["product"]]
    got = stl_summary(make_jig(case, str(tmp_path)))
    assert got["min"] == pytest.approx(want["stl"]["min"], abs=1e-3)
    assert got["max"] == pytest.approx(want["stl"]["max"], abs=1e-3)
    assert got["volume"] == pytest.approx(want["stl"]["volume"], rel=1e-4)
    assert svg_body_hash(generate_svg(case, str(tmp_path))) == want["svg_sha256"]


def _plate_volume(w, h, z, r):
    return (w * h - (4 - math.pi) * r * r) * z


DOTS = 2 * math.pi * 1.5 ** 2 * 0.3


@pytest.mark.parametrize("tolerance, clearance", [("tight", 0.5), ("loose", 0.8)])
def test_rectangular_pockets_have_the_stated_clearance(tolerance, clearance, tmp_path):
    r = row(blank_w_mm="45", blank_h_mm="40", blank_z_mm="3", layout="2x1", tolerance=tolerance)
    pocket = (45 + 2 * clearance) * (40 + 2 * clearance) * pocket_depth(3)
    want = _plate_volume(109, 109, 9, 5) + DOTS - 2 * pocket
    assert stl_summary(make_jig(r, str(tmp_path)))["volume"] == pytest.approx(want, abs=5)


def test_round_pocket_has_the_loose_clearance(tmp_path):
    r = row(shape="circle", pocket_type="cylinder", blank_w_mm="80", blank_h_mm="0", tolerance="loose")
    pocket = math.pi * (40 + 0.8) ** 2 * pocket_depth(3)
    want = _plate_volume(109, 109, 9, 5) + DOTS - pocket
    assert stl_summary(make_jig(r, str(tmp_path)))["volume"] == pytest.approx(want, abs=10)


def test_thick_blanks_keep_a_floor_under_the_pocket():
    assert pocket_depth(3) == 3.5
    assert pocket_depth(20) == base.BASE_Z - 1.0
    assert pocket_depth(8) == 6.0


def _dot_centres(stl_path):
    """Centres (x, y) of the raised registration dots: the vertices above the plate's top face."""
    pts = stl_triangles(stl_path).reshape(-1, 3)
    top = pts[pts[:, 2] > base.HZ + 0.2][:, :2]
    left, right = top[top[:, 0] < 0], top[top[:, 0] > 0]
    return [tuple(np.round((g.min(axis=0) + g.max(axis=0)) / 2, 3)) for g in (left, right)]


@pytest.mark.parametrize("size", [(109.0, 109.0), (150.0, 120.0)])
def test_registration_dots_match_in_stl_and_svg(size, tmp_path):
    w, h = size
    base.use_base(width=w, height=h)
    r = row()
    (left, right) = _dot_centres(make_jig(r, str(tmp_path)))
    # STL coordinates are centred on the plate; the SVG's origin is its top-left corner.
    assert left == pytest.approx((5 - w / 2, 5 - h / 2), abs=1e-3)
    assert right == pytest.approx((w - 5 - w / 2, 5 - h / 2), abs=1e-3)
    text = open(generate_svg(r, str(tmp_path)), encoding="utf-8").read()
    circles = re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="1.500" fill="none" stroke="#999"', text)
    assert [(float(x), float(y)) for x, y in circles] == [(5.0, 5.0), (w - 5, 5.0)]


def test_custom_base_sets_stl_and_svg_size(tmp_path):
    base.use_base(width=150, height=120, thickness=12, corner_radius=8)
    r = row()
    s = stl_summary(make_jig(r, str(tmp_path)))
    assert s["min"] == pytest.approx([-75, -60, -6], abs=1e-3)
    assert s["max"][:2] == pytest.approx([75, 60], abs=1e-3)
    text = open(generate_svg(r, str(tmp_path)), encoding="utf-8").read()
    assert 'width="150.000mm" height="120.000mm"' in text
    assert 'rx="8.000"' in text
    assert "GREY=150mm jig boundary" in text


@pytest.mark.parametrize("kwargs, message", [
    ({"width": 0}, "greater than 0"),
    ({"height": -5}, "greater than 0"),
    ({"width": float("nan")}, "greater than 0"),
    ({"thickness": float("inf")}, "greater than 0"),
    ({"width": 15}, "at least 20"),
    ({"thickness": 1.5}, "at least 2 mm"),
    ({"corner_radius": -1}, "corner radius"),
    ({"width": 40, "corner_radius": 20}, "corner radius"),
    ({"corner_radius": float("nan")}, "corner radius"),
])
def test_use_base_rejects_impossible_plates(kwargs, message):
    with pytest.raises(ValueError, match=message):
        base.use_base(**kwargs)
    assert (base.BASE_W, base.BASE_H, base.BASE_Z, base.CORNER_R) == (109.0, 109.0, 9.0, 5.0)


def test_use_base_updates_derived_values():
    base.use_base(width=120, height=100, thickness=10, corner_radius=0)
    assert (base.HW, base.HH, base.HZ, base.FIELD_W, base.FIELD_H) == (60, 50, 5, 120, 100)


def test_square_corners_build(tmp_path):
    base.use_base(corner_radius=0)
    s = stl_summary(make_jig(row(), str(tmp_path)))
    assert s["max"][:2] == pytest.approx([54.5, 54.5], abs=1e-3)
