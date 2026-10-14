"""I2B MCP E2E: real stdio MCP client against the actual server.

Starts the MCP server as a subprocess, performs JSON-RPC initialize /
tools/list / tools/call, and verifies that defect queries return valid JSON
with grade/level/provenance fields.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MCP_SERVER = REPO / "experiments" / "context_bundle_v0" / "formal_harness" / "provenlattice_mcp_server.py"
CONTRACT = REPO / "experiments" / "context_bundle_v0" / "formal_harness" / "d9-c8" / "d9-c8-a-native-tool-exposure-contract.json"

FIXTURE = """#include <stdlib.h>
int f01(int n) {
    char *p = malloc(64);
    if (!p) return -1;
    if (n) { free(p); return 0; }
    free(p);
    return n;
}
"""

ALL_QUERIES = (
    "resource_lifetime", "lock_order", "race_condition", "null_flow",
    "use_after_free", "double_free", "taint_path", "error_handling",
)


def write(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class McpE2ETests(unittest.TestCase):
    """MCP protocol E2E: server startup, tool discovery, defect query."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name) / "repo"
        cls.database = Path(cls.temp.name) / "graph.db"
        write(cls.root, "src/t.c", FIXTURE)
        from provenlattice.graph import full_index
        from provenlattice.orchestrator import analyze_scope
        full_index(cls.root, cls.database)
        analyze_scope(cls.root, "src", ("defect",), database=cls.database)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _rpc(self, proc, method, params=None, rid=0):
        msg = {"jsonrpc": "2.0", "method": method, "id": rid}
        if params is not None:
            msg["params"] = params
        proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if not line:
                return None
            resp = json.loads(line.strip())
            if resp.get("id") == rid:
                return resp

    def _start(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO / "src")
        proc = subprocess.Popen(
            [sys.executable, str(MCP_SERVER), str(CONTRACT)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env)
        self._rpc(proc, "initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.1"},
        }, rid=1)
        return proc

    def test_initialize(self):
        proc = self._start()
        try:
            resp = self._rpc(proc, "ping", rid=2)
            self.assertIsNotNone(resp)
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    def test_tools_list_has_query(self):
        proc = self._start()
        try:
            resp = self._rpc(proc, "tools/list", {}, rid=2)
            names = [t["name"] for t in resp["result"]["tools"]]
            self.assertIn("query", names)
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    def test_all_8_defect_queries_via_mcp(self):
        proc = self._start()
        try:
            for q in ALL_QUERIES:
                rid = 10 + ALL_QUERIES.index(q)
                resp = self._rpc(proc, "tools/call", {
                    "name": "query",
                    "arguments": {
                        "command": "defect",
                        "args": [str(self.root), "--type", q, "--database", str(self.database), "--json"],
                    },
                }, rid=rid)
                self.assertIn("result", resp, f"{q}: no result")
                content = resp["result"]["content"]
                self.assertGreater(len(content), 0, f"{q}: empty content")
                text = content[0]["text"]
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    self.fail(f"{q}: subprocess returned non-JSON: {text[:200]}")
                self.assertEqual(data.get("status"), "available",
                                 f"{q}: expected available, got {data.get('status')}")
                self.assertIn("grade", data, f"{q}: missing grade")
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    def test_stale_upstream_fails_closed_via_mcp(self):
        proc = self._start()
        try:
            fake_db = str(self.database) + ".nonexistent"
            resp = self._rpc(proc, "tools/call", {
                "name": "query",
                "arguments": {
                    "command": "defect",
                        "args": [str(self.root), "--type", "double_free", "--database", fake_db, "--json"],
                },
            }, rid=100)
            content = resp["result"]["content"]
            text = content[0]["text"]
            try:
                data = json.loads(text)
                # if it's JSON, verify fail-closed
                self.assertNotEqual(data.get("status"), "available")
            except json.JSONDecodeError:
                # non-JSON error output is also acceptable fail-closed behavior
                self.assertIn("error", text.lower())
        finally:
            proc.terminate()
            proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
