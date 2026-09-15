"""Frozen R2.4-R1 nine-cell online qualification (no policy search)."""
from __future__ import annotations
import argparse, hashlib, importlib, json
from pathlib import Path

adapter_module = importlib.import_module("experiments.retrieval-v1.harness.agent_adapter")
models = importlib.import_module("experiments.retrieval-v1.harness.models")
runner = importlib.import_module("experiments.retrieval-v1.harness.runner")
evaluator = importlib.import_module("experiments.retrieval-v2.evaluator-v2.evaluator")

ROOT = Path(__file__).parent
GT_PATH = ROOT.parent / "evaluator-v2/ground-truth-v2/ground-truth-v2.json"
TASKS = ("T01", "T03", "T05")
POLICY = {
 "T01": ("document_to_code", ("c_murmurhash_bl", "boundedload", "consistenthashingboundedloadbalancer")),
 "T03": ("code_to_document", ("replicas", "virtual nodes", "addserversinbatch")),
 "T05": ("module_understanding", ("ratelimitedbackuppolicyoptions", "backup request", "backup")),
}
LOOSE = {"PL_R2_4_MAX_PRIMARY":"8", "PL_R2_4_MAX_SUPPORTING":"12", "PL_R2_4_MAX_TOTAL":"24"}

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def task_map(): return {x: models.TaskDefinition.load(ROOT.parent / "r2_1/tasks" / f"{x}.json") for x in TASKS}
def gt(): return {x["task_id"]:x for x in json.loads(GT_PATH.read_text(encoding="utf-8"))["tasks"]}

def bundle_manifest(path: Path) -> dict:
    values=[json.loads(x) for x in (path/"events.ndjson").read_text(encoding="utf-8").splitlines() if x]
    bundles=[]
    for event in values:
        bundle=event.get("bundle")
        if not bundle: continue
        bundles.append({"query_id":event.get("query_id"), "query_type":event.get("query_type"),
          "bundle_profile":bundle.get("profile"), "focus_terms": [], "budget":bundle.get("budget"),
          "primary_evidence_ids":[x["evidence_id"] for x in bundle.get("primary_evidence",[])],
          "supporting_evidence_ids":[x["evidence_id"] for x in bundle.get("supporting_evidence",[])],
          "contextual_evidence_ids":[x["evidence_id"] for x in bundle.get("supporting_evidence",[]) if x.get("metadata",{}).get("bundle_role")=="CONTEXTUAL"],
          "suppressed_evidence_ids":bundle.get("suppressed_evidence_ids",[]), "bundle_size":event.get("bundle_size")})
    return {"bundles":bundles}

def main():
 p=argparse.ArgumentParser(); p.add_argument("--repo",required=True,type=Path); p.add_argument("--codegraph-database",required=True); p.add_argument("--knowledge-database",required=True); p.add_argument("--agent-command",default="claude -p --verbose --output-format stream-json"); p.add_argument("--model-id",default="deepseek-v4-flash"); p.add_argument("--claude-version",required=True); p.add_argument("--provenlattice-commit",required=True); p.add_argument("--results",type=Path,default=ROOT/"agent-results"); p.add_argument("--timeout",type=float,default=900); p.add_argument("--resume",action="store_true"); a=p.parse_args(); a.results.mkdir(parents=True,exist_ok=True)
 adapter=adapter_module.CommandAgentAdapter(a.agent_command); tasks=task_map(); truth=gt(); cells=[]
 for task_id in TASKS:
  profile,focus=POLICY[task_id]
  for arm in ("native","codegraph","knowledge"):
   path=a.results/task_id/arm/"r1"
   if path.exists() and not a.resume: raise FileExistsError(path)
   database=None if arm=="native" else a.codegraph_database if arm=="codegraph" else a.knowledge_database
   env={} if arm=="native" else {**LOOSE,"PL_R2_4_BUNDLE_PROFILE":profile,"PL_R2_4_FOCUS_TERMS":"\x1f".join(focus),"PL_R2_4_POLICY":"Loose"}
   out=runner.run_task(tasks[task_id],arm,a.repo,a.results,adapter,a.timeout,repetition=1,model_id=a.model_id,claude_version=a.claude_version,provenlattice_commit=a.provenlattice_commit,database=database,protocol="r2",environment_overrides=env)
   path=Path(out["run_dir"]); events=[json.loads(x) for x in (path/"events.ndjson").read_text(encoding="utf-8").splitlines() if x]
   ev=evaluator.evaluate_v2(truth[task_id],(path/"agent-output.txt").read_text(encoding="utf-8"),events,repo_root=a.repo,known_evidence_ids={"E-CODE-C2F8A2E93CB05E73B643FBBE","E-CODE-4374CC9A74236B67C11F3479"})
   (path/"evaluation-v2.json").write_text(json.dumps(ev,indent=2,ensure_ascii=False),encoding="utf-8")
   if arm!="native": (path/"bundle-manifest.json").write_text(json.dumps(bundle_manifest(path),indent=2,ensure_ascii=False),encoding="utf-8")
   run=json.loads((path/"run.json").read_text(encoding="utf-8")); run.update({"protocol_revision":"r2.4-r1","ground_truth_v2_hash":digest(GT_PATH),"evaluator_v2_version":"r2.2-groundtruth-v2","bundle_policy":"Loose" if arm!="native" else None}); (path/"run.json").write_text(json.dumps(run,indent=2,ensure_ascii=False),encoding="utf-8")
   cells.append({"run_key":run["run_key"],"status":run["status"],"task_success":ev["task_success"],"concept_recall":ev["concept_recall"]}); print(json.dumps(cells[-1]),flush=True)
 (a.results/"qualification.json").write_text(json.dumps({"protocol":"r2.4-r1","agent_runs":9,"policy":"Loose","cells":cells},indent=2),encoding="utf-8")

if __name__=="__main__": main()
