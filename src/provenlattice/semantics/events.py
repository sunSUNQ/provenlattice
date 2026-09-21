from __future__ import annotations

from dataclasses import dataclass, field


# Design doc §13 splits semantic events into levels. Level 0 is extracted
# unconditionally; level 1 waits until a defect rule asks for it; level 2 is
# rebuilt on demand as a local deep graph rather than stored.
LEVEL_0_EVENTS = frozenset({
    "CALL", "RETURN", "THROW",
    "ALLOC", "RELEASE",
    "LOCK", "UNLOCK", "ATOMIC",
    "THREAD_SPAWN", "THREAD_JOIN",
})

# Level 1 holds two different things, and the distinction matters:
#
#   READ / WRITE / DEREFERENCE / CHECK / BRANCH are level 1 by design -- they
#   are only extracted for symbols a defect rule has already flagged.
#
#   OPEN / CLOSE / ACQUIRE / WAIT / SIGNAL / CREATE / DESTROY are level 1 by
#   omission. The design doc §23 lists them as node types, but the stage 2
#   level 0 list in appendix B.4 does not include them. Keeping them here means
#   a matrix entry that needs them -- 4.5 non-memory resource leak, graded A --
#   is reported as "requires an event we do not yet extract" instead of
#   silently looking supported.
LEVEL_1_EVENTS = frozenset({
    "READ", "WRITE", "DEREFERENCE", "CHECK", "BRANCH",
    "OPEN", "CLOSE", "ACQUIRE", "WAIT", "SIGNAL", "CREATE", "DESTROY",
})

KNOWN_EVENTS = LEVEL_0_EVENTS | LEVEL_1_EVENTS


def event_level(event_type: str) -> int:
    if event_type in LEVEL_0_EVENTS:
        return 0
    if event_type in LEVEL_1_EVENTS:
        return 1
    raise KeyError(f"unknown event type: {event_type}")


@dataclass(frozen=True, slots=True)
class SemanticEvent:
    """One defect-relevant operation inside a method body.

    Identity is method-anchored, not position-anchored (appendix B.2.1): the id
    derives from the owning symbol plus the event's ordinal within that method,
    never from a line number. Editing a different method therefore leaves this
    id untouched, which is what keeps incremental deltas bounded.
    """

    event_id: str
    event_type: str
    owner_symbol_id: str
    file_id: str
    ordinal: int
    start_line: int
    end_line: int
    # How this event was found, kept as evidence rather than discarded: which
    # keyword or node type matched, and by which axis.
    matched_name: str
    matched_via: str
    flags: tuple[str, ...] = field(default=())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "owner_symbol_id": self.owner_symbol_id,
            "file_id": self.file_id,
            "ordinal": self.ordinal,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "matched_name": self.matched_name,
            "matched_via": self.matched_via,
            "flags": list(self.flags),
            "metadata": dict(self.metadata),
        }
