# Changelog

Versions follow [Semantic Versioning](https://semver.org/).

## 0.1.1 — 2026-11-08

### Fixed

- On 3-wall templates whose ring slots run to the front edge, the product label and colour key were
  drawn on top of the slots. They now sit above the pockets. Jigs (STL files) are unchanged.

## 0.1.0 — 2026-11-08 (published on GitHub, not tagged)

First public release: STL jigs and matching SVG templates from a CSV of blank sizes; rectangle, circle, heart,
tombstone and rounded-rectangle pockets with tight or loose clearance, ring slots and finger notches; plate size
options; every CSV row checked before anything is written; existing files never replaced without `--overwrite`;
`doctor` command.
