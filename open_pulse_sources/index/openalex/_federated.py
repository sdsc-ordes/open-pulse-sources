"""OpenAlex registration with the federated discover/hydrate registries.

Imported lazily by ``open_pulse_sources.index._federated.dh_registry.load_*``.
"""

from __future__ import annotations

from open_pulse_sources.index._federated.dh_registry import (
    register_discoverer,
    register_hydrator,
)
from open_pulse_sources.index.openalex.discover import DISCOVERER
from open_pulse_sources.index.openalex.hydrate import HYDRATOR

register_discoverer(DISCOVERER)
register_hydrator(HYDRATOR)
