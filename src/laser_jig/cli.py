"""laser-jig: 3D-printable laser-engraving jigs and matching SVG templates from a CSV of blank sizes.

    laser-jig generate BLANKS.csv [-o jigs/]   one STL and one SVG per row
    laser-jig doctor                           environment report for bug reports
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

from . import __version__, base

REQUIRED = ("product", "blank_w_mm", "blank_h_mm", "blank_z_mm", "shape", "layout", "pocket_type", "tolerance")
OPTIONAL = ("folder", "tab_w_mm", "tab_l_mm", "n_pockets", "notes")
POCKET_TYPES = {
    "rect": ("4wall", "3wall", "3wall_top_notch", "3wall_overrun"),
    "circle": ("cylinder", "cylinder_notch", "cylinder_removal_notch"),
    "tombstone": ("tombstone_pocket",),
    "wallet": ("wallet_pocket",),
    "heart": ("heart_profile",),
}
SINGLE_POCKET = ("circle", "tombstone", "wallet")
TOLERANCES = ("tight", "loose")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
# Names Windows reserves for devices; a folder called "con" can't be created there.
RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)
MAX_BLANK = 1000.0   # mm; larger values are almost certainly typing mistakes
MAX_THICKNESS = 100.0
MAX_OVERRUN = 3      # designs that run off the plate may be at most this many plate depths long
MIN_ROUNDED = 10.0   # rounded-rectangle and tombstone pockets need room for their 3-5 mm corner radii
_LAYOUT = re.compile(r"^([1-9][0-9]?)x([1-9][0-9]?)$")


def _num(row: dict, key: str, problems: list[str], *, positive: bool, optional: bool = False) -> float:
    raw = (row.get(key) or "").strip()
    if not raw:
        if optional or not positive:
            return 0.0
        problems.append(f"{key} is empty")
        return 0.0
    try:
        v = float(raw)
    except ValueError:
        problems.append(f"{key} {raw!r} is not a number")
        return 0.0
    if v != v or v in (float("inf"), float("-inf")):
        problems.append(f"{key} {raw!r} is not a finite number")
        return 0.0
    if positive and not v > 0:
        problems.append(f"{key} must be greater than 0 (got {raw})")
    elif v < 0:
        problems.append(f"{key} can't be negative (got {raw})")
    return v


def footprint(row: dict) -> tuple[float, float, bool]:
    """Width and depth (mm) the pockets need on the plate, including walls, and whether the blank is designed to
    run past the plate's front or back edge (running past the sides is never allowed)."""
    from .stl import INTER, WALL, tol
    t = tol(row["tolerance"])
    w, h = float(row["blank_w_mm"]), float(row["blank_h_mm"] or 0)
    cols, rows = (int(x) for x in row["layout"].lower().split("x"))
    shape, ptype = row["shape"], row["pocket_type"]
    grid = lambda n, size: 2 * WALL + n * size + (n - 1) * INTER  # noqa: E731
    if shape in ("rect", "heart"):
        if ptype == "3wall_overrun":
            return grid(cols, w + 2 * t), 0.0, True
        if ptype.startswith("3wall"):
            pl = w + t
            return grid(cols, h + 2 * t), (base.BASE_H - pl) / 2 + (rows - 1) * (pl + INTER) + pl, False
        return grid(cols, w + 2 * t), grid(rows, h + 2 * t), False
    if shape == "circle":
        return w + 2 * t + 2 * WALL, w + 2 * t + 2 * WALL, False
    if shape == "wallet":
        return w + 2 * t + 2 * WALL, h + 2 * t + 2 * WALL, False
    return w + 2 * t + 2 * WALL, 0.0, True  # tombstone: the tag may run past the back edge


def _tab_problems(shape, ptype, layout, w, h, tab_w, tab_l) -> list[str]:
    """Ring/tab slots: they must be narrower than the blank, fit the plate, and leave other pockets alone."""
    if ptype.startswith("3wall") and ptype != "3wall_overrun":
        has_slot, across = tab_w > 0, h
    elif ptype in ("4wall", "heart_profile"):
        has_slot, across = tab_w > 0 and tab_l > 0, w
    elif ptype == "cylinder_notch":
        has_slot, across = True, w
        tab_w = tab_w or 12.0  # the generator's default slot width
    else:
        has_slot, across = False, w
    problems = []
    if has_slot and tab_w > across:
        problems.append(f"tab_w_mm ({tab_w:g}) must not be wider than the blank ({across:g} mm across)")
    if tab_l > base.BASE_H:
        problems.append(f"tab_l_mm ({tab_l:g}) must not be longer than the plate is deep ({base.BASE_H:g} mm)")
    rows = int(layout.split("x")[1])
    if has_slot and rows > 1:
        problems.append("ring slots only work with one row of pockets (each slot runs to the plate edge and would "
                        "cut through the pockets in the other rows); use a layout like 3x1")
    return problems


def row_problems(row: dict) -> list[str]:
    """Everything wrong with one CSV row, against the current base plate."""
    from .stl import pocket_depth
    problems: list[str] = []
    product = (row.get("product") or "").strip()
    if not SAFE_NAME.match(product):
        problems.append("product must be 1-64 letters, digits, '_' or '-' (it becomes the file name)")
    folder = (row.get("folder") or "").strip()
    if folder and not SAFE_NAME.match(folder):
        problems.append("folder must be letters, digits, '_' or '-' (one folder level, no slashes)")
    for label, name in (("product", product), ("folder", folder)):
        if RESERVED.match(name):
            problems.append(f"{label} {name!r} is a reserved device name on Windows; choose another")
    shape = (row.get("shape") or "").strip()
    ptype = (row.get("pocket_type") or "").strip()
    if shape not in POCKET_TYPES:
        problems.append(f"shape {shape!r} isn't one of {', '.join(POCKET_TYPES)}")
    elif ptype not in POCKET_TYPES[shape]:
        problems.append(f"pocket_type {ptype!r} doesn't go with shape {shape} (use {', '.join(POCKET_TYPES[shape])})")
    if (row.get("tolerance") or "").strip() not in TOLERANCES:
        problems.append(f"tolerance must be {' or '.join(TOLERANCES)}")
    layout = (row.get("layout") or "").strip().lower()
    m = _LAYOUT.match(layout)
    if not m:
        problems.append(f"layout {layout!r} must look like 2x1 (columns x rows)")
    elif shape in SINGLE_POCKET and layout != "1x1":
        problems.append(f"shape {shape} makes one pocket; layout must be 1x1")
    w = _num(row, "blank_w_mm", problems, positive=True)
    h = _num(row, "blank_h_mm", problems, positive=shape != "circle")
    z = _num(row, "blank_z_mm", problems, positive=True)
    tab_w = _num(row, "tab_w_mm", problems, positive=False, optional=True)
    tab_l = _num(row, "tab_l_mm", problems, positive=False, optional=True)
    for key, v, cap in (("blank_w_mm", w, MAX_BLANK), ("blank_h_mm", h, MAX_BLANK), ("blank_z_mm", z, MAX_THICKNESS)):
        if v > cap:
            problems.append(f"{key} must be at most {cap:g} mm (got {v:g})")
    if shape == "wallet" and (0 < w < MIN_ROUNDED or 0 < h < MIN_ROUNDED):
        problems.append(f"a wallet blank must be at least {MIN_ROUNDED:g} mm each way (its corners are 5 mm round)")
    if shape == "tombstone" and 0 < w < MIN_ROUNDED:
        problems.append(f"a tombstone blank must be at least {MIN_ROUNDED:g} mm wide")
    if shape == "tombstone" and w and h and h <= w / 2:
        problems.append("a tombstone blank must be taller than half its width")
    if problems:
        return problems
    problems += _tab_problems(shape, ptype, layout, w, h, tab_w, tab_l)
    if (ptype == "3wall_overrun" or shape == "tombstone") and h > MAX_OVERRUN * base.BASE_H:
        problems.append(f"blank_h_mm can be at most {MAX_OVERRUN * base.BASE_H:g} mm ({MAX_OVERRUN}x the plate depth) "
                        f"for a blank that runs off the plate (got {h:g})")
    if pocket_depth(z) > base.BASE_Z - 1.0:
        problems.append(f"a {z:g} mm blank needs a pocket deeper than the {base.BASE_Z:g} mm plate allows "
                        "(keep at least 1 mm of floor; use a thicker --thickness)")
    clean = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
    clean["layout"] = layout
    need_x, need_y, may_overrun_y = footprint(clean)
    if need_x > base.BASE_W + 1e-9:
        problems.append(f"the pockets need {need_x:.1f} mm across but the plate is {base.BASE_W:g} mm wide")
    if not may_overrun_y and need_y > base.BASE_H + 1e-9:
        problems.append(f"the pockets need {need_y:.1f} mm front to back but the plate is {base.BASE_H:g} mm deep")
    return problems


def read_rows(path: Path) -> list[dict]:
    """Rows of a blanks CSV, validated. Raises ValueError listing every problem in every row."""
    try:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            header = [c.strip() for c in (reader.fieldnames or [])]
            raw_rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        raise ValueError(f"couldn't read {path.name}: {e}") from None
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise ValueError(f"{path.name} is missing column(s): {', '.join(missing)}")
    unknown = [c for c in header if c and c not in REQUIRED + OPTIONAL]
    if unknown:
        raise ValueError(f"{path.name} has unknown column(s): {', '.join(unknown)} "
                         f"(allowed: {', '.join(REQUIRED + OPTIONAL)})")
    rows, errors, seen = [], [], {}
    for n, raw in enumerate(raw_rows, start=2):  # line 1 is the header
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k is not None}
        if not any(row.values()):
            continue
        if None in raw:
            errors.append(f"line {n}: more values than columns")
            continue
        row.setdefault("folder", "")
        row.setdefault("tab_w_mm", "")
        row.setdefault("tab_l_mm", "")
        row["layout"] = row["layout"].lower()
        problems = row_problems(row)
        key = f"{row['folder']}/{row['product']}".casefold()
        if key in seen:
            problems.append(f"same product and folder as line {seen[key]} (the files would overwrite each other)")
        seen.setdefault(key, n)
        if problems:
            errors.append(f"line {n} ({row.get('product') or 'no product'}): " + "; ".join(problems))
        row["_line"] = n
        rows.append(row)
    if errors:
        raise ValueError("\n  ".join([f"{len(errors)} row(s) in {path.name} need fixing:"] + errors))
    if not rows:
        raise ValueError(f"{path.name} has no rows")
    return rows


def planned_outputs(row: dict, out_dir: Path, kinds: tuple[str, ...]) -> list[Path]:
    folder = out_dir / row["folder"] if row["folder"] else out_dir
    return [folder / f"{row['product']}_jig.{k}" for k in kinds]


def _atomic(dest: Path, write, content) -> None:
    """Write to dest.part, then rename over dest, so an interrupted run never leaves a half-written file."""
    tmp = dest.with_name(dest.name + ".part")
    try:
        write(content, tmp)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="laser-jig", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"laser-jig {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate", help="make jigs from a CSV of blank sizes")
    g.add_argument("csv", type=Path, help="CSV file, one blank per row (see examples/blanks.csv)")
    g.add_argument("-o", "--out-dir", type=Path, default=Path("jigs"), help="output folder (default: ./jigs)")
    g.add_argument("--only", choices=("stl", "svg"), help="make only the STL jigs or only the SVG templates")
    d = base.DEFAULT
    g.add_argument("--width", type=float, default=d["width"], help=f"plate width in mm (default: {d['width']:g})")
    g.add_argument("--height", type=float, default=d["height"],
                   help=f"plate depth, front to back, in mm (default: {d['height']:g})")
    g.add_argument("--thickness", type=float, default=d["thickness"],
                   help=f"plate thickness in mm (default: {d['thickness']:g})")
    g.add_argument("--corner-radius", type=float, default=d["corner_radius"],
                   help=f"plate corner radius in mm (default: {d['corner_radius']:g})")
    g.add_argument("--overwrite", action="store_true", help="replace existing output files")
    g.add_argument("-q", "--quiet", action="store_true")
    doc = sub.add_parser("doctor", help="environment report to paste into bug reports")
    doc.add_argument("--json", action="store_true")
    return p


def _generate(args) -> int:
    try:
        base.use_base(args.width, args.height, args.thickness, args.corner_radius)
        rows = read_rows(args.csv)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    kinds = (args.only,) if args.only else ("stl", "svg")
    folders = {args.out_dir} | {args.out_dir / r["folder"] for r in rows if r["folder"]}
    blocked = sorted(str(f) for f in folders if f.exists() and not f.is_dir())
    if blocked:
        print(f"error: {', '.join(blocked)} is not a folder (a file has that name); choose another --out-dir",
              file=sys.stderr)
        return 2
    existing = [p for row in rows for p in planned_outputs(row, args.out_dir, kinds) if p.exists()]
    if existing and not args.overwrite:
        shown = "\n  ".join(str(p) for p in existing[:10]) + ("\n  ..." if len(existing) > 10 else "")
        print(f"error: {len(existing)} output file(s) already exist, so nothing was made:\n  {shown}\n"
              "Use --overwrite to replace them, or choose another --out-dir.", file=sys.stderr)
        return 2
    from . import stl, svg
    # Build every jig in memory first, so a row the CAD kernel can't build leaves no files behind.
    built, failures = [], []
    for row in rows:
        try:
            part = stl.build_jig(row) if "stl" in kinds else None
            text = svg.svg_text(row) if "svg" in kinds else None
        except Exception as e:  # the CAD kernel raises its own (non-Python) error types; report them per row
            failures.append(f"line {row['_line']} ({row['product']}): couldn't build the jig: {type(e).__name__}: {e}")
            continue
        built.append((row, part, text))
    if failures:
        print("error: nothing was written because these rows failed:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    for i, (row, part, text) in enumerate(built, 1):
        outs = dict(zip(kinds, planned_outputs(row, args.out_dir, kinds), strict=True))
        try:
            outs[kinds[0]].parent.mkdir(parents=True, exist_ok=True)
            if part is not None:
                _atomic(outs["stl"], stl.write_stl, part)
            if text is not None:
                _atomic(outs["svg"], svg.write_svg, text)
        except OSError as e:
            print(f"error: line {row['_line']} ({row['product']}): couldn't write to {outs[kinds[0]].parent}: "
                  f"{e.strerror or e}", file=sys.stderr)
            return 1
        if not args.quiet:
            for out in outs.values():
                print(f"[{i}/{len(built)}] {row['product']} -> {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = _parser().parse_args(argv)
    if args.command == "doctor":
        from .doctor import run
        return run(as_json=args.json)
    return _generate(args)
