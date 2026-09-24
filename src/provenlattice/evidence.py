from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


EVIDENCE_KINDS = {
    "CODE_DEFINITION", "CALL_RELATION", "REFERENCE", "DEPENDENCY",
    "SHARD_RELATION", "DOCUMENT_SECTION", "CROSS_LAYER_LINK",
    "DEFECT_CANDIDATE",
}
PREFIXES = {
    "CODE_DEFINITION": "CODE", "CALL_RELATION": "CALL", "REFERENCE": "REF",
    "DEPENDENCY": "DEP", "SHARD_RELATION": "SHARD", "DOCUMENT_SECTION": "DOC",
    "CROSS_LAYER_LINK": "XLINK", "DEFECT_CANDIDATE": "DEFECT",
}


def evidence_id(kind: str, repository: str, source_id: str, relation: str,
                target_id: str, fact_id: str = "") -> str:
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"unsupported evidence kind: {kind}")
    canonical = json.dumps(
        [repository, kind, source_id, relation, target_id, fact_id],
        ensure_ascii=False, separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"E-{PREFIXES[kind]}-{digest[:24]}"


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    kind: str
    source_id: str
    relation: str
    target_id: str
    repository: str
    commit: str
    generation: int
    provenance: str
    confidence: float
    source_path: str | None
    source_range: dict[str, int | None] | None
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls, *, kind: str, source_id: str, relation: str, target_id: str,
        repository: str, commit: str, generation: int, provenance: str,
        confidence: float, source_path: str | None, start_line: int | None,
        end_line: int | None, summary: str, fact_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "Evidence":
        return cls(
            evidence_id(kind, repository, source_id, relation, target_id, fact_id),
            kind, source_id, relation, target_id, repository, commit, generation,
            provenance, float(confidence), source_path,
            ({"start_line": start_line, "end_line": end_line}
             if start_line is not None or end_line is not None else None),
            summary, dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class QueryBudget:
    max_evidence: int = 20
    max_symbols: int = 8
    max_edges: int = 12
    max_sections: int = 6

    def __post_init__(self) -> None:
        if min(self.max_evidence, self.max_symbols, self.max_edges, self.max_sections) < 0:
            raise ValueError("query budgets must be >= 0")

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def rank_evidence(values: Iterable[Evidence]) -> list[Evidence]:
    status_rank = {"resolved": 2, "ambiguous": 1, "unresolved": 0}

    def key(item: Evidence) -> tuple:
        metadata = item.metadata
        return (
            -status_rank.get(str(metadata.get("resolution_status", "resolved")), 0),
            -int(bool(metadata.get("direct", True))),
            -item.confidence,
            int(metadata.get("distance", 0)),
            -int(bool(metadata.get("boundary_relevant", False))),
            item.evidence_id,
        )

    return sorted(values, key=key)


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    anchor: str
    intent: str
    summary: str
    primary_evidence: tuple[Evidence, ...]
    supporting_evidence: tuple[Evidence, ...]
    related_entities: tuple[dict[str, Any], ...]
    uncertainties: tuple[str, ...]
    provenance: tuple[str, ...]
    generation: int
    budget: QueryBudget

    @classmethod
    def create(
        cls, *, anchor: str, intent: str, summary: str,
        primary_evidence: Iterable[Evidence], supporting_evidence: Iterable[Evidence],
        related_entities: Iterable[dict[str, Any]], uncertainties: Iterable[str],
        generation: int, budget: QueryBudget,
    ) -> "EvidenceBundle":
        primary = rank_evidence(primary_evidence)
        supporting = rank_evidence(supporting_evidence)
        selected_primary = primary[:budget.max_evidence]
        remaining = max(budget.max_evidence - len(selected_primary), 0)
        selected_supporting = supporting[:remaining]
        combined = [*selected_primary, *selected_supporting]
        return cls(
            anchor, intent, summary, tuple(selected_primary), tuple(selected_supporting),
            tuple(dict(item) for item in list(related_entities)[:budget.max_symbols]),
            tuple(uncertainties), tuple(sorted({item.provenance for item in combined})),
            generation, budget,
        )

    @property
    def evidence_ids(self) -> list[str]:
        return [item.evidence_id for item in (*self.primary_evidence, *self.supporting_evidence)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor, "intent": self.intent, "summary": self.summary,
            "primary_evidence": [item.to_dict() for item in self.primary_evidence],
            "supporting_evidence": [item.to_dict() for item in self.supporting_evidence],
            "related_entities": list(self.related_entities),
            "uncertainties": list(self.uncertainties), "provenance": list(self.provenance),
            "generation": self.generation, "budget": self.budget.to_dict(),
            "returned_evidence_ids": self.evidence_ids,
            "returned_evidence_count": len(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class DefectEvidenceBundle:
    """One defect candidate's evidence, in the shape design doc §15 froze.

    The first eight members are §15's verbatim -- `facts` are what the graph
    proved, `uncertain_facts` what it could not, and `missing_evidence` names
    what a stronger analysis would have to add. The bookkeeping keys follow,
    because a reader comparing a bundle against §15 should meet the same block
    first.

    This is a parallel type, not a subclass of `EvidenceBundle`. That one is a
    *retrieval* bundle: it ranks and truncates heterogeneous evidence under a
    `QueryBudget`. Here the evidence is one candidate and its path, the
    truncation already happened inside the query (`max_candidates`,
    `max_paths`), and inheriting would force §15's members into fields that
    mean something else.
    """

    defect_type: str
    defect_key: str
    subject: dict[str, Any]
    facts: tuple[dict[str, Any], ...]
    uncertain_facts: tuple[dict[str, Any], ...]
    paths: tuple[dict[str, Any], ...]
    source_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    candidate_id: str
    anchor: str
    resolution_status: str
    confidence: float
    generation: int

    def to_dict(self) -> dict[str, Any]:
        """JSON-native throughout: this goes straight into a query result's
        `data` and out through the CLI's `json.dumps` without a second pass."""
        return {
            "defect_type": self.defect_type,
            "defect_key": self.defect_key,
            "subject": dict(self.subject),
            "facts": [dict(fact) for fact in self.facts],
            "uncertain_facts": [dict(fact) for fact in self.uncertain_facts],
            "paths": [dict(path) for path in self.paths],
            "source_evidence": list(self.source_evidence),
            "missing_evidence": list(self.missing_evidence),
            "candidate_id": self.candidate_id,
            "anchor": self.anchor,
            "resolution_status": self.resolution_status,
            "confidence": self.confidence,
            "generation": self.generation,
        }


def parse_evidence_citations(text: str) -> list[str]:
    import re
    pattern = r"\bE-(?:CODE|CALL|REF|DEP|SHARD|DOC|XLINK|DEFECT)-[0-9a-f]{24}\b"
    return list(dict.fromkeys(re.findall(pattern, text)))
