"""SVG alignment templates, drawn 1:1 at the jig's size:
  GREY  outline   — the jig's base plate
  BLUE  outlines  — where each blank sits
  GREEN dashed    — 2 mm engraving safe zone inside each blank
Import a template into your laser software as a locked reference layer.
"""

import os

from . import base

FIELD_MARGIN = 3.0      # wall thickness — pocket starts 3mm from jig edge
WALL = 3.0
INTER_WALL = 2.0
TOLERANCE_TIGHT = 0.5
TOLERANCE_LOOSE = 0.8
SAFE_ZONE = 2.0         # green inset from blank edge


def get_tol(t_type):
    return TOLERANCE_TIGHT if t_type == "tight" else TOLERANCE_LOOSE


def jig_to_svg(x, y):
    """Jig coords and SVG coords are the same (the SVG shows the whole base plate)."""
    return x, y


def f(v):
    return f"{v:.3f}"


def rect_el(x, y, w, h, fill, stroke, sw, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def circle_el(cx, cy, radius, fill, stroke, sw, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(radius)}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def line_el(x1, y1, x2, y2, stroke, sw, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" '
            f'stroke="{stroke}" stroke-width="{sw}"{d}/>')


def text_el(x, y, content, size=3.0, anchor="middle", color="#555"):
    return (f'<text x="{f(x)}" y="{f(y)}" font-size="{size}" '
            f'text-anchor="{anchor}" fill="{color}" font-family="Arial,sans-serif">'
            f'{content}</text>')


def heart_path_d(cx, cy, w, h):
    """SVG cubic-bezier heart: puffy shape with rounded bottom.
    4 segments: top-notch → right widest → bottom → left widest → top-notch.
    Horizontal tangent at bottom ensures smooth arc (no cusp)."""
    hw, hh = w / 2.0, h / 2.0
    # SVG Y increases downward: lobes at small y (top), rounded bottom at large y (bottom).
    nx, ny = cx, cy - hh * 0.6           # top notch
    return (
        f"M {f(nx)},{f(ny)} "
        # notch → right widest (over right lobe); hw*0.25 CP1 → consistently rounded arc
        f"C {f(cx + hw*0.25)},{f(cy - hh)} "
        f"{f(cx + hw)},{f(cy - hh)} "
        f"{f(cx + hw)},{f(cy - hh*0.4)} "
        # right widest → bottom tip; CP2 at hh level → horizontal tangent, no cusp
        f"C {f(cx + hw)},{f(cy + hh*0.05)} "
        f"{f(cx + hw*0.1)},{f(cy + hh)} "
        f"{f(cx)},{f(cy + hh)} "
        # bottom tip → left widest
        f"C {f(cx - hw*0.1)},{f(cy + hh)} "
        f"{f(cx - hw)},{f(cy + hh*0.05)} "
        f"{f(cx - hw)},{f(cy - hh*0.4)} "
        # left widest → notch (over left lobe)
        f"C {f(cx - hw)},{f(cy - hh)} "
        f"{f(cx - hw*0.25)},{f(cy - hh)} "
        f"{f(nx)},{f(ny)} Z"
    )


def build_pockets(row, tol_val, cols, rows):
    """Return list of SVG element strings for this product's pocket layout."""
    blank_w = float(row["blank_w_mm"])
    blank_h = float(row["blank_h_mm"]) if row["blank_h_mm"] else 0.0
    shape = row["shape"]
    pocket_type = row["pocket_type"]
    els = []

    if shape == "rect":
        pw = blank_w + 2 * tol_val
        ph = blank_h + 2 * tol_val

        if pocket_type == "3wall_overrun":
            total_w = WALL + cols * pw + (cols - 1) * INTER_WALL + WALL
            x0 = (base.BASE_W - total_w) / 2 + WALL
            # Pocket starts at FIELD_MARGIN so blank back edge aligns with work-area top
            y0 = FIELD_MARGIN
            for c in range(cols):
                px = x0 + c * (pw + INTER_WALL) + tol_val
                py = y0 + tol_val
                sx, sy = jig_to_svg(px, py)
                sy = max(sy, 0.0)      # clamp: back edge at canvas top (blank overruns upward)
                vis_h = min(blank_h, base.FIELD_H - sy)
                els.append(rect_el(sx, sy, blank_w, vis_h,
                                   "rgba(0,100,220,0.06)", "blue", 0.3))
                if vis_h > 2 * SAFE_ZONE and blank_w > 2 * SAFE_ZONE:
                    els.append(rect_el(sx + SAFE_ZONE, sy + SAFE_ZONE,
                                       blank_w - 2 * SAFE_ZONE,
                                       vis_h - 2 * SAFE_ZONE,
                                       "none", "#008800", 0.25, "2,1"))
                els.append(text_el(sx + blank_w / 2, base.BASE_H - 4,
                                   "↓ blank overruns plate front edge", 2.2, "middle", "#cc0000"))
        elif pocket_type.startswith("3wall"):
            # Long side (blank_w) along Y, short side (blank_h) across X.
            # Matches stl._build_pockets 3wall branch exactly.
            pw_x = blank_h + 2 * tol_val
            pl_y = blank_w + tol_val
            total_x = WALL + cols * pw_x + (cols - 1) * INTER_WALL + WALL
            x0 = (base.BASE_W - total_x) / 2 + WALL
            y0 = (base.BASE_H - pl_y) / 2
            tab_w_val = float(row.get("tab_w_mm") or 0)
            for ri in range(rows):
                for ci in range(cols):
                    px = x0 + ci * (pw_x + INTER_WALL)
                    py = y0 + ri * (pl_y + INTER_WALL)
                    sx, sy = jig_to_svg(px + tol_val, py)
                    els.append(rect_el(sx, sy, blank_h, blank_w,
                                       "rgba(0,100,220,0.06)", "blue", 0.3))
                    if blank_h > 2 * SAFE_ZONE and blank_w > 2 * SAFE_ZONE:
                        els.append(rect_el(sx + SAFE_ZONE, sy + SAFE_ZONE,
                                           blank_h - 2 * SAFE_ZONE,
                                           blank_w - 2 * SAFE_ZONE,
                                           "none", "#008800", 0.25, "2,1"))
                    if tab_w_val > 0:
                        pcx_svg = px + pw_x / 2
                        slot_x = pcx_svg - tab_w_val / 2
                        if pocket_type == "3wall_top_notch":
                            # Slot from jig top (y=0) down to 2mm past pocket top
                            slot_h = py + 2.0
                            if slot_h > 0:
                                els.append(rect_el(
                                    slot_x, 0.0,
                                    tab_w_val, slot_h,
                                    "rgba(0,100,220,0.06)", "blue", 0.3, "1,0.5"
                                ))
                        else:
                            # Slot from pocket bottom to jig bottom edge
                            slot_top_svg = py + pl_y
                            slot_h = base.BASE_H - slot_top_svg
                            if slot_h > 0:
                                els.append(rect_el(
                                    slot_x, slot_top_svg,
                                    tab_w_val, slot_h,
                                    "rgba(0,100,220,0.06)", "blue", 0.3, "1,0.5"
                                ))
        else:
            total_w = WALL + cols * pw + (cols - 1) * INTER_WALL + WALL
            total_h = WALL + rows * ph + (rows - 1) * INTER_WALL + WALL
            x0 = (base.BASE_W - total_w) / 2 + WALL
            y0 = (base.BASE_H - total_h) / 2 + WALL
            for ri in range(rows):
                for ci in range(cols):
                    px = x0 + ci * (pw + INTER_WALL) + tol_val
                    py = y0 + ri * (ph + INTER_WALL) + tol_val
                    sx, sy = jig_to_svg(px, py)
                    els.append(rect_el(sx, sy, blank_w, blank_h,
                                       "rgba(0,100,220,0.06)", "blue", 0.3))
                    if blank_w > 2 * SAFE_ZONE and blank_h > 2 * SAFE_ZONE:
                        els.append(rect_el(sx + SAFE_ZONE, sy + SAFE_ZONE,
                                           blank_w - 2 * SAFE_ZONE,
                                           blank_h - 2 * SAFE_ZONE,
                                           "none", "#008800", 0.25, "2,1"))

    elif shape == "circle":
        r_blank = blank_w / 2.0
        cx_p = base.BASE_W / 2.0
        cy_p = base.BASE_H / 2.0
        scx, scy = jig_to_svg(cx_p, cy_p)
        els.append(circle_el(scx, scy, r_blank,
                              "rgba(0,100,220,0.06)", "blue", 0.3))
        if r_blank > SAFE_ZONE:
            els.append(circle_el(scx, scy, r_blank - SAFE_ZONE,
                                  "none", "#008800", 0.25, "2,1"))
        if pocket_type == "cylinder_notch":
            # Ring slot from the circle's bottom edge toward the jig's bottom edge
            tab_w_val = float(row.get("tab_w_mm") or 12.0)
            tab_l_val = float(row.get("tab_l_mm") or 12.0)
            slot_top = scy + r_blank
            slot_h = min(tab_l_val, base.BASE_H - slot_top)
            if slot_h > 0:
                els.append(rect_el(
                    scx - tab_w_val / 2, slot_top,
                    tab_w_val, slot_h,
                    "rgba(0,100,220,0.06)", "blue", 0.3, "1,0.5"
                ))
        elif pocket_type == "cylinder_removal_notch":
            # Finger notch at the bottom overlaps the circle, to lift the blank out
            NOTCH_W, NOTCH_D, NOTCH_OVR = 20.0, 20.0, 5.0
            r_pkt = r_blank + tol_val
            ny_top = cy_p + r_pkt - NOTCH_OVR
            nx_left = cx_p - NOTCH_W / 2
            nx_svg, ny_svg = jig_to_svg(nx_left, ny_top)
            els.append(rect_el(nx_svg, ny_svg, NOTCH_W, NOTCH_D,
                               "rgba(0,100,220,0.06)", "blue", 0.3))
            els.append(text_el(scx, ny_svg + NOTCH_D / 2,
                               "removal notch", 2.5, "middle", "blue"))

    elif shape == "tombstone":
        # Tombstone: round end (semicircle R=blank_w/2) at the back of the plate (top of SVG),
        # straight body with R=3mm rounded corners at the other end (bottom of SVG).
        r = blank_w / 2.0          # semicircle radius
        corner_r = 3.0              # bottom-corner radius
        straight_h = blank_h - r   # straight section

        # The tag may run past the plate's back edge; the semicircle centre sits FIELD_MARGIN + r from it.
        y_ctr_jig = FIELD_MARGIN + r
        x_ctr_jig = base.BASE_W / 2.0
        sx_ctr, sy_ctr = jig_to_svg(x_ctr_jig, y_ctr_jig)

        def _tombstone_d(cx, cy_eq, w, sh, cr):
            """Tombstone path: semicircle up from cy_eq, rect body down, rounded bottom corners."""
            rr = w / 2.0
            left, right = cx - rr, cx + rr
            wall_end_y = cy_eq + sh - cr    # where straight wall ends before corner
            bottom_y = cy_eq + sh
            return (
                f"M {f(left)},{f(cy_eq)} "
                f"A {f(rr)},{f(rr)} 0 0 1 {f(right)},{f(cy_eq)} "   # top semicircle (sweep=1 = upward arc)
                f"L {f(right)},{f(wall_end_y)} "
                f"A {f(cr)},{f(cr)} 0 0 1 {f(right - cr)},{f(bottom_y)} "  # bottom-right corner
                f"L {f(left + cr)},{f(bottom_y)} "
                f"A {f(cr)},{f(cr)} 0 0 1 {f(left)},{f(wall_end_y)} Z"     # bottom-left corner
            )

        d1 = _tombstone_d(sx_ctr, sy_ctr, blank_w, straight_h, corner_r)
        els.append(f'<path d="{d1}" fill="rgba(0,100,220,0.06)" stroke="blue" stroke-width="0.3"/>')

        r_s = r - SAFE_ZONE
        sh_s = straight_h - SAFE_ZONE
        cr_s = max(0.5, corner_r - SAFE_ZONE)
        if r_s > 0 and sh_s > cr_s:
            d2 = _tombstone_d(sx_ctr, sy_ctr, blank_w - 2 * SAFE_ZONE, sh_s, cr_s)
            els.append(f'<path d="{d2}" fill="none" stroke="#008800" '
                       f'stroke-width="0.25" stroke-dasharray="2,1"/>')

    elif shape == "wallet":
        # Plain rounded rectangle
        cr = 5.0
        pw = blank_w + 2 * tol_val
        ph = blank_h + 2 * tol_val
        x0_jig = (base.BASE_W - pw) / 2.0 + tol_val
        y0_jig = (base.BASE_H - ph) / 2.0 + tol_val
        sx0, sy0 = jig_to_svg(x0_jig, y0_jig)
        w, h = blank_w, blank_h

        def _rrect_d(ox, oy, ww, hh, c):
            right, bottom = ox + ww, oy + hh
            return (
                f"M {f(ox + c)},{f(oy)} L {f(right - c)},{f(oy)} "
                f"A {f(c)},{f(c)} 0 0 1 {f(right)},{f(oy + c)} "
                f"L {f(right)},{f(bottom - c)} "
                f"A {f(c)},{f(c)} 0 0 1 {f(right - c)},{f(bottom)} "
                f"L {f(ox + c)},{f(bottom)} "
                f"A {f(c)},{f(c)} 0 0 1 {f(ox)},{f(bottom - c)} "
                f"L {f(ox)},{f(oy + c)} "
                f"A {f(c)},{f(c)} 0 0 1 {f(ox + c)},{f(oy)} Z"
            )

        els.append(f'<path d="{_rrect_d(sx0, sy0, w, h, cr)}" '
                   f'fill="rgba(0,100,220,0.06)" stroke="blue" stroke-width="0.3"/>')
        cr_s = max(0.5, cr - SAFE_ZONE)
        if w > 2 * SAFE_ZONE and h > 2 * SAFE_ZONE:
            inner = _rrect_d(sx0 + SAFE_ZONE, sy0 + SAFE_ZONE, w - 2 * SAFE_ZONE, h - 2 * SAFE_ZONE, cr_s)
            els.append(f'<path d="{inner}" '
                       f'fill="none" stroke="#008800" stroke-width="0.25" stroke-dasharray="2,1"/>')

    elif shape == "heart":
        pw = blank_w + 2 * tol_val
        ph = blank_h + 2 * tol_val
        total_w = WALL + cols * pw + (cols - 1) * INTER_WALL + WALL
        total_h = WALL + rows * ph + (rows - 1) * INTER_WALL + WALL
        x0 = (base.BASE_W - total_w) / 2 + WALL + tol_val + blank_w / 2
        y0 = (base.BASE_H - total_h) / 2 + WALL + tol_val + blank_h / 2
        for ri in range(rows):
            for ci in range(cols):
                hcx = x0 + ci * (pw + INTER_WALL)
                hcy = y0 + ri * (ph + INTER_WALL)
                scx, scy = jig_to_svg(hcx, hcy)
                d1 = heart_path_d(scx, scy, blank_w, blank_h)
                d2 = heart_path_d(scx, scy,
                                  blank_w - 2 * SAFE_ZONE,
                                  blank_h - 2 * SAFE_ZONE)
                els.append(f'<path d="{d1}" fill="rgba(0,100,220,0.06)" '
                            f'stroke="blue" stroke-width="0.3"/>')
                els.append(f'<path d="{d2}" fill="none" stroke="#008800" '
                            f'stroke-width="0.25" stroke-dasharray="2,1"/>')
                tab_w_val = float(row.get("tab_w_mm") or 0)
                tab_l_val = float(row.get("tab_l_mm") or 0)
                if tab_w_val > 0 and tab_l_val > 0:
                    # Tab slot from jig top (y=0) down to 2mm past notch.
                    # Matches STL: slot and heart pocket connect at the notch.
                    notch_svg_y = scy - (blank_h / 2.0) * 0.6  # notch Y in SVG (Y-down)
                    slot_h = notch_svg_y + 2.0                   # slot bottom = notch + 2mm
                    if slot_h > 0:
                        els.append(rect_el(
                            scx - tab_w_val / 2, 0.0,
                            tab_w_val, slot_h,
                            "rgba(0,100,220,0.06)", "blue", 0.3, "1,0.5"
                        ))

    return els


def svg_text(row):
    """The SVG template for one CSV row, as text (nothing is written)."""
    product = row["product"]
    tol_val = get_tol(row["tolerance"])
    layout = row["layout"].lower()
    cols, rows = (int(x) for x in layout.split("x")) if "x" in layout else (1, 1)

    pocket_els = build_pockets(row, tol_val, cols, rows)

    label = product.replace("_", " ").title()

    # Registration marks match the raised dots on the printed jig. With two-point positioning in your laser
    # software, jog to the left dot, then the right one, and every outline lines up with the jig.
    _rg = 1.5   # crosshair circle radius (mm)
    def _reg(cx, cy):
        return [
            f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(_rg)}" fill="none" stroke="#999" stroke-width="0.25"/>',
            f'<line x1="{f(cx-_rg-1)}" y1="{f(cy)}" x2="{f(cx+_rg+1)}" y2="{f(cy)}" stroke="#999" stroke-width="0.2"/>',
            f'<line x1="{f(cx)}" y1="{f(cy-_rg-1)}" x2="{f(cx)}" y2="{f(cy+_rg+1)}" stroke="#999" stroke-width="0.2"/>',
        ]
    reg_marks = (
        _reg(base.REG_INSET, base.REG_INSET) + _reg(base.BASE_W - base.REG_INSET, base.REG_INSET)
        + [text_el(base.REG_INSET, base.REG_INSET - 1.5, "REG", 1.6, "left", "#999")]
    )

    # Place label below blank outline when there is room (≥5mm before canvas edge).
    shape = row["shape"]
    pocket_type = row["pocket_type"]
    blank_w = float(row["blank_w_mm"])
    blank_h = float(row.get("blank_h_mm") or 0)
    tol_v = get_tol(row["tolerance"])
    _, rows_n = (int(x) for x in row["layout"].lower().split("x")) if "x" in row["layout"] else (1, 1)

    LABEL_FALLBACK = base.BASE_H - 3.0    # near-bottom label row

    if shape == "tombstone":
        # Tag overruns back edge; label near bottom where there's always room.
        label_y, legend_y = LABEL_FALLBACK, None
    elif shape == "circle":
        r = blank_w / 2.0
        blank_bottom_svg = base.BASE_H / 2 + r
        if pocket_type == "cylinder_removal_notch":
            NOTCH_D, NOTCH_OVR = 20.0, 5.0
            r_pkt = r + tol_v
            feature_bottom = base.BASE_H / 2 + r_pkt - NOTCH_OVR + NOTCH_D
            label_y = feature_bottom + 3.0
            legend_y = label_y + 3.5 if label_y + 3.5 < base.BASE_H else None
        elif pocket_type == "cylinder_notch":
            tab_l_val = float(row.get("tab_l_mm") or 12.0)
            feature_bottom = blank_bottom_svg + tab_l_val
            label_y = min(feature_bottom + 3.0, base.BASE_H - 4.0)
            legend_y = label_y + 3.5 if label_y + 3.5 < base.BASE_H else None
        else:
            label_y = blank_bottom_svg + 3.0
            legend_y = blank_bottom_svg + 6.5 if label_y < base.BASE_H - 6 else None
    elif pocket_type.startswith("3wall") and not pocket_type.endswith("overrun"):
        # 3-wall pockets: long dimension (blank_w) runs along Y; rows_n rows stacked.
        pl = blank_w + tol_v       # pocket length along Y (one tolerance — open ring end)
        ph_total = rows_n * pl + (rows_n - 1) * INTER_WALL
        y0_svg = (base.BASE_H - ph_total) / 2
        blank_bottom_svg = y0_svg + ph_total
        if pocket_type != "3wall_top_notch" and float(row.get("tab_w_mm") or 0) > 0:
            # The ring slots fill the space below the pockets, so the label goes above them instead.
            label_y = max(y0_svg - 3.0, 4.0)
            legend_y = label_y - 4.0 if label_y - 4.0 >= 3.0 else None
        else:
            label_y = blank_bottom_svg + 3.0
            legend_y = blank_bottom_svg + 6.5 if label_y < base.BASE_H - 6 else None
    elif blank_h > 0:
        ph_row = blank_h + 2 * tol_v
        ph_total = rows_n * ph_row + (rows_n - 1) * INTER_WALL + 2 * WALL
        y0_svg = (base.BASE_H - ph_total) / 2 + WALL
        blank_bottom_svg = y0_svg + rows_n * ph_row + (rows_n - 1) * INTER_WALL
        if blank_bottom_svg < base.BASE_H - 8:
            label_y = blank_bottom_svg + 3.0
            legend_y = blank_bottom_svg + 6.5
        else:
            label_y, legend_y = LABEL_FALLBACK, None
    else:
        label_y, legend_y = LABEL_FALLBACK, None

    footer = [text_el(base.BASE_W / 2, label_y, label, 3.2, "middle", "#333")]
    if legend_y:
        footer.append(text_el(base.BASE_W / 2, legend_y,
                               f"BLUE=blank edge | GREEN DASH=safe zone | GREY={base.BASE_W:g}mm jig boundary",
                               1.8, "middle", "#aaa"))

    jig_border = (
        f'<rect x="0" y="0" width="{f(base.BASE_W)}" height="{f(base.BASE_H)}" '
        f'rx="{f(base.CORNER_R)}" ry="{f(base.CORNER_R)}" '
        f'fill="none" stroke="#bbb" stroke-width="0.4"/>'
    )
    body_lines = (
        [jig_border]
        + reg_marks
        + pocket_els
        + footer
    )

    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg"\n'
        f'     width="{f(base.BASE_W)}mm" height="{f(base.BASE_H)}mm"\n'
        f'     viewBox="0 0 {f(base.BASE_W)} {f(base.BASE_H)}">\n'
        f'  <!-- Laser jig template: {product} -->\n'
        '  <!-- Import into your laser software as a locked reference layer -->\n'
        + "".join(f"  {el}\n" for el in body_lines)
        + "</svg>\n"
    )

    return svg


def write_svg(text, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def generate_svg(row, out_dir="."):
    out_folder = os.path.join(out_dir, row["folder"])
    os.makedirs(out_folder, exist_ok=True)
    out = os.path.join(out_folder, f"{row['product']}_jig.svg")
    write_svg(svg_text(row), out)
    return out
