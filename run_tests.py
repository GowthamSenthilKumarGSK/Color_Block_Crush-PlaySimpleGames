#!/usr/bin/env python3
"""Automated test runner: runs all solvers on all test levels and validates."""
import subprocess
import sys
import time
import os

TESTS = [
    ("tests/test1.txt", "Starter"),
    ("tests/test2.txt", "Medium"),
    ("tests/test3.txt", "Walls"),
    ("tests/test4.txt", "Ice + directional"),
    ("tests/test5.txt", "Ice only"),
]

SOLVERS = ["complete", "fast", "optional"]

TIME_LIMIT = 65


def run_test(level_path, solver):
    """Run a solver on a level and validate the output."""
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, "solve.py", level_path, "--solver", solver],
            capture_output=True, text=True, timeout=TIME_LIMIT
        )
        elapsed = time.time() - start
        stdout = result.stdout.strip()
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT (process)", "moves": 0, "time": TIME_LIMIT,
                "valid": False, "error": "Process exceeded 65s"}

    lines = stdout.split("\n")
    status = lines[0].replace("STATUS: ", "") if lines else "UNKNOWN"
    moves = 0
    if len(lines) > 1:
        try:
            moves = int(lines[1].replace("MOVES: ", ""))
        except ValueError:
            pass

    if status != "SOLVED":
        return {"status": status, "moves": moves, "time": elapsed,
                "valid": False, "error": f"Status: {status}"}

    # Validate with validator.py
    val_result = subprocess.run(
        [sys.executable, "validator.py", level_path],
        input=stdout, capture_output=True, text=True
    )
    val_out = val_result.stdout.strip()
    valid = val_out.startswith("Valid solution")

    return {"status": status, "moves": moves, "time": elapsed,
            "valid": valid, "error": None if valid else val_out}


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    passed = 0
    failed = 0
    total = 0

    for solver in SOLVERS:
        print(f"\n{'='*60}")
        print(f"  Solver: {solver}")
        print(f"{'='*60}")

        for level_path, desc in TESTS:
            if solver == "optional" and not os.path.exists("solver_optional.py"):
                continue

            total += 1
            r = run_test(level_path, solver)
            icon = "PASS" if r["valid"] else "FAIL"
            print(f"  [{icon}] {desc:25s} | {r['time']:5.1f}s | "
                  f"{r['moves']:4d} moves | {r['status']}")

            if r["valid"]:
                passed += 1
            else:
                failed += 1
                print(f"         Error: {r['error']}")

            if r["time"] > 60:
                print(f"         WARNING: exceeded 60s time limit")

    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print(f"{'='*60}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
