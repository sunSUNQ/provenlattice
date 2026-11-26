"""Projector Registry V1 (Issue #83).

The unified Projector protocol + registry that wires the two GATE-0 defect
projectors (``race_condition`` / ``double_free``) into one discoverable,
fail-closed mechanism, and proves extensibility by registering a third test-only
projector on an independent ``Registry()`` (never the production ``REGISTRY``).

Positioning: stage ① (#79) froze the Canonical Evidence IR V1 (whose
``run.projector_version`` is permanently ``NOT_APPLICABLE``); this stage ②
introduces the generic Projector **mechanism** and its ``projector_version``
(``"1"``). The two are different concepts at different layers and are never
conflated:

* ``projector_version`` (this module) -- the Registry mechanism version, stored
  on each Projector and returned by ``list_projector_capabilities()``.
* ``projection_version`` (``factbundle-projection-v2.1``) -- the GATE-0 concrete
  projection implementation version, stamped by the wrapped ``adapter.analyze_*``
  on the produced FactBundle. The registry never rewrites it.
* IR V1 ``run.projector_version`` (``NOT_APPLICABLE``, frozen in ``ir.py``) --
  the IR layer's own field; this module does **not** import or modify it.

Contract constraints honoured:

* ``analyze`` forwards ``(case_workdir, database, target_symbols, **kwargs)``
  verbatim to the wrapped GATE-0 ``adapter.analyze_*`` and returns the
  FactBundle v2.1 verbatim -- no re-projection, no post-processing, no
  default injection, no ``target_symbols`` truncation.
* ``defect_type`` / ``projector_version`` are read-only (frozen) metadata; the
  registry deep-copies a projector on registration.
* duplicate ``defect_type`` is rejected (``DuplicateDefectTypeError``); an
  unknown ``defect_type`` is rejected (``UnknownDefectTypeError``); never a
  silent overwrite and never a placeholder projector.

This module only *wraps* the GATE-0 ``adapter`` (read-only reference); it never
modifies ``source.py`` / ``projection.py`` / ``adapter.py`` / ``constants.py``
or the IR V1 ``ir.py``, and never touches the Engine / parser / CFG / DFG / GT /
Prompt / Skill / Scorer.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from . import adapter
from . import constants as C

# The generic Projector *mechanism* version (this stage). Distinct from the
# GATE-0 ``projection_version`` ("factbundle-projection-v2.1") and from the
# frozen IR V1 ``run.projector_version`` ("NOT_APPLICABLE").
PROJECTOR_MECHANISM_VERSION = "1"


class DuplicateDefectTypeError(ValueError):
    """A ``defect_type`` is already registered (fail-closed, never overwrite)."""


class UnknownDefectTypeError(KeyError):
    """A ``defect_type`` is not registered (fail-closed, never a placeholder)."""


class Projector(Protocol):
    """Unified projector interface: one implementation == one defect type.

    ``analyze`` has the same signature and contract as a GATE-0
    ``adapter.analyze_*`` entry point (``-> FactBundle v2.1``).
    """

    defect_type: str
    projector_version: str

    def analyze(self, case_workdir, database, target_symbols=(), **kwargs) -> dict:
        """Project one defect type to a FactBundle v2.1."""
        ...


@dataclass(frozen=True, slots=True)
class AdapterProjector:
    """A concrete, read-only Projector that wraps one ``adapter.analyze_*``.

    ``defect_type`` and ``projector_version`` are frozen metadata (no setter).
    ``_analyze`` holds the wrapped GATE-0 entry point (a read-only reference;
    the adapter module itself is never modified). ``analyze`` forwards its
    arguments verbatim and returns the bundle verbatim.
    """

    defect_type: str
    projector_version: str
    _analyze: Callable[..., dict] = field(repr=False, compare=False)

    def analyze(self, case_workdir, database, target_symbols=(), **kwargs) -> dict:
        return self._analyze(case_workdir, database, target_symbols, **kwargs)


class Registry:
    """A deterministic, fail-closed projector registry.

    Instantiable: tests use a fresh ``Registry()``; production uses the module
    global ``REGISTRY``. Each instance is independent (no shared mutable state).
    """

    def __init__(self) -> None:
        self._by_defect_type: dict[str, Projector] = {}

    def register_projector(self, projector: Projector) -> None:
        """Register a projector; reject a duplicate ``defect_type`` (fail-closed).

        The projector is deep-copied so the registry owns an immutable snapshot;
        later mutation of the caller's object cannot affect the registry.
        """
        self._validate(projector)
        defect_type = projector.defect_type
        if defect_type in self._by_defect_type:
            raise DuplicateDefectTypeError(
                "defect_type already registered: %r" % (defect_type,))
        self._by_defect_type[defect_type] = copy.deepcopy(projector)

    def get_projector(self, defect_type: str) -> Projector:
        """Return the projector for ``defect_type``; reject unknown (fail-closed)."""
        try:
            return self._by_defect_type[defect_type]
        except KeyError:
            raise UnknownDefectTypeError(
                "unknown defect_type: %r (registered: %r)"
                % (defect_type, sorted(self._by_defect_type))) from None

    def list_projector_capabilities(self) -> list[dict[str, str]]:
        """Capability discovery, deterministically sorted by ``defect_type``."""
        return [
            {"defect_type": defect_type, "projector_version": projector.projector_version}
            for defect_type, projector in sorted(self._by_defect_type.items())
        ]

    def analyze(self, defect_type: str, case_workdir, database,
                target_symbols=(), **kwargs: Any) -> dict:
        """Convenience: resolve ``defect_type`` then forward ``analyze`` as-is."""
        return self.get_projector(defect_type).analyze(
            case_workdir, database, target_symbols, **kwargs)

    @staticmethod
    def _validate(projector: Projector) -> None:
        defect_type = getattr(projector, "defect_type", None)
        projector_version = getattr(projector, "projector_version", None)
        analyze = getattr(projector, "analyze", None)
        if not isinstance(defect_type, str) or not defect_type:
            raise ValueError("projector.defect_type must be a non-empty string")
        if not isinstance(projector_version, str) or not projector_version:
            raise ValueError("projector.projector_version must be a non-empty string")
        if not callable(analyze):
            raise TypeError("projector.analyze must be callable")


# --- production global registry: two built-in projectors ---------------------

REGISTRY = Registry()
REGISTRY.register_projector(AdapterProjector(
    defect_type=C.ENTRY_DEFECT_TYPE[C.ENTRY_SHARED_ACCESS],
    projector_version=PROJECTOR_MECHANISM_VERSION,
    _analyze=adapter.analyze_shared_access,
))
REGISTRY.register_projector(AdapterProjector(
    defect_type=C.ENTRY_DEFECT_TYPE[C.ENTRY_DOUBLE_FREE],
    projector_version=PROJECTOR_MECHANISM_VERSION,
    _analyze=adapter.analyze_double_free,
))

# Generic fact projectors (projector-registry expansion). Each entry is a
# read-only wrapper over the adapter's static entry point; the registry remains
# pure forwarding, so its bundle is byte-identical to the direct entry.
for _entry, _analyze in (
    (C.ENTRY_LOCK_ORDER, adapter.analyze_lock_order),
    (C.ENTRY_RESOURCE_LIFETIME, adapter.analyze_resource_lifetime),
    (C.ENTRY_USE_AFTER_FREE, adapter.analyze_use_after_free),
    (C.ENTRY_NULL_FLOW, adapter.analyze_null_flow),
    (C.ENTRY_MISMATCHED_FREE, adapter.analyze_mismatched_free),
):
    REGISTRY.register_projector(AdapterProjector(
        defect_type=C.ENTRY_DEFECT_TYPE[_entry],
        projector_version=PROJECTOR_MECHANISM_VERSION,
        _analyze=_analyze,
    ))


__all__ = [
    "PROJECTOR_MECHANISM_VERSION",
    "DuplicateDefectTypeError",
    "UnknownDefectTypeError",
    "Projector",
    "AdapterProjector",
    "Registry",
    "REGISTRY",
]
