#!/usr/bin/env python3
"""
Session 8 Assignment Test Runner
Validates all 5 base queries + designer's choice queries with metrics logging
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Five BASE QUERIES (mandatory)
BASE_QUERIES = {
    "hello": {
        "query": "hello",
        "description": "Simple greeting",
        "expected_nodes": ["planner", "formatter"],
        "expected_wall_clock_max": 90,
    },
    "A": {
        "query": "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory.",
        "description": "Web fetch + structure extraction",
        "expected_nodes": ["planner", "researcher", "distiller", "formatter"],
        "expected_wall_clock_max": 180,
    },
    "I": {
        "query": "Tell me the current population of New York, Tokyo, and London",
        "description": "Parallel data lookup (3 cities)",
        "expected_nodes": ["planner", "researcher", "researcher", "researcher", "formatter"],
        "expected_parallel_branches": 3,
        "expected_wall_clock_max": 180,
    },
    "J": {
        "query": "Read /nonexistent/path.txt and tell me what's in it.",
        "description": "Graceful failure handling",
        "expected_nodes": ["planner", "formatter"],
        "expected_wall_clock_max": 90,
    },
    "K": {
        "query": "For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest",
        "description": "Parallel fetch + computation",
        "expected_nodes": ["planner", "researcher", "researcher", "researcher", "coder", "sandbox_executor", "formatter"],
        "expected_parallel_branches": 3,
        "expected_wall_clock_max": 300,
    },
}

# DESIGNER'S CHOICE QUERIES
DESIGNER_QUERIES = {
    "parallel_fan_out": {
        "query": "Find the founding year, current age, and net worth of Elon Musk, Bill Gates, and Steve Ballmer. Which one was youngest when their company was founded?",
        "description": "Parallel fan-out with computation (3 independent researchers + coder)",
        "requires": ["parallel_execution", "computation"],
    },
    "critic_test": {
        "query": "Write a haiku about climate change. The haiku must have exactly 5 syllables in line 1, 7 in line 2, and 5 in line 3.",
        "description": "Critic verdict with format validation",
        "requires": ["critic_verdict"],
    },
}


class TestRunner:
    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or Path("test_results")
        self.output_dir.mkdir(exist_ok=True)
        self.code_dir = Path(__file__).parent
        self.results = {}
        self.start_time = datetime.now()

    def analyze_graph(self, session_id: str) -> dict:
        """Analyze the graph.json to extract execution metrics."""
        graph_file = self.code_dir / "state" / "sessions" / session_id / "graph.json"

        if not graph_file.exists():
            return {"error": "graph not found"}

        try:
            with open(graph_file) as f:
                graph_data = json.load(f)

            nodes = graph_data.get("nodes", [])
            skills = [n.get("skill") for n in nodes]

            # Calculate wall-clock from node execution times
            max_time = 0
            for i, node_file in enumerate(sorted(self.code_dir.glob(f"state/sessions/{session_id}/nodes/n_*.json"))):
                try:
                    with open(node_file) as f:
                        node_data = json.load(f)
                        elapsed = node_data.get("result", {}).get("elapsed_s", 0)
                        if elapsed > max_time:
                            max_time = elapsed
                except:
                    pass

            return {
                "skill_sequence": skills,
                "node_count": len(nodes),
                "parallel_nodes": len([s for s in skills if skills.count(s) > 1]),
                "wall_clock_estimate": max_time,
            }
        except Exception as e:
            return {"error": str(e)}

    def run_query(self, query_key: str, query_text: str, query_info: dict) -> dict:
        """Run a single query and capture metrics."""
        print(f"\n{'='*80}")
        print(f"QUERY: {query_key} - {query_info['description']}")
        print(f"{'='*80}")
        print(f"Text: {query_text[:100]}{'...' if len(query_text) > 100 else ''}")
        print(f"Start: {datetime.now().strftime('%H:%M:%S')}")

        start = time.time()

        try:
            result = subprocess.run(
                ["python", "flow.py", query_text],
                cwd=self.code_dir,
                timeout=query_info.get("expected_wall_clock_max", 120),
                capture_output=False,
            )

            elapsed = time.time() - start
            success = result.returncode == 0

            # Extract session ID from most recent state/sessions directory
            sessions_dir = self.code_dir / "state" / "sessions"
            session_id = None
            if sessions_dir.exists():
                recent = sorted(sessions_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
                if recent:
                    session_id = recent[0].name

            graph_info = {}
            if session_id:
                graph_info = self.analyze_graph(session_id)

            result_data = {
                "query_key": query_key,
                "success": success,
                "elapsed_seconds": elapsed,
                "session_id": session_id,
                "graph_info": graph_info,
                "timestamp": datetime.now().isoformat(),
            }

            status = "✅ PASS" if success else "❌ FAIL"
            print(f"\n{status} - {elapsed:.1f}s wall-clock")

            if session_id:
                print(f"Session: {session_id}")

            return result_data

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            print(f"\n❌ TIMEOUT - exceeded {query_info.get('expected_wall_clock_max')}s limit")
            return {
                "query_key": query_key,
                "success": False,
                "elapsed_seconds": elapsed,
                "error": "timeout",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            elapsed = time.time() - start
            print(f"\n❌ ERROR: {e}")
            return {
                "query_key": query_key,
                "success": False,
                "elapsed_seconds": elapsed,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def validate_base_queries(self):
        """Run all 5 base queries."""
        print("\n" + "="*80)
        print("RUNNING: 5 BASE QUERIES")
        print("="*80)

        for key in ["hello", "A", "I", "J", "K"]:
            info = BASE_QUERIES[key]
            result = self.run_query(key, info["query"], info)
            self.results[f"base_{key}"] = result

    def validate_designer_queries(self):
        """Run designer's choice queries."""
        print("\n" + "="*80)
        print("RUNNING: DESIGNER'S CHOICE QUERIES")
        print("="*80)

        for key, info in DESIGNER_QUERIES.items():
            print(f"\n[INFO] {key}: Requires {', '.join(info['requires'])}")
            result = self.run_query(key, info["query"], info)
            self.results[f"designer_{key}"] = result

    def generate_report(self):
        """Generate summary report."""
        report = {
            "test_suite": "Session 8 DAG Agent Assignment",
            "run_date": datetime.now().isoformat(),
            "duration_seconds": (datetime.now() - self.start_time).total_seconds(),
            "results": self.results,
            "summary": {
                "total_queries": len(self.results),
                "passed": sum(1 for r in self.results.values() if r.get("success")),
                "failed": sum(1 for r in self.results.values() if not r.get("success")),
            }
        }

        # Write JSON report
        report_file = self.output_dir / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        print("\n" + "="*80)
        print("FINAL REPORT")
        print("="*80)
        print(f"Total queries: {report['summary']['total_queries']}")
        print(f"Passed: {report['summary']['passed']}")
        print(f"Failed: {report['summary']['failed']}")
        print(f"Duration: {report['duration_seconds']:.1f}s")
        print(f"Report: {report_file}")

        return report


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Session 8 Assignment Test Runner")
    parser.add_argument("--base-only", action="store_true", help="Run only 5 base queries")
    parser.add_argument("--designer-only", action="store_true", help="Run only designer's choice queries")
    parser.add_argument("--query", help="Run single query by key (hello, A, I, J, K, parallel_fan_out, critic_test)")

    args = parser.parse_args()

    runner = TestRunner()

    if args.query:
        # Single query
        if args.query in BASE_QUERIES:
            info = BASE_QUERIES[args.query]
            runner.run_query(args.query, info["query"], info)
        elif args.query in DESIGNER_QUERIES:
            info = DESIGNER_QUERIES[args.query]
            runner.run_query(args.query, info["query"], info)
        else:
            print(f"Unknown query: {args.query}")
            sys.exit(1)
    else:
        # Full suite
        if not args.designer_only:
            runner.validate_base_queries()

        if not args.base_only:
            runner.validate_designer_queries()

    runner.generate_report()


if __name__ == "__main__":
    main()



# cd /Users/srinivasmukka/SchoolOfAI/DAG/session8/code

# # Run one query at a time
# uv run python run_assignment_tests.py --query hello
# uv run python run_assignment_tests.py --query A
# uv run python run_assignment_tests.py --query I
# uv run python run_assignment_tests.py --query J
# uv run python run_assignment_tests.py --query K

# # Or all 5 at once
# uv run python run_assignment_tests.py --base-only

# # Designer's choice
# uv run python run_assignment_tests.py --query parallel_fan_out
# uv run python run_assignment_tests.py --query critic_test
