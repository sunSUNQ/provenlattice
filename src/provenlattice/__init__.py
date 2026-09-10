"""ProvenLattice Core V0."""

from .graph import full_index
from .incremental import incremental_update
from .query import GraphQuery

__all__ = ["GraphQuery", "full_index", "incremental_update"]
__version__ = "0.2.0"
