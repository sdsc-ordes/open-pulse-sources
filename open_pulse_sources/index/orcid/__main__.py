"""Module entrypoint: delegates to the CLI."""

from __future__ import annotations

from open_pulse_sources.index.orcid.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
