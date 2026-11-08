"""The product label on a template must never sit on top of a ring slot, or it gets engraved over the slot area."""

import csv
import re

import pytest

from conftest import DATA, EXAMPLES
from laser_jig.svg import svg_text

LABEL_SIZE = 3.2
CHAR_W = 0.6  # generous average glyph width of a sans-serif font, as a fraction of the font size
ASCENT = 0.75  # height of tall letters above the baseline (Arial: about 0.72)

CASES = [c for path in (DATA / "all_pocket_types.csv", EXAMPLES / "blanks.csv")
         for c in csv.DictReader(path.open(encoding="utf-8"))]
NUM = r"(-?[\d.]+)"


def _label_box(svg):
    m = re.search(rf'<text x="{NUM}" y="{NUM}" font-size="{LABEL_SIZE}"[^>]*>([^<]*)</text>', svg)
    x, y, text = float(m[1]), float(m[2]), m[3]
    half = len(text) * LABEL_SIZE * CHAR_W / 2
    return x - half, y - LABEL_SIZE * ASCENT, x + half, y + LABEL_SIZE * 0.25


def _slot_boxes(svg):
    pat = rf'<rect x="{NUM}" y="{NUM}" width="{NUM}" height="{NUM}"[^>]*stroke-dasharray="1,0.5"'
    return [(float(x), float(y), float(x) + float(w), float(y) + float(h)) for x, y, w, h in re.findall(pat, svg)]


def _overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@pytest.mark.parametrize("case", CASES, ids=[c["product"] for c in CASES])
def test_label_clears_every_ring_slot(case):
    svg = svg_text(case)
    label = _label_box(svg)
    assert 0 <= label[1] and label[3] <= 109, "label must stay on the plate"
    hits = [s for s in _slot_boxes(svg) if _overlaps(label, s)]
    assert not hits, f"label {label} overlaps slot(s) {hits}"
