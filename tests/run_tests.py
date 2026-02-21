#!/usr/bin/env python3
"""
Simple test runner for EMS Learning Platform.
Usage: python run_tests.py [unit|integration|all]
"""

import subprocess
import sys


def run_tests(category="all"):
    """Run tests by category."""
    if category == "unit":
        cmd = ["python", "-m", "pytest", "tests/unit/", "-v"]
    elif category == "integration":
        cmd = ["python", "-m", "pytest", "tests/integration/", "-v"]
    elif category == "e2e":
        cmd = ["python", "-m", "pytest", "tests/e2e/", "-v"]
    else:
        cmd = ["python", "-m", "pytest", "tests/", "-v", "--cov=.", "--cov-report=term-missing"]

    print(f"Running {category} tests...")
    print("=" * 50)
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    category = sys.argv[1] if len(sys.argv) > 1 else "all"
    sys.exit(run_tests(category))
