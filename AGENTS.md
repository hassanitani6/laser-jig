# Notes for coding agents

- Install: `uv sync`. Test: `uv run pytest` (a few seconds). Lint: `uv run ruff check .`.
- Package code is in `src/laser_jig/`. `base.use_base()` sets module-wide plate settings; tests reset them.
- STL and SVG must agree: a pocket type changed in `stl.py` needs the same change in `svg.py`.
- Every change needs a test; test data is synthetic (`tests/data/`).
- Do not add network calls or telemetry.
