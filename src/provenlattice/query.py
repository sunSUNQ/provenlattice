from __future__ import annotations

import time
from pathlib import Path

from .storage import SQLiteStorage, decode_row


SYMBOL_KINDS = ("Namespace", "Class", "Struct", "Interface", "Function", "Method", "Type")


class GraphQuery:
    def __init__(self, database: str | Path) -> None:
        self.storage = SQLiteStorage(database)

    def close(self) -> None:
        self.storage.close()

    def __enter__(self) -> "GraphQuery":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def graph_generation(self) -> int:
        repo = self.storage.repository()
        return int(repo["current_generation"]) if repo else 0

    def _result(self, data: object, started: float) -> dict:
        return {
            "graph_generation": self.graph_generation,
            "query_time_ms": (time.perf_counter() - started) * 1000,
            "data": data,
        }

    def find_symbol(self, name: str) -> dict:
        started = time.perf_counter()
        placeholders = ",".join("?" for _ in SYMBOL_KINDS)
        rows = self.storage.rows(
            f"""SELECT * FROM nodes WHERE kind IN ({placeholders})
                AND (name = ? OR qualified_name = ? OR qualified_name LIKE ?)
                ORDER BY qualified_name""",
            (*SYMBOL_KINDS, name, name, f"%.{name}"),
        )
        return self._result([decode_row(row) for row in rows], started)

    def _resolve(self, symbol: str) -> dict | None:
        return self.storage.row(
            """SELECT * FROM nodes WHERE id = ? OR qualified_name = ? OR name = ?
               ORDER BY CASE WHEN id = ? THEN 0 WHEN qualified_name = ? THEN 1 ELSE 2 END LIMIT 1""",
            (symbol, symbol, symbol, symbol, symbol),
        )

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
        rows = self.storage.rows(
            f"""SELECT n.*, e.type AS relation, e.metadata AS edge_metadata
                FROM edges e JOIN nodes n ON n.id = e.{node_column}
                WHERE e.{edge_column} = ? AND e.type = ? ORDER BY n.qualified_name""",
            (anchor["id"], edge_type),
        )
        return self._result([decode_row(row) for row in rows], started)

    def get_callers(self, symbol: str) -> dict:
        return self._neighbors(symbol, "CALLS", True)

    def get_callees(self, symbol: str) -> dict:
        return self._neighbors(symbol, "CALLS", False)

    def get_references(self, symbol: str) -> dict:
        return self._neighbors(symbol, "REFERENCES", True)

    def get_raw_references(
        self,
        *,
        raw_name: str | None = None,
        file_id: str | None = None,
        owner_symbol_id: str | None = None,
        resolved_symbol_id: str | None = None,
        status: str | None = None,
    ) -> dict:
        started = time.perf_counter()
        filters: list[str] = []
        values: list[str] = []
        for column, value in (
            ("raw_name", raw_name), ("file_id", file_id),
            ("owner_symbol_id", owner_symbol_id),
            ("resolved_symbol_id", resolved_symbol_id), ("status", status),
        ):
            if value is not None:
                filters.append(f"{column} = ?")
                values.append(value)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        rows = self.storage.rows(
            f"SELECT * FROM raw_references {where} ORDER BY file_id, start_line, id",
            tuple(values),
        )
        return self._result([decode_row(row) for row in rows], started)

    def _shard(self, shard: str) -> dict | None:
        return self.storage.row(
            "SELECT * FROM shards WHERE shard_id = ? OR path = ? ORDER BY path LIMIT 1",
            (shard, shard),
        )

    def _boundary(self, shard: str, dependents: bool) -> dict:
        started = time.perf_counter()
        anchor = self._shard(shard)
        if not anchor:
            return self._result([], started)
        source, target = ("dst_shard_id", "src_shard_id") if dependents else ("src_shard_id", "dst_shard_id")
        rows = self.storage.rows(
            f"""SELECT DISTINCT s.* FROM shard_edges e
                JOIN shards s ON s.shard_id = e.{target}
                WHERE e.{source} = ? ORDER BY s.path""",
            (anchor["shard_id"],),
        )
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
        rows = self.storage.rows(
            """SELECT r.* FROM raw_references r
               JOIN nodes owner ON owner.id=r.owner_symbol_id
               JOIN nodes target ON target.id=r.resolved_symbol_id
               WHERE r.resolved_symbol_id=? AND owner.shard_id != target.shard_id
               ORDER BY r.file_id, r.start_line, r.id""",
            (anchor["id"],),
        )
        return self._result([decode_row(row) for row in rows], started)

    def get_subgraph(self, anchor: str, max_hops: int = 2, max_nodes: int = 100) -> dict:
        if max_hops < 0 or max_nodes < 1:
            raise ValueError("max_hops must be >= 0 and max_nodes must be >= 1")
        started = time.perf_counter()
        root = self._resolve(anchor)
        if not root:
            return self._result({"nodes": [], "edges": []}, started)
        seen = {root["id"]}
        frontier = {root["id"]}
        selected_edges: dict[str, dict] = {}
        for _ in range(max_hops):
            if not frontier or len(seen) >= max_nodes:
                break
            placeholders = ",".join("?" for _ in frontier)
            values = tuple(sorted(frontier))
            edges = self.storage.rows(
                f"SELECT * FROM edges WHERE src_id IN ({placeholders}) "
                f"OR dst_id IN ({placeholders}) ORDER BY id",
                (*values, *values),
            )
            next_frontier: set[str] = set()
            for edge in edges:
                endpoints = (edge["src_id"], edge["dst_id"])
                if not any(endpoint in frontier for endpoint in endpoints):
                    continue
                for other in endpoints:
                    if other in seen:
                        continue
                    if len(seen) >= max_nodes:
                        break
                    seen.add(other)
                    next_frontier.add(other)
                if edge["src_id"] in seen and edge["dst_id"] in seen:
                    selected_edges[edge["id"]] = decode_row(edge)
            frontier = next_frontier
        placeholders = ",".join("?" for _ in seen)
        nodes = self.storage.rows(f"SELECT * FROM nodes WHERE id IN ({placeholders})", tuple(seen))
        return self._result(
            {"nodes": [decode_row(row) for row in nodes], "edges": list(selected_edges.values())}, started
        )

    def status(self) -> dict:
        started = time.perf_counter()
        repo = self.storage.repository()
        counts = {
            table: self.storage.row(f"SELECT COUNT(*) AS count FROM {table}")["count"]
            for table in ("files", "shards", "nodes", "edges", "raw_references")
        }
        latest = self.storage.row("SELECT * FROM graph_generation ORDER BY generation DESC LIMIT 1")
        return self._result(
            {"repository": decode_row(repo) if repo else None, "counts": counts,
             "latest_generation": decode_row(latest) if latest else None,
             "database_size": self.storage.database_size},
            started,
        )
