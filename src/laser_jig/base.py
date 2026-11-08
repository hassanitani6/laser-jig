"""The jig's base plate, shared by the STL and SVG generators.

The default plate is 109 x 109 mm, 9 mm thick, with 5 mm rounded corners.
Call use_base() before generating to make jigs of another size.
"""

BASE_W = 109.0
BASE_H = 109.0
BASE_Z = 9.0
CORNER_R = 5.0
REG_INSET = 5.0      # registration dots sit this far in from the top corners
HW, HH, HZ = BASE_W / 2, BASE_H / 2, BASE_Z / 2
FIELD_W, FIELD_H = BASE_W, BASE_H

MIN_SIDE = 20.0      # two registration dots plus a usable pocket
DEFAULT = {"width": 109.0, "height": 109.0, "thickness": 9.0, "corner_radius": 5.0}


def use_base(width: float = 109.0, height: float = 109.0, thickness: float = 9.0, corner_radius: float = 5.0) -> None:
    """Set the base plate size (mm) for every jig generated afterwards."""
    global BASE_W, BASE_H, BASE_Z, CORNER_R, HW, HH, HZ, FIELD_W, FIELD_H
    for name, v in (("width", width), ("height", height), ("thickness", thickness)):
        if not 0 < v < float("inf"):
            raise ValueError(f"base {name} must be a number greater than 0 (got {v})")
    for name, v in (("width", width), ("height", height)):
        if v < MIN_SIDE:
            raise ValueError(f"base {name} must be at least {MIN_SIDE:g} mm to fit the registration dots (got {v})")
    if not 0 <= corner_radius < min(width, height) / 2:
        raise ValueError(f"corner radius must be at least 0 and less than half the smaller side (got {corner_radius})")
    if thickness < 2:
        raise ValueError(f"base thickness must be at least 2 mm so pockets have a floor (got {thickness})")
    BASE_W, BASE_H, BASE_Z, CORNER_R = float(width), float(height), float(thickness), float(corner_radius)
    HW, HH, HZ = BASE_W / 2, BASE_H / 2, BASE_Z / 2
    FIELD_W, FIELD_H = BASE_W, BASE_H
