from __future__ import annotations

import time
from pathlib import Path

from .overlay import GraphView
from .storage import decode_row


SYMBOL_KINDS = ("Namespace", "Class", "Struct", "Interface", "Function", "Method", "Type")


class GraphQuery:
    def __init__(
        self, database: str | Path, *, branch_overlay: str | Path | None = None,
        session_overlay: str | Path | None = None, current_base_commit: str | None = None,
    ) -> None:
        self.view = GraphView(
            database, branch_overlay, session_overlay,
            current_base_commit=current_base_commit,
        )
        self.storage = self.view.base

    def close(self) -> None:
        self.view.close()

    def __enter__(self) -> "GraphQuery":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def graph_generation(self) -> int:
        return self.view.graph_generation

    def _result(self, data: object, started: float) -> dict:
        return {"graph_generation": self.graph_generation,
                "query_time_ms": (time.perf_counter() - started) * 1000, "data": data}

    def find_symbol(self, name: str) -> dict:
        started = time.perf_counter()
        placeholders = ",".join("?" for _ in SYMBOL_KINDS)

        def matches(row: dict) -> bool:
            qualified = row.get("qualified_name", "")
            return row.get("kind") in SYMBOL_KINDS and (
                row.get("name") == name or qualified == name or qualified.endswith(f".{name}")
            )

        rows = self.view.query(
            "Node",
            f"SELECT * FROM nodes WHERE kind IN ({placeholders}) "
            "AND (name=? OR qualified_name=? OR qualified_name LIKE ?)",
            (*SYMBOL_KINDS, name, name, f"%.{name}"), matches,
        )
        rows.sort(key=lambda item: (item["qualified_name"], item["id"]))
        return self._result([decode_row(row) for row in rows], started)

    def _resolve(self, symbol: str) -> dict | None:
        matches = lambda row: (
            row.get("id") == symbol or row.get("qualified_name") == symbol
            or row.get("name") == symbol
        )
        rows = self.view.query(
            "Node", "SELECT * FROM nodes WHERE id=? OR qualified_name=? OR name=?",
            (symbol, symbol, symbol), matches,
        )
        if not rows:
            return None
        return min(rows, key=lambda row: (
            0 if row["id"] == symbol else 1 if row["qualified_name"] == symbol else 2,
            row["qualified_name"], row["id"],
        ))

    def get_definition(self, symbol: str) -> dict:
        started = time.perf_counter()
        row = self._resolve(symbol)
        return self._result(decode_row(row) if row else None, started)

    def _neighbors(self, symbol: str, edge_type: str, incoming: bool) -> dict:
        started = time.perf_counter()
        anchor = self._resolve(symbol)
        if not anchor:
            return self._result([], started)
        edge_column, node_column = ("dst_id", "src_id") if incoming else ("src_id", "dst_id")
        edges = self.view.query(
            "Edge", f"SELECT * FROM edges WHERE {edge_column}=? AND type=?",
            (anchor["id"], edge_type),
            lambda row: row.get(edge_column) == anchor["id"] and row.get("type") == edge_type,
        )
        nodes = {row["id"]: row for row in self.view.by_ids(
            "Node", (edge[node_column] for edge in edges)
        )}
        result = []
        for edge in edges:
            node = nodes.get(edge[node_column])
            if node is None:
                continue
            item = dict(node)
            item["relation"], item["edge_metadata"] = edge["type"], edge["metadata"]
            result.append(decode_row(item))
        result.sort(key=lambda item: (item["qualified_name"], item["id"]))
        return self._result(result, started)

    def get_callers(self, symbol: str) -> dict:
        return self._neighbors(symbol, "CALLS", True)

    def get_callees(self, symbol: str) -> dict:
        return self._neighbors(symbol, "CALLS", False)

    def get_references(self, symbol: str) -> dict:
        return self._neighbors(symbol, "REFERENCES", True)

    def get_raw_references(
        self, *, raw_name: str | None = None, file_id: str | None = None,
        owner_symbol_id: str | None = None, resolved_symbol_id: str | None = None,
        status: str | None = None,
    ) -> dict:
        started = time.perf_counter()
        filters = {"raw_name": raw_name, "file_id": file_id,
                   "owner_symbol_id": owner_symbol_id,
                   "resolved_symbol_id": resolved_symbol_id, "status": status}
        active = {key: value for key, value in filters.items() if value is not None}
        where = " AND ".join(f"{key}=?" for key in active)
        sql = "SELECT * FROM raw_references" + (f" WHERE {where}" if where else "")
        rows = self.view.query(
            "RawReference", sql, tuple(active.values()),
            lambda row: all(row.get(key) == value for key, value in active.items()),
        )
        rows.sort(key=lambda row: (row["file_id"], row.get("start_line") or 0, row["id"]))
        return self._result([decode_row(row) for row in rows], started)

    def get_evidence_links(
        self, *, source_node_id: str | None = None,
        resolved_target_id: str | None = None, status: str | None = None,
        anchor_type: str | None = None,
    ) -> dict:
        started = time.perf_counter()
        filters = {"source_node_id": source_node_id, "resolved_target_id": resolved_target_id,
                   "resolution_status": status, "anchor_type": anchor_type}
        active = {key: value for key, value in filters.items() if value is not None}
        where = " AND ".join(f"{key}=?" for key in active)
        sql = "SELECT * FROM raw_evidence_links" + (f" WHERE {where}" if where else "")
        rows = self.view.query(
            "RawEvidenceLink", sql, tuple(active.values()),
            lambda row: all(row.get(key) == value for key, value in active.items()),
        )
        rows.sort(key=lambda row: (row["source_node_id"], row["raw_anchor"], row["id"]))
        return self._result([decode_row(row) for row in rows], started)

    def _cross_layer_neighbors(self, anchor: str, relations: set[str], incoming: bool) -> dict:
        started = time.perf_counter()
        node = self._resolve(anchor)
        if not node:
            return self._result([], started)
        edge_column, node_column = (("dst_id", "src_id") if incoming
                                    else ("src_id", "dst_id"))
        edges = self.view.query(
            "Edge", f"SELECT * FROM edges WHERE {edge_column}=?",
            (node["id"],),
            lambda row: row.get(edge_column) == node["id"] and row.get("type") in relations,
        )
        targets = {row["id"]: row for row in self.view.by_ids(
            "Node", (edge[node_column] for edge in edges)
        )}
        result = []
        for edge in edges:
            target = targets.get(edge[node_column])
            if target:
                item = decode_row(target)
                item["relation"] = edge["type"]
                item["edge_metadata"] = decode_row(edge).get("metadata", {})
                result.append(item)
        result.sort(key=lambda item: (item["qualified_name"], item["id"]))
        return self._result(result, started)

    def get_implemented_code(self, requirement: str) -> dict:
        return self._cross_layer_neighbors(requirement, {"IMPLEMENTED_BY"}, False)

    def get_requirements(self, symbol: str) -> dict:
        result = self._cross_layer_neighbors(symbol, {"IMPLEMENTED_BY"}, True)
        result["data"] = [item for item in result["data"] if item.get("kind") == "Requirement"]
        return result

    def get_document_targets(self, document: str) -> dict:
        return self._cross_layer_neighbors(
            document, {"DESCRIBES", "CONSTRAINS", "IMPLEMENTED_BY", "VERIFIED_BY",
                       "BELONGS_TO", "DOCUMENTS"}, False,
        )

    def _shard(self, shard: str) -> dict | None:
        rows = self.view.query(
            "Shard", "SELECT * FROM shards WHERE shard_id=? OR path=?", (shard, shard),
            lambda row: row.get("shard_id") == shard or row.get("path") == shard,
        )
        return min(rows, key=lambda row: (row["path"], row["shard_id"])) if rows else None

    def _boundary(self, shard: str, dependents: bool) -> dict:
        started = time.perf_counter()
        anchor = self._shard(shard)
        if not anchor:
            return self._result([], started)
        source, target = (("dst_shard_id", "src_shard_id") if dependents
                          else ("src_shard_id", "dst_shard_id"))
        edges = self.view.query(
            "BoundaryEdge", f"SELECT * FROM shard_edges WHERE {source}=?",
            (anchor["shard_id"],), lambda row: row.get(source) == anchor["shard_id"],
        )
        rows = self.view.by_ids("Shard", {edge[target] for edge in edges})
        rows.sort(key=lambda item: (item["path"], item["shard_id"]))
        return self._result([decode_row(row) for row in rows], started)

    def get_dependencies(self, shard: str) -> dict:
        return self._boundary(shard, False)

    def get_dependents(self, shard: str) -> dict:
        return self._boundary(shard, True)

    def get_boundary_references(self, symbol: str) -> dict:
        started = time.perf_counter()
        anchor = self._resolve(symbol)
        if not anchor:
            return self._result([], started)
        references = self.view.query(
            "RawReference", "SELECT * FROM raw_references WHERE resolved_symbol_id=?",
            (anchor["id"],), lambda row: row.get("resolved_symbol_id") == anchor["id"],
        )
        node_ids = {value for reference in references for value in (
            reference.get("owner_symbol_id"), reference.get("resolved_symbol_id")) if value}
        nodes = {row["id"]: row for row in self.view.by_ids("Node", node_ids)}
        rows = [reference for reference in references
                if nodes.get(reference["owner_symbol_id"], {}).get("shard_id")
                != nodes.get(reference["resolved_symbol_id"], {}).get("shard_id")]
        rows.sort(key=lambda row: (row["file_id"], row.get("start_line") or 0, row["id"]))
        return self._result([decode_row(row) for row in rows], started)

    def get_subgraph(self, anchor: str, max_hops: int = 2, max_nodes: int = 100) -> dict:
        if max_hops < 0 or max_nodes < 1:
            raise ValueError("max_hops must be >= 0 and max_nodes must be >= 1")
        started = time.perf_counter()
        root = self._resolve(anchor)
        if not root:
            return self._result({"nodes": [], "edges": []}, started)
        seen, frontier = {root["id"]}, {root["id"]}
        selected: dict[str, dict] = {}
        for _ in range(max_hops):
            if not frontier or len(seen) >= max_nodes:
                break
            placeholders = ",".join("?" for _ in frontier)
            values = tuple(sorted(frontier))
            edges = self.view.query(
                "Edge", f"SELECT * FROM edges WHERE src_id IN ({placeholders}) "
                f"OR dst_id IN ({placeholders})", (*values, *values),
                lambda row: row.get("src_id") in frontier or row.get("dst_id") in frontier,
            )
            next_frontier: set[str] = set()
            for edge in sorted(edges, key=lambda row: row["id"]):
                for other in (edge["src_id"], edge["dst_id"]):
                    if other not in seen and len(seen) < max_nodes:
                        seen.add(other)
                        next_frontier.add(other)
                if edge["src_id"] in seen and edge["dst_id"] in seen:
                    selected[edge["id"]] = decode_row(edge)
            frontier = next_frontier
        nodes = self.view.by_ids("Node", seen)
        return self._result({"nodes": [decode_row(row) for row in nodes],
                             "edges": list(selected.values())}, started)

    def status(self) -> dict:
        started = time.perf_counter()
        repository = self.storage.repository()
        counts = {"files": self.storage.row("SELECT COUNT(*) AS count FROM files")["count"],
                  "shards": len(self.view.all("Shard")), "nodes": len(self.view.all("Node")),
                  "edges": len(self.view.all("Edge")),
                  "raw_references": len(self.view.all("RawReference")),
                  "raw_evidence_links": len(self.view.all("RawEvidenceLink"))}
        latest = self.storage.row("SELECT * FROM graph_generation ORDER BY generation DESC LIMIT 1")
        return self._result({"repository": decode_row(repository) if repository else None,
                             "counts": counts,
                             "latest_generation": decode_row(latest) if latest else None,
                             "database_size": self.storage.database_size,
                             "overlay_size": sum(item.database_size for item in self.view.layers)}, started)
