"""Shared version and status constants for the Evidence Projection (GATE-0).

These encode the FactBundle v2.1 contract surface that the projection and the
adapter agree on. The ``api_version`` "v1.1" and the terminal status set are
reproduced from the frozen v1 core's *documented* contract; the frozen v1
module itself is an out-of-repo reference and is never imported at runtime
(see the package README, "Dependency closure").
"""

from __future__ import annotations

# --- envelope / version surface -------------------------------------------

API_VERSION = "v1.1"
SCHEMA_VERSION = "2.1"
CONTRACT_VERSION = "skill-graph-factbundle-contract-v2.1"
PROJECTION_VERSION = "factbundle-projection-v2.1"
ADAPTER_VERSION = "provenlattice-evidence-projection-v1"
# A1 is the core adapter here: provenance is its own, so the delegated-core
# stamp stays empty (kept for contract compatibility with A2/A3-style wrappers).
CORE_ADAPTER_VERSION = ""

# --- terminal statuses (v1 envelope) --------------------------------------

ST_OK = "ok"
ST_PARTIAL = "partial"
ST_EMPTY = "empty"
ST_UNSUPPORTED_ONLY = "unsupported_only"
ST_STALE = "stale"
ST_NOT_BUILT = "not_built"
ST_FAILED = "failed"
ST_TIMEOUT = "timeout"

# Statuses that mean "no live facts were delivered" (fail-closed terminals).
TERMINAL_STATUSES = frozenset({ST_FAILED, ST_TIMEOUT, ST_STALE, ST_NOT_BUILT})

# --- entry names -----------------------------------------------------------

ENTRY_SHARED_ACCESS = "analyze_shared_access"
ENTRY_DOUBLE_FREE = "analyze_double_free"

# Generic fact projection entries (projector-registry expansion). These are
# static entries so ``validate_bundle_v2(entry, bundle)`` keeps a deterministic
# entry -> defect_type identity instead of a dynamic "generic" entry.
ENTRY_LOCK_ORDER = "analyze_lock_order"
ENTRY_RESOURCE_LIFETIME = "analyze_resource_lifetime"
ENTRY_USE_AFTER_FREE = "analyze_use_after_free"
ENTRY_NULL_FLOW = "analyze_null_flow"
ENTRY_MISMATCHED_FREE = "analyze_mismatched_free"

GENERIC_ENTRIES = (
    ENTRY_LOCK_ORDER,
    ENTRY_RESOURCE_LIFETIME,
    ENTRY_USE_AFTER_FREE,
    ENTRY_NULL_FLOW,
    ENTRY_MISMATCHED_FREE,
)

# defect_type values each entry maps to
ENTRY_DEFECT_TYPE = {
    ENTRY_SHARED_ACCESS: "race_condition",
    ENTRY_DOUBLE_FREE: "double_free",
    ENTRY_LOCK_ORDER: "lock_order",
    ENTRY_RESOURCE_LIFETIME: "resource_lifetime",
    ENTRY_USE_AFTER_FREE: "use_after_free",
    ENTRY_NULL_FLOW: "null_flow",
    ENTRY_MISMATCHED_FREE: "mismatched_free",
}

GENERIC_DEFECT_TYPES = frozenset(
    ENTRY_DEFECT_TYPE[entry] for entry in GENERIC_ENTRIES
)
