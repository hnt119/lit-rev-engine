#!/usr/bin/env python3
"""Build a reviewed source-only local preview; never install, run or publish it."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.license_policy import validate_distribution_license

VERSION = "0.3.0-beta.2"
NAME = "lit-rev-engine-" + VERSION
EXACT = {
    "requirements-hosted.txt", "requirements-web-lock.txt", "requirements-retrieval.txt", "requirements-map.txt", "requirements-map-lock.txt",
    "LICENSE", "THIRD_PARTY_NOTICES.md", "config/local-beta.example.json",
    "apps/web/package.json", "apps/web/pnpm-lock.yaml", "apps/web/tsconfig.json",
    "apps/web/next-env.d.ts", "apps/web/next.config.ts",
    "apps/streamlit/theme/tokens.css",
}
TREES = ("src/mvp/", "src/review/", "src/web_api/", "apps/web/app/",
         "apps/web/components/", "apps/web/lib/", "examples/mvp/offline_microbiome_30_v1/")
TASK_FILES = {"scripts/retrieval_pack.py", "scripts/run_web.py", "scripts/local_preview.py", "scripts/license_policy.py",
              "scripts/local_beta_settings.py", "scripts/check_local_beta.py", "scripts/run_map_worker.py",
              "apps/web/lib/comparison-passage.ts"}
DOCUMENTS = {"README.md": "docs/local_preview.md",
             "DISTRIBUTION_TERMS.md": "docs/local_preview_distribution_terms.md",
             "OPTIONAL_FEATURES.md": "docs/local_beta_optional_features.md",
             "CAPABILITIES.md": "docs/local_beta_capabilities.md",
             "SETTINGS.md": "docs/research_ai_settings.md",
             "RETRIEVAL.md": "docs/hybrid_retrieval.md",
             "MODEL_REFERENCES.md": "docs/hybrid_model_references.md",
             "notices/QWEN_APACHE_LICENSE.txt": "docs/notices/QWEN_APACHE_LICENSE.txt",
             "notices/MEDCPT_PUBLIC_DOMAIN_NOTICE.txt": "docs/notices/MEDCPT_PUBLIC_DOMAIN_NOTICE.txt"}
TRACK_B_FILES = {"src/review/pilot.py", "src/mvp/review_pilot.py", "src/web_api/pilot_routes.py",
                 "src/web_api/pilot_contracts.py", "apps/web/components/review-pilot.tsx"}
LICENSE_NAME = re.compile(r"(?:LICEN[CS]E|COPYING|COPYRIGHT|NOTICE)(?:\.(?:md|txt|rst))?", re.I)
FORBIDDEN_PARTS = {"node_modules", "__pycache__", ".next", ".git", ".cache", "tests",
                   "browser-state", "backups", "private-exports", "model-cache", ".preview",
                   ".hosted-state", ".huggingface", ".venv", ".venv-preview", ".venv-map"}
FORBIDDEN_SUFFIXES = (".sqlite", ".sqlite3", ".db", ".pem", ".key", ".crt", ".cer",
                      ".p12", ".pfx", ".pyc", ".safetensors", ".gguf", ".pt", ".pth", ".bin",
                      ".bak", ".zip", ".tar", ".tar.gz", ".tgz", ".tsbuildinfo", ".log", ".map")
SECRET_PATTERNS = (
    rb"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----",
    rb"(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})",
    rb"/Users/[A-Za-z][A-Za-z0-9._-]+/",
    rb"/home/[A-Za-z][A-Za-z0-9._-]+/",
    rb"[A-Za-z]:\\{1,2}Users\\{1,2}[A-Za-z][A-Za-z0-9._-]+\\{1,2}",
)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def safe_input(root, name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or set(path.parts) & FORBIDDEN_PARTS:
        raise ValueError("Unsafe release path: " + name)
    if (any(part.startswith((".env", ".mvp", ".local-preview")) for part in path.parts)
            or name.lower().endswith(FORBIDDEN_SUFFIXES)
            or path.name in {"cookies.json", "storage-state.json", "browser-state.json"}
            or re.search(r"cookie.*jar", path.name, re.I)):
        raise ValueError("Private/runtime release path: " + name)
    target = root / name
    if any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file():
        raise ValueError("Release inputs must be ordinary, non-symlink files: " + name)
    data = target.read_bytes()
    if any(re.search(pattern, data) for pattern in SECRET_PATTERNS):
        raise ValueError("Review possible credential or private machine path in: " + name)
    return data


def git(root, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=root)


def clean_checkout(root, expected):
    if git(root, "rev-parse", "HEAD").decode().strip() != expected:
        raise ValueError("The source commit changed during release preparation.")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("Release builds require a clean committed checkout, including no non-ignored untracked files. Use a fresh checkout and an output directory outside it.")


def committed_input(root, name, source_commit):
    data = safe_input(root, name)
    entry = git(root, "ls-tree", source_commit, "--", name).decode().strip()
    if not entry or not entry.split()[0] in {"100644", "100755"}:
        raise ValueError("Required release input is not an ordinary committed file: " + name)
    if git(root, "show", source_commit + ":" + name) != data:
        raise ValueError("Release input differs from the recorded committed source: " + name)
    return data


def build(root, output, *, expected_source_commit=None, allow_working_tree=False):
    root, output = root.resolve(), output.absolute()
    if not (root / ".git").exists():
        raise ValueError("Build from the reviewed Git checkout, not an installed preview.")
    source_commit = git(root, "rev-parse", "HEAD").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("Record an exact full Git source SHA.")
    if expected_source_commit is not None and source_commit != expected_source_commit:
        raise ValueError("Checkout HEAD does not match the explicitly selected source commit.")
    if not allow_working_tree:
        clean_checkout(root, source_commit)
    tracked = set(git(root, "ls-files", "-z").decode().split("\0")) - {""}
    if tracked & TRACK_B_FILES:
        raise ValueError("Track B pilot code is not part of the Track A beta; build from the reviewed Track A branch.")
    licenses = {name for name in tracked if "/" not in name and LICENSE_NAME.fullmatch(name)}
    names = {name for name in tracked if name in EXACT or name.startswith(TREES)} | TASK_FILES | licenses
    required = EXACT | TASK_FILES | set(DOCUMENTS.values())
    missing = required - tracked if not allow_working_tree else {name for name in required if not (root / name).is_file()}
    if missing:
        raise ValueError("Missing required release inputs: " + ", ".join(sorted(missing)))
    read = (lambda name: safe_input(root, name)) if allow_working_tree else (lambda name: committed_input(root, name, source_commit))
    license_metadata = validate_distribution_license(root)
    package_metadata = json.loads(read("apps/web/package.json"))
    if package_metadata.get("license") != "MIT" or package_metadata.get("version") != VERSION:
        raise ValueError("Beta package metadata must identify this version and the owner-approved MIT license")
    payload = {name: read(name) for name in sorted(names)}
    for destination, source in DOCUMENTS.items():
        payload[destination] = read(source)
    code_license_present = payload.get("LICENSE") is not None
    required_notices = sorted(licenses | {"THIRD_PARTY_NOTICES.md"})
    if not allow_working_tree:
        clean_checkout(root, source_commit)
    payload["RELEASE.json"] = json_bytes({
        "schema": "litrev.local-preview.release.v1", "version": VERSION,
        "label": "Local beta — setup required", "product_track": "A",
        "spdx_license": license_metadata["spdx_license"], "license_sha256": license_metadata["license_sha256"], "source_commit": source_commit,
        "source_state": "review working tree; not for publication" if allow_working_tree else "clean committed checkout",
        "source_snapshot_sha256": digest(json_bytes({p: digest(b) for p, b in payload.items()})),
        "runtimes_bundled": False, "models_bundled": False,
        "code_license_present": code_license_present,
        "distribution_terms": "DISTRIBUTION_TERMS.md; source article licenses remain separate from project code",
        "root_notice_files": required_notices,
        "optional_feature_configuration": "Research & AI Settings: session-owned non-secret preferences + memory-only credentials; existing private external --config remains supported; generation defaults off",
        "tested_platform": "macOS Apple Silicon; Python 3.12.7 and Node 24.19.0",
        "other_platforms": "Linux unverified; Windows unsupported in this beta",
        "setup_requires_network": "Python/JavaScript package installation only; no model downloads",
    })
    manifest = json_bytes({
        "schema": "litrev.local-preview.manifest.v1", "version": VERSION,
        "scope": "Every archive file except MANIFEST.json itself; paths relative to archive root",
        "files": {name: {"bytes": len(data), "sha256": digest(data)}
                  for name, data in sorted(payload.items())},
    })
    payload["MANIFEST.json"] = manifest
    archive, manifest_path, checksum_path = (output / (NAME + suffix) for suffix in (".zip", ".manifest.json", ".SHA256SUMS"))
    output.mkdir(parents=True, exist_ok=True)
    if any(p.exists() for p in (archive, manifest_path, checksum_path)):
        raise ValueError("Release outputs already exist; use a new empty review output directory.")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, data in sorted(payload.items()):
            entry = zipfile.ZipInfo(NAME + "/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            bundle.writestr(entry, data)
    manifest_path.write_bytes(manifest)
    checksum_path.write_text("".join(digest(p.read_bytes()) + "  " + p.name + "\n"
                                     for p in (archive, manifest_path)))
    return {"archive": str(archive), "archive_sha256": digest(archive.read_bytes()),
            "archive_bytes": archive.stat().st_size, "manifest": str(manifest_path),
            "checksums": str(checksum_path), "files": len(payload), "source_commit": source_commit}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New local artifact directory; never publishes")
    parser.add_argument("--expected-source-commit", help="Require this exact full SHA at HEAD")
    parser.add_argument("--allow-working-tree", action="store_true", help="Review-only archive; explicitly not for publication")
    args = parser.parse_args()
    try:
        print(json.dumps(build(ROOT, args.output, expected_source_commit=args.expected_source_commit,
                               allow_working_tree=args.allow_working_tree), indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(2, "Release preparation refused: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
