"""ProvenLattice V1.0 knowledge and code evidence core."""

from .graph import full_index
from .incremental import incremental_update
from .knowledge import CrossLayerResolver, index_knowledge
from .overlay import GraphView, OverlayStore, materialize_view
from .query import GraphQuery

__all__ = ["CrossLayerResolver", "GraphQuery", "GraphView", "OverlayStore", "full_index",
           "incremental_update", "index_knowledge", "materialize_view"]
__version__ = "1.0.0"
