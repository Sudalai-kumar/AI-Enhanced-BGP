"""
Reproducibility Manifest Generator.

Generates environment_manifest.json at the repository root capturing:
  - Python version
  - Git commit SHA
  - Docker version
  - FRR image digest (via docker inspect)
  - Platform info
  - SHA-256 hashes of requirements.txt, requirements.lock, and model files
  - Dataset and model artifact hashes

Run this script after any change to requirements, models, or environment.
"""

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from typing import Optional

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_MODELS_DIR = os.path.join(_REPO_ROOT, "src", "models")
_DATA_DIR = os.path.join(_REPO_ROOT, "data")


def _sha256_file(path: str) -> str:
    """Returns hex SHA-256 digest of a file, or 'file-not-found' if missing."""
    if not os.path.exists(path):
        return "file-not-found"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(cmd: list, default: str = "unknown") -> str:
    """Runs a command and returns stripped stdout, or default on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return default


def _git_commit() -> str:
    return _run(["git", "rev-parse", "HEAD"])


def _docker_version() -> str:
    out = _run(["docker", "--version"])
    return out


def _frr_image_digest(image: str = "frrouting/frr:10.2.1") -> str:
    """Returns the RepoDigest of the FRR image if available locally."""
    out = _run(["docker", "inspect", "--format", "{{index .RepoDigests 0}}", image])
    if out and out != "unknown" and "sha256" in out:
        return out
    return "not-pulled-locally"


def generate_manifest() -> dict:
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": _git_commit(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "docker_version": _docker_version(),
        "frr_image": "frrouting/frr:10.2.1",
        "frr_image_digest": _frr_image_digest(),
        "requirements_txt_sha256": _sha256_file(os.path.join(_REPO_ROOT, "requirements.txt")),
        "requirements_lock_sha256": _sha256_file(os.path.join(_REPO_ROOT, "requirements.lock")),
        "model_rf_sha256": _sha256_file(os.path.join(_MODELS_DIR, "random_forest.joblib")),
        "model_lr_sha256": _sha256_file(os.path.join(_MODELS_DIR, "logistic_regression.joblib")),
        "model_scaler_sha256": _sha256_file(os.path.join(_MODELS_DIR, "scaler.joblib")),
        "model_metadata_sha256": _sha256_file(os.path.join(_MODELS_DIR, "model_metadata.json")),
    }
    return manifest


def main():
    print("[*] Generating reproducibility manifest...")
    manifest = generate_manifest()
    out_path = os.path.join(_REPO_ROOT, "environment_manifest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[+] Manifest written to: {out_path}")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
