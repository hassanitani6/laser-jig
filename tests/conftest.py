import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from laser_jig import base  # noqa: E402

DATA = Path(__file__).parent / "data"
EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture(autouse=True)
def default_base():
    """Every test starts and ends with the default plate, because use_base() changes module-wide settings."""
    base.use_base(**base.DEFAULT)
    yield
    base.use_base(**base.DEFAULT)


def row(**overrides) -> dict:
    r = {"product": "sample", "folder": "", "blank_w_mm": "40", "blank_h_mm": "30", "blank_z_mm": "3",
         "shape": "rect", "layout": "1x1", "pocket_type": "4wall", "tolerance": "tight",
         "tab_w_mm": "", "tab_l_mm": ""}
    r.update(overrides)
    return r
