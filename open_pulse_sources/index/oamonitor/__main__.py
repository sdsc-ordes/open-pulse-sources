"""Module entrypoint: ``python -m open_pulse_sources.index.oamonitor <subcommand>``."""

from __future__ import annotations

from open_pulse_sources.index.oamonitor.cli import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
