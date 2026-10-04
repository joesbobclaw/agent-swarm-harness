#!/usr/bin/env python3
"""Operator entry point for the DeepSeek cross-model replication."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
BASELINE = "src/phase1a-confirmation.yaml"
MATRIX = "src/deepseek-v4-replication.yaml"
CANARY = "src/deepseek-v4-replication-canary.yaml"


def run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=REPO)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def doctor() -> None:
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run([sys.executable, "-m", "src.offline_gate", MATRIX])
    run([
        sys.executable, "-m", "src.cross_model_gate", BASELINE, MATRIX,
        "--canary", CANARY,
    ])
    print("READY-OFFLINE: no model calls were made")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("doctor", "canary", "matrix"))
    args = parser.parse_args()
    if args.command == "doctor":
        doctor()
        return
    config = CANARY if args.command == "canary" else MATRIX
    run([sys.executable, "-m", "src.orchestrator", config])


if __name__ == "__main__":
    main()
