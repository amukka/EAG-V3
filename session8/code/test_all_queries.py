#!/usr/bin/env python3
"""
Test script for Session 8 DAG agent - all 5 base queries.

Run individually with:
    python test_all_queries.py --query 1
    python test_all_queries.py --query 2
    python test_all_queries.py --query 3
    python test_all_queries.py --query 4
    python test_all_queries.py --query 5

Or run all:
    python test_all_queries.py --all
"""

import subprocess
import sys
import time
from pathlib import Path

# The 5 base queries from the assignment
QUERIES = {
    1: "hello",
    2: "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory.",
    3: "Tell me the current population of New York, Tokyo, and London",
    4: "Read /nonexistent/path.txt and tell me what's in it.",
    5: "For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest"
}

DESCRIPTIONS = {
    1: "Simple greeting (formatter only)",
    2: "Web fetch + structure extraction (researcher + distiller)",
    3: "Parallel data lookup (3x researcher)",
    4: "Graceful failure (nonexistent file)",
    5: "Parallel fetch + computation (3x researcher + coder + sandbox)"
}


def run_query(query_num: int):
    """Run a single query via flow.py."""
    if query_num not in QUERIES:
        print(f"❌ Invalid query number: {query_num}. Valid: 1-5")
        return False

    query = QUERIES[query_num]
    desc = DESCRIPTIONS[query_num]

    print("\n" + "="*80)
    print(f"QUERY {query_num}: {desc}")
    print("="*80)
    print(f"Query text: {query[:100]}{'...' if len(query) > 100 else ''}")
    print(f"Starting at: {time.strftime('%H:%M:%S')}")
    print("-"*80)

    try:
        result = subprocess.run(
            ["python", "flow.py", query],
            cwd=Path(__file__).parent,
            timeout=180  # 3 minute timeout per query
        )

        if result.returncode == 0:
            print("\n✅ Query completed successfully")
            return True
        else:
            print(f"\n❌ Query failed with exit code {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        print(f"\n❌ Query timed out after 180 seconds")
        return False
    except Exception as e:
        print(f"\n❌ Error running query: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test Session 8 DAG agent queries")
    parser.add_argument(
        "--query",
        type=int,
        choices=[1, 2, 3, 4, 5],
        help="Run a specific query (1-5)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all 5 queries sequentially"
    )

    args = parser.parse_args()

    if args.query:
        # Run single query
        success = run_query(args.query)
        sys.exit(0 if success else 1)

    elif args.all:
        # Run all queries
        results = {}
        for query_num in [1, 2, 3, 4, 5]:
            success = run_query(query_num)
            results[query_num] = success
            time.sleep(2)  # Brief pause between queries

        # Summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        for query_num in [1, 2, 3, 4, 5]:
            status = "✅ PASS" if results[query_num] else "❌ FAIL"
            print(f"Query {query_num}: {status} — {DESCRIPTIONS[query_num]}")

        total = sum(1 for v in results.values() if v)
        print(f"\nTotal: {total}/5 passed")
        sys.exit(0 if total == 5 else 1)

    else:
        # Show help
        parser.print_help()
        print("\nQueries:")
        for num, query in QUERIES.items():
            print(f"\n  Query {num}: {DESCRIPTIONS[num]}")
            print(f"    {query[:70]}{'...' if len(query) > 70 else ''}")


if __name__ == "__main__":
    main()
