from __future__ import annotations

import argparse
import json
from pathlib import Path

from .harness.agent_adapter import CommandAgentAdapter
from .harness.models import ARM_TOOLS, TaskDefinition
from .harness.runner import run_task


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fixed R1 task matrix")
    parser.add_argument("--tasks", type=Path, default=Path("experiments/retrieval-v1/tasks"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--agent-command", required=True)
    parser.add_argument("--results", type=Path, default=Path("experiments/retrieval-v1/results"))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--skip-commit-check", action="store_true")
    args = parser.parse_args()
    if args.repetitions < 1:
        raise ValueError("repetitions must be >= 1")
    adapter = CommandAgentAdapter(args.agent_command)
    results = []
    for repetition in range(1, args.repetitions + 1):
        for task_path in sorted(args.tasks.glob("T*.json")):
            task = TaskDefinition.load(task_path)
            for arm in ARM_TOOLS:
                # Runner V1 stores the first qualification pass under r1. Later
                # repetitions are intentionally separate directories.
                root = args.results if repetition == 1 else args.results.parent / f"{args.results.name}-r{repetition}"
                results.append(run_task(task, arm, args.repo, root, adapter, args.timeout,
                                        verify_commit=not args.skip_commit_check))
    print(json.dumps({"runs": len(results), "repetitions": args.repetitions}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
