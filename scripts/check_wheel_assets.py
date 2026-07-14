"""Guard: every non-Python runtime asset in the source tree ships in the wheel.

Compares the package's on-disk asset files (currently ``*.sql`` DuckDB
schemas, loaded via ``Path(__file__)`` at store bootstrap) against the
members of a built wheel. Exits non-zero listing anything missing — the
failure mode this guards against is a store that works in editable installs
and silently cannot bootstrap in Docker/git installs.

Usage: python scripts/check_wheel_assets.py dist/open_pulse_sources-*.whl
"""
from __future__ import annotations

import glob
import sys
import zipfile
from pathlib import Path

ASSET_GLOBS = ("**/*.sql",)
ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "open_pulse_sources"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_wheel_assets.py <wheel path or glob>")
        return 2
    matches = sorted(glob.glob(sys.argv[1]))
    if not matches:
        print(f"no wheel matches {sys.argv[1]!r} — build one with `uv build --wheel`")
        return 2
    wheel = matches[-1]
    members = set(zipfile.ZipFile(wheel).namelist())

    expected = [
        f"open_pulse_sources/{path.relative_to(PACKAGE).as_posix()}"
        for pattern in ASSET_GLOBS
        for path in sorted(PACKAGE.glob(pattern))
    ]
    missing = [name for name in expected if name not in members]

    print(f"{wheel}: {len(expected)} expected assets, {len(missing)} missing")
    if missing:
        for name in missing:
            print(f"  MISSING {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
