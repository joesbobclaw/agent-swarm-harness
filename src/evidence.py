"""Deterministic manifests, Ed25519 signing, and external-anchor receipts."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

try:
    from .event_store import canonical_json
except ImportError:  # direct execution from src/
    from event_store import canonical_json

VERIFIER_VERSION = "phase1-v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(repo: str | Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
            capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def build_prerun_manifest(run_id: str, condition: dict, model: dict, seed: int,
                          task_instances: list[dict], config_path: str | Path,
                          repo: str | Path) -> dict:
    return {
        "schema": "swarm-study-prerun-manifest-v1",
        "run_id": run_id,
        "condition": condition,
        "model": model,
        "run_seed": seed,
        "task_instances": task_instances,
        "config_sha256": sha256_file(config_path),
        "code_commit": git_commit(repo),
        "ordered_agent_indices": list(range(len(task_instances))),
    }


def write_json(path: str | Path, value: dict) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(value) + "\n"
    path.write_text(payload, encoding="utf-8")
    return sha256_bytes(payload.encode())


def load_private_key(path: str | Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("study signing key must be Ed25519")
    return key


def public_key_pem(private_key: Ed25519PrivateKey) -> str:
    return private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def sign_manifest(manifest: dict, private_key: Ed25519PrivateKey) -> dict:
    payload = canonical_json(manifest).encode()
    return {
        "algorithm": "Ed25519",
        "manifest_sha256": sha256_bytes(payload),
        "signature_base64": base64.b64encode(private_key.sign(payload)).decode(),
        "public_key_pem": public_key_pem(private_key),
    }


def verify_signature(manifest: dict, signature: dict) -> bool:
    try:
        payload = canonical_json(manifest).encode()
        if signature["manifest_sha256"] != sha256_bytes(payload):
            return False
        key = serialization.load_pem_public_key(signature["public_key_pem"].encode())
        if not isinstance(key, Ed25519PublicKey):
            return False
        key.verify(base64.b64decode(signature["signature_base64"]), payload)
        return True
    except (KeyError, ValueError, TypeError):
        return False


def build_completion_manifest(run_result: dict, db_path: str | Path,
                              prerun_manifest_hash: str) -> dict:
    return {
        "schema": "swarm-study-completion-manifest-v1",
        "run_id": run_result["run_id"],
        "prerun_manifest_sha256": prerun_manifest_hash,
        "db_sha256": sha256_file(db_path),
        "final_chain_head": run_result["chain_integrity"].get("head"),
        "total_cost": run_result["total_cost"],
        "total_turns": run_result["total_turns"],
        "agent_count": run_result["metrics"]["total_agents"],
        "verifier_version": VERIFIER_VERSION,
    }


def write_anchor_request(path: str | Path, manifest: dict, signature: dict) -> str:
    """Write the digest that must be externally timestamped before analysis."""
    digest = signature["manifest_sha256"]
    Path(path).write_text(
        "swarm-study-completion-manifest-sha256 " + digest + "\n", encoding="utf-8")
    return digest


def record_anchor_receipt(path: str | Path, manifest_digest: str,
                          anchor_uri: str, anchored_at: str) -> dict:
    """Record a public immutable anchor after the operator publishes the digest."""
    receipt = {"schema": "swarm-study-anchor-receipt-v1",
               "manifest_sha256": manifest_digest,
               "anchor_uri": anchor_uri, "anchored_at": anchored_at}
    write_json(path, receipt)
    return receipt
