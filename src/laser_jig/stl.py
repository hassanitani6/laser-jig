"""3D-printable laser jigs (STL): a base plate with pockets that hold blanks in a fixed position.

Suggested print settings: 0.2 mm layers, 3 walls, 15% gyroid infill, PLA.
"""

import os

from build123d import (
    BuildLine,
    BuildPart,
    BuildSketch,
    Circle,
    Cylinder,
    Locations,
    Mode,
    Plane,
    Polyline,
    Rectangle,
    RectangleRounded,
    export_stl,
    extrude,
    insert,
    make_face,
)

from . import base

# ── Constants (the base plate size lives in base.py) ───────────────────────────
WALL   = 3.0
INTER  = 2.0
FIELD_MARGIN = 3.0
TOL_TIGHT = 0.5
TOL_LOOSE = 0.8
POCKET_EXTRA_Z = 0.5


def tol(t):
    return TOL_TIGHT if t == "tight" else TOL_LOOSE


def sb(x, y):
    """Coordinates measured from the plate corner at (0, 0) → coordinates centred on the plate."""
    return x - base.HW, y - base.HH


def pocket_depth(blank_z):
    if blank_z >= 5:
        return min(blank_z - 2.0, base.BASE_Z - 1.0)
    return blank_z + POCKET_EXTRA_Z


def heart_pts(W, H, n=25):
    """Puffy heart polygon: rounded bottom (no cusp), symmetric lobes.
    sb() maps jig-Y directly to b123d-Y (no flip), so jig-top = small jig-Y = b123d -Y.
    Lobes at -Y (jig top, near REG dots), rounded bottom at +Y (jig bottom).
    Winding is naturally CCW in XY-plane → face normal +Z → extrude(-depth) cuts downward."""
    hw, hh = W / 2.0, H / 2.0

    def bezier(p0, p1, p2, p3, steps):
        pts = []
        for i in range(steps):
            t = i / steps
            u = 1.0 - t
            x = u**3*p0[0] + 3*u**2*t*p1[0] + 3*u*t**2*p2[0] + t**3*p3[0]
            y = u**3*p0[1] + 3*u**2*t*p1[1] + 3*u*t**2*p2[1] + t**3*p3[1]
            pts.append((x, y))
        return pts

    # 4 cubic Bezier segments, CCW from top notch.
    # Lobes at -hh (jig top), rounded bottom at +hh (jig bottom).
    # CP1 x=hw*0.25 gives a consistently rounded lobe arc.
    # Endpoint at -hh*0.4 places widest point 30% from top edge.
    # S2 CP2 at (hw*0.1, hh) gives horizontal tangent at bottom — no cusp.
    segments = [
        ((0, -hh*0.6),    (hw*0.25, -hh), (hw, -hh),      (hw, -hh*0.4)),
        ((hw, -hh*0.4),   (hw, hh*0.05),  (hw*0.1, hh),   (0,   hh)),
        ((0,   hh),       (-hw*0.1, hh),  (-hw, hh*0.05), (-hw, -hh*0.4)),
        ((-hw, -hh*0.4),  (-hw, -hh),     (-hw*0.25, -hh),(0,  -hh*0.6)),
    ]
    pts = []
    for seg in segments:
        pts.extend(bezier(*seg, n))
    return pts


# ── Solid builders ─────────────────────────────────────────────────────────────
# Each returns a Solid that the caller adds with insert(s, mode=Mode.ADD/SUBTRACT).

def reg_dot_solid(rx, ry):
    bx, by = sb(rx, ry)
    with BuildPart() as d:
        with Locations((bx, by, base.HZ + 0.15)):
            Cylinder(1.5, 0.3)
    return d.part


def rect_solid(w, h, depth, cx=0, cy=0):
    with BuildSketch(Plane.XY.offset(base.HZ)) as sk:
        with Locations((cx, cy)):
            Rectangle(w, h)
    return extrude(sk.sketch, amount=-depth)


def circle_solid(r, depth, cx=0, cy=0):
    with BuildSketch(Plane.XY.offset(base.HZ)) as sk:
        with Locations((cx, cy)):
            Circle(r)
    return extrude(sk.sketch, amount=-depth)




def rounded_rect_solid(pw, ph, cr, depth):
    with BuildSketch(Plane.XY.offset(base.HZ)) as sk:
        RectangleRounded(pw, ph, cr)
    return extrude(sk.sketch, amount=-depth)


def tombstone_solid(blank_w, blank_h, tv, depth):
    PW      = blank_w + 2 * tv
    SEMI_R  = PW / 2
    STR_H   = blank_h - blank_w / 2 + tv  # straight body height
    TOP_R   = 3.0
    cy_b    = (FIELD_MARGIN + SEMI_R) - base.HH  # b123d Y of semicircle center

    with BuildSketch(Plane.XY.offset(base.HZ)) as sk:
        with Locations((0, cy_b)):
            Circle(SEMI_R)
            with Locations((0, STR_H / 2)):
                Rectangle(PW, STR_H)
            for corner_x in (-PW / 2 + TOP_R, PW / 2 - TOP_R):
                with Locations((corner_x, STR_H)):
                    Circle(TOP_R)
            with Locations((0, STR_H)):
                Rectangle(PW - 2 * TOP_R, TOP_R * 2)
    return extrude(sk.sketch, amount=-depth)


def heart_solid(blank_w, blank_h, depth, cx=0, cy=0):
    pts = heart_pts(blank_w, blank_h)
    with BuildSketch(Plane.XY.offset(base.HZ)) as sk:
        with Locations((cx, cy)):
            with BuildLine():
                Polyline(*pts, close=True)
            make_face()
    return extrude(sk.sketch, amount=-depth)


# ── Jig builder ────────────────────────────────────────────────────────────────

def build_jig(row):
    """The jig for one CSV row, as a build123d solid (nothing is written)."""
    tv         = tol(row["tolerance"])
    blank_w    = float(row["blank_w_mm"])
    blank_h    = float(row["blank_h_mm"]) if row["blank_h_mm"] else 0.0
    blank_z    = float(row["blank_z_mm"])
    shape      = row["shape"]
    ptype      = row["pocket_type"]
    layout     = row["layout"].lower()
    cols, rows = (int(x) for x in layout.split("x")) if "x" in layout else (1, 1)
    pz         = pocket_depth(blank_z)

    # Build pocket solids first (outside any BuildPart context)
    pockets = _build_pockets(row, blank_w, blank_h, tv, pz, shape, ptype, cols, rows, blank_z)

    with BuildPart() as jig:
        with BuildSketch(Plane.XY.offset(-base.HZ)) as sk:
            if base.CORNER_R > 0:
                RectangleRounded(base.BASE_W, base.BASE_H, base.CORNER_R)
            else:
                Rectangle(base.BASE_W, base.BASE_H)
        extrude(sk.sketch, amount=base.BASE_Z)
        # Registration dots (jig coords — match SVG crosshairs and raised physical dots)
        for rx, ry in [(base.REG_INSET, base.REG_INSET), (base.BASE_W - base.REG_INSET, base.REG_INSET)]:
            insert(reg_dot_solid(rx, ry))
        # Cut pockets
        for pocket in pockets:
            insert(pocket, mode=Mode.SUBTRACT)

    return jig.part


def write_stl(part, path):
    if not export_stl(part, str(path)):
        raise OSError(f"couldn't write {path}")


def make_jig(row, out_dir="."):
    out_folder = os.path.join(out_dir, row["folder"])
    os.makedirs(out_folder, exist_ok=True)
    out = os.path.join(out_folder, f"{row['product']}_jig.stl")
    write_stl(build_jig(row), out)
    return out


def _build_pockets(row, blank_w, blank_h, tv, pz, shape, ptype, cols, rows, blank_z):
    solids = []

    if shape == "rect":
        if ptype == "3wall_overrun":
            pw = blank_w + 2 * tv
            ph = base.BASE_H - WALL
            total_w = WALL + cols * pw + (cols - 1) * INTER + WALL
            x0 = (base.BASE_W - total_w) / 2 + WALL
            for c in range(cols):
                px = x0 + c * (pw + INTER) + tv
                cx, cy = sb(px + blank_w / 2, ph / 2)
                solids.append(rect_solid(blank_w, ph, pz, cx, cy))

        elif ptype.startswith("3wall"):
            # Long side (blank_w) along Y, short (blank_h) across X
            pw_x = blank_h + 2 * tv
            pl_y = blank_w + tv
            total_x = WALL + cols * pw_x + (cols - 1) * INTER + WALL
            x0 = (base.BASE_W - total_x) / 2 + WALL
            y0 = (base.BASE_H - pl_y) / 2
            tab_w_val = float(row.get("tab_w_mm") or 0)
            for r in range(rows):
                for c in range(cols):
                    px = x0 + c * (pw_x + INTER)
                    py = y0 + r * (pl_y + INTER)
                    cx, cy = sb(px + pw_x / 2, py + pl_y / 2)
                    solids.append(rect_solid(pw_x, pl_y, pz, cx, cy))
                    if tab_w_val > 0:
                        if ptype == "3wall_top_notch":
                            # Slot at jig top (b123d -Y): ring exits from closed end.
                            # Extends from jig top (-base.HH) to 2mm past pocket top edge.
                            pocket_top_b = cy - pl_y / 2
                            slot_bot_b = pocket_top_b + 2.0
                            slot_d = slot_bot_b - (-base.HH)
                            if slot_d > 0:
                                solids.append(rect_solid(
                                    tab_w_val + 2 * tv, slot_d, pz,
                                    cx, -base.HH + slot_d / 2
                                ))
                        else:
                            # Slot at jig bottom (b123d +Y): ring exits from open end.
                            # Extends from pocket bottom edge to jig edge (+base.HH).
                            pocket_bot_b = cy + pl_y / 2
                            slot_d = base.HH - pocket_bot_b
                            if slot_d > 0:
                                solids.append(rect_solid(
                                    tab_w_val + 2 * tv, slot_d, pz,
                                    cx, pocket_bot_b + slot_d / 2
                                ))

        else:
            # 4-wall enclosed
            pw = blank_w + 2 * tv
            ph = blank_h + 2 * tv
            total_w = WALL + cols * pw + (cols - 1) * INTER + WALL
            total_h = WALL + rows * ph + (rows - 1) * INTER + WALL
            x0 = (base.BASE_W - total_w) / 2 + WALL
            y0 = (base.BASE_H - total_h) / 2 + WALL
            tab_w_val = float(row.get("tab_w_mm") or 0)
            tab_l_val = float(row.get("tab_l_mm") or 0)
            for ri in range(rows):
                for ci in range(cols):
                    pcx_jig = x0 + ci * (pw + INTER) + pw / 2
                    pcy_jig = y0 + ri * (ph + INTER) + ph / 2
                    cx, cy = sb(pcx_jig, pcy_jig)
                    solids.append(rect_solid(pw, ph, pz, cx, cy))
                    if tab_w_val > 0 and tab_l_val > 0:
                        # Tab slot at +Y (bottom of pocket), extends to jig edge
                        pocket_bottom_b = cy + ph / 2
                        available = base.HH - pocket_bottom_b
                        if available > 0:
                            solids.append(rect_solid(
                                tab_w_val + 2 * tv, available, pz,
                                cx, pocket_bottom_b + available / 2
                            ))

    elif shape == "circle":
        r = blank_w / 2 + tv
        cx, cy = sb(base.BASE_W / 2, base.BASE_H / 2)
        if ptype == "cylinder_notch":
            # Circle pocket + ring slot to the jig's front edge (large b123d +Y).
            # Slot starts 2mm inside circle bottom so it overlaps and connects to pocket.
            tab_w_val = float(row.get("tab_w_mm") or 12.0)
            solids.append(circle_solid(r, pz, cx, cy))
            slot_top_b = cy + r - 2.0       # 2mm inside circle bottom edge
            slot_d = base.HH - slot_top_b        # height from there to jig bottom edge
            if slot_d > 0:
                solids.append(rect_solid(tab_w_val + 2 * tv, slot_d, pz,
                                          cx, slot_top_b + slot_d / 2))
        elif ptype == "cylinder_removal_notch":
            # Finger notch overlapping the circle at the front (+Y), to lift the blank out
            solids.append(circle_solid(r, pz, cx, cy))
            NOTCH_W, NOTCH_D, NOTCH_OVR = 20.0, 20.0, 5.0
            notch_cy_jig = base.BASE_H / 2 + r - NOTCH_OVR + NOTCH_D / 2
            ncx, ncy = sb(base.BASE_W / 2, notch_cy_jig)
            solids.append(rect_solid(NOTCH_W, NOTCH_D, pz, ncx, ncy))
        else:
            solids.append(circle_solid(r, pz, cx, cy))

    elif shape == "tombstone":
        solids.append(tombstone_solid(blank_w, blank_h, tv, pz))

    elif shape == "wallet":
        PW = blank_w + 2 * tv
        PH = blank_h + 2 * tv
        solids.append(rounded_rect_solid(PW, PH, 5.0, pz))

    elif shape == "heart":
        PW = blank_w + 2 * tv
        PH = blank_h + 2 * tv
        total_w = WALL + cols * PW + (cols - 1) * INTER + WALL
        total_h = WALL + rows * PH + (rows - 1) * INTER + WALL
        x0 = (base.BASE_W - total_w) / 2 + WALL + tv + blank_w / 2
        y0 = (base.BASE_H - total_h) / 2 + WALL + tv + blank_h / 2
        tab_w_val = float(row.get("tab_w_mm") or 0)
        tab_l_val = float(row.get("tab_l_mm") or 0)
        for ri in range(rows):
            for ci in range(cols):
                hcx = x0 + ci * (PW + INTER)
                hcy = y0 + ri * (PH + INTER)
                bx, by = sb(hcx, hcy)
                solids.append(heart_solid(blank_w + 2*tv, blank_h + 2*tv, pz, bx, by))
                if tab_w_val > 0 and tab_l_val > 0:
                    # Tab slot from jig top edge down to 2mm past notch — ensures
                    # slot and heart pocket are physically connected at the notch.
                    hh_pocket = (blank_h + 2 * tv) / 2
                    notch_b = by - hh_pocket * 0.6     # b123d Y of heart notch (top center dip)
                    slot_bot_b = notch_b + 2.0          # 2mm inside pocket past notch
                    slot_d = slot_bot_b - (-base.HH)         # total height: jig top to slot_bot_b
                    if slot_d > 0:
                        solids.append(rect_solid(
                            tab_w_val + 2 * tv, slot_d, pz,
                            bx, -base.HH + slot_d / 2
                        ))

    return solids
