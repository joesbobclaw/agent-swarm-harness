#!/usr/bin/env python3
"""Operator entry point for the locked Mini bootstrap diagnostic."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MATRIX = "src/gpt54mini-bootstrap-diagnostic.yaml"
CANARY = "src/gpt54mini-bootstrap-diagnostic-canary.yaml"


def run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=REPO)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def doctor() -> None:
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run([sys.executable, "-m", "src.bootstrap_diagnostic_gate", MATRIX,
         "--canary", CANARY])
    print("READY-OFFLINE: no model calls were made")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("doctor", "canary", "matrix"))
    args = parser.parse_args()
    if args.command == "doctor":
        doctor()
        return
    run([sys.executable, "-m", "src.orchestrator",
         CANARY if args.command == "canary" else MATRIX])


if __name__ == "__main__":
    main()
