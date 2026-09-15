#!/usr/bin/env python3
"""Record a receipt after a completion-manifest digest is publicly anchored."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .evidence import record_anchor_receipt
except ImportError:
    from evidence import record_anchor_receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", help="completion manifest JSON")
    parser.add_argument("anchor_uri", help="public immutable timestamp/anchor URI")
    parser.add_argument("anchored_at", help="timestamp reported by the anchor")
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    signature_path = manifest_path.with_suffix(".signature.json")
    signature = json.loads(signature_path.read_text())
    receipt_path = manifest_path.with_suffix(".anchor-receipt.json")
    record_anchor_receipt(receipt_path, signature["manifest_sha256"],
                          args.anchor_uri, args.anchored_at)
    print(receipt_path)


if __name__ == "__main__":
    main()
