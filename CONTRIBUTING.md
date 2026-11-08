# Contributing

Thanks for helping! Small, focused pull requests are easiest to review.

## Set up

```bash
uv sync
uv run pytest
uv run ruff check .
```

## Ground rules

- Bug fixes come with a test that fails before the fix and passes after it.
- Geometry changes must keep `tests/data/golden.json` passing, or update it in the same pull request with an
  explanation of why every changed jig is better.
- No network access or telemetry, and no new required dependencies without an issue first.

## Where things are

`base.py` holds the plate size; `stl.py` builds the printable jig; `svg.py` draws the matching template (keep the two
in step: every pocket type exists in both); `cli.py` reads and checks the CSV; `doctor.py` the environment report.
