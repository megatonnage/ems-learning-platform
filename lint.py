#!/usr/bin/env python3
"""
Linting script for EMS Learning Platform.
Usage: python lint.py [check|fix]
"""

import subprocess
import sys


def run_command(cmd, description):
    """Run a command and print status."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print("=" * 60)
    result = subprocess.run(cmd, shell=True)
    return result.returncode


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"

    if mode == "fix":
        # Fix mode: auto-fix issues
        commands = [
            ("ruff check . --fix", "Ruff (auto-fix issues)"),
            ("black .", "Black (format code)"),
        ]
    else:
        # Check mode: report only
        commands = [
            ("ruff check .", "Ruff (check for issues)"),
            ("black --check .", "Black (check formatting)"),
        ]

    exit_codes = []
    for cmd, desc in commands:
        exit_codes.append(run_command(cmd, desc))

    print(f"\n{'='*60}")
    if all(code == 0 for code in exit_codes):
        print("✅ All checks passed!")
        return 0
    else:
        print("❌ Some checks failed.")
        if mode == "check":
            print("   Run 'python lint.py fix' to auto-fix issues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
