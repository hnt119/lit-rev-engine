#!/usr/bin/env python3
"""Build a reviewed source-only local preview; never install, run or publish it."""
import argparse
import csv
import io
import posixpath
from urllib.parse import unquote, urlsplit
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

VERSION = "0.3.0-beta.4"
NAME = "lit-rev-engine-" + VERSION
EXACT = {
    "requirements-hosted.txt", "requirements-windows-bootstrap.txt", "requirements-web-lock.txt", "requirements-retrieval.txt", "requirements-map.txt", "requirements-map-lock.txt",
    "LICENSE", "THIRD_PARTY_NOTICES.md", "config/local-beta.example.json",
    "apps/web/package.json", "apps/web/pnpm-lock.yaml", "apps/web/tsconfig.json",
    "apps/web/next-env.d.ts", "apps/web/next.config.ts",
    "apps/streamlit/theme/tokens.css",
}
TREES = ("src/platform_support/", "src/mvp/", "src/review/", "src/web_api/", "apps/web/app/",
         "apps/web/components/", "apps/web/lib/", "examples/mvp/offline_microbiome_30_v1/")
TASK_FILES = {"scripts/retrieval_pack.py", "scripts/run_web.py", "scripts/local_preview.py", "scripts/license_policy.py",
              "scripts/local_beta_settings.py", "scripts/check_local_beta.py", "scripts/run_map_worker.py",
              "apps/web/lib/comparison-passage.ts"}
DOCUMENTS = {"README.md": "docs/local_preview.md",
             "DISTRIBUTION_TERMS.md": "docs/local_preview_distribution_terms.md",
             "OPTIONAL_FEATURES.md": "docs/local_beta_optional_features.md",
             "CAPABILITIES.md": "docs/local_beta_capabilities.md",
             "SETTINGS.md": "docs/research_ai_settings.md",
             "WINDOWS_SOURCE.md": "docs/windows_source.md",
             "VALIDATION.md": "docs/source_beta4_validation.md",
             "HISTORICAL_EXCERPT_VALIDATION.md": "docs/excerpt_first_validation.md",
             "USER_MANUAL.md": "docs/user_manual.md",
             "HISTORICAL_RETRIEVAL_VALIDATION.md": "docs/combined_beta_validation.md",
             "RETRIEVAL.md": "docs/hybrid_retrieval.md",
             "MODEL_REFERENCES.md": "docs/hybrid_model_references.md",
             "notices/QWEN_APACHE_LICENSE.txt": "docs/notices/QWEN_APACHE_LICENSE.txt",
             "notices/MEDCPT_PUBLIC_DOMAIN_NOTICE.txt": "docs/notices/MEDCPT_PUBLIC_DOMAIN_NOTICE.txt"}
# Deliberately explicit public documentation and blank templates. Never glob this
# evaluation directory: future participant observations must not enter assets.
WORKBENCH_DOCUMENTS = {'question_evidence_user_guide.md': 'docs/question_evidence_user_guide.md',
 'question_evidence_validation.md': 'docs/question_evidence_validation.md',
 'question_evidence_validation_software.json': 'docs/question_evidence_validation_software.json',
 'question_evidence_access_audit.md': 'docs/question_evidence_access_audit.md',
 'question_evidence_workbench.md': 'docs/question_evidence_workbench.md',
 'question_evidence_windows_validation.md': 'docs/question_evidence_windows_validation.md',
 'question_evidence_evaluation/README.md': 'docs/question_evidence_evaluation/README.md',
 'question_evidence_evaluation/acceptance.md': 'docs/question_evidence_evaluation/acceptance.md',
 'question_evidence_evaluation/analysis.md': 'docs/question_evidence_evaluation/analysis.md',
 'question_evidence_evaluation/comparators.md': 'docs/question_evidence_evaluation/comparators.md',
 'question_evidence_evaluation/observer.md': 'docs/question_evidence_evaluation/observer.md',
 'question_evidence_evaluation/participant.md': 'docs/question_evidence_evaluation/participant.md',
 'question_evidence_evaluation/protocol.md': 'docs/question_evidence_evaluation/protocol.md',
 'question_evidence_evaluation/seed_lock.md': 'docs/question_evidence_evaluation/seed_lock.md',
 'question_evidence_evaluation/tasks.md': 'docs/question_evidence_evaluation/tasks.md',
 'question_evidence_evaluation/templates/assignments.csv': 'docs/question_evidence_evaluation/templates/assignments.csv',
 'question_evidence_evaluation/templates/conditions.csv': 'docs/question_evidence_evaluation/templates/conditions.csv',
 'question_evidence_evaluation/templates/documents.csv': 'docs/question_evidence_evaluation/templates/documents.csv',
 'question_evidence_evaluation/templates/field_checks.csv': 'docs/question_evidence_evaluation/templates/field_checks.csv',
 'question_evidence_evaluation/templates/issues.csv': 'docs/question_evidence_evaluation/templates/issues.csv',
 'question_evidence_evaluation/templates/observer_events.csv': 'docs/question_evidence_evaluation/templates/observer_events.csv',
 'question_evidence_evaluation/templates/participant_feedback.csv': 'docs/question_evidence_evaluation/templates/participant_feedback.csv',
 'question_evidence_evaluation/templates/seeds.csv': 'docs/question_evidence_evaluation/templates/seeds.csv',
 'question_evidence_evaluation/templates/timings.csv': 'docs/question_evidence_evaluation/templates/timings.csv'}
BLANK_TEMPLATE_HEADERS = {'assignments.csv': 'participant_code,protocol_version,task_id,matched_set_id,condition_id,order,prior_exposure,assignment_locked_at,amendment',
 'conditions.csv': 'condition_id,tool,version_or_model,plan_features,date,source_scope,source_manifest_sha256,context_budget,tools_allowed,access_status,authorization_reference,cost_policy,execution_status,limitation',
 'documents.csv': 'set_id,report_id,title,pmid,doi,source_filename,source_format,source_sha256,blocks_sha256,parser_id,license_or_local_permission,attribution,provided_scope,permission_for_cloud,cohort_or_site_case_verified_by,verification_date,selection_status',
 'field_checks.csv': 'participant_code,condition_id,set_id,report_id,field_id,definition_revision,submitted_value_status,source_reference,cohort_or_observation_scope,assessable,adjudicator_code,support_applicability,wrong_report,wrong_cohort,numeric_or_unit_error,negation_error,critical_error,correction_required,resolution,judged_at',
 'issues.csv': 'issue_id,participant_code,condition_id,task_id,observed_at,category,severity,observed_problem,expected_outcome,source_or_scope_effect,assistance,workaround,execution_status,follow_up',
 'observer_events.csv': 'participant_code,condition_id,set_id,task_id,event_timestamp,event_type,observed_action,participant_statement_if_permitted,assistance_category,assistance_detail,issue_id,private_evidence_reference',
 'participant_feedback.csv': 'participant_code,condition_id,task_id,question_id,actual_response,voluntary_reuse,publication_permission_reference,recorded_at',
 'seeds.csv': 'seed_id,identifier_type,identifier,established_pmid,identity_evidence,development_or_held_out,scope_approval,database_coverage,test_date,limits,lock_timestamp,lock_sha256,query_revision,query_membership,preview_recovery,execution_status,unresolved_reason',
 'timings.csv': 'participant_code,condition_id,set_id,task_id,segment_id,segment_type,start_timestamp,end_timestamp,elapsed_seconds,actual_or_observed,completion_status,assistance_seconds,exclusion_reason'}
DOCUMENTS.update(WORKBENCH_DOCUMENTS)

TRACK_B_FILES = {"src/review/pilot.py", "src/mvp/review_pilot.py", "src/web_api/pilot_routes.py",
                 "src/web_api/pilot_contracts.py", "apps/web/components/review-pilot.tsx"}
LICENSE_NAME = re.compile(r"(?:LICEN[CS]E|COPYING|COPYRIGHT|NOTICE)(?:\.(?:md|txt|rst))?", re.I)
FORBIDDEN_PARTS = {"node_modules", "__pycache__", ".next", ".git", ".cache", "tests",
                   "browser-state", "backups", "private-exports", "model-cache", ".preview",
                   ".hosted-state", ".huggingface", ".venv", ".venv-preview", ".venv-map", ".venv-bootstrap"}
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


def packaged_document(destination, raw):
    # Only this new guide's two source-relative manual links need the existing
    # archive alias. Every other documentation byte stays unchanged.
    if destination == 'question_evidence_user_guide.md':
        return raw.replace(b'](user_manual.md', b'](USER_MANUAL.md')
    return raw


def validate_workbench_documents(payload):
    for name, header in BLANK_TEMPLATE_HEADERS.items():
        raw = payload['question_evidence_evaluation/templates/' + name]
        rows = list(csv.reader(io.StringIO(raw.decode('utf-8'), newline='')))
        if rows != [header.split(',')]:
            raise ValueError('Evaluation templates must contain the exact public header only; no observations may be packaged: ' + name)
    # Validate local file targets in actual copied Markdown. Ignore links inside
    # fenced/inline code, external URLs and same-document anchors; do not fetch.
    for name, raw in payload.items():
        if not name.endswith('.md'):
            continue
        visible, fence = [], None
        for line in raw.decode('utf-8').splitlines():
            match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
            if match:
                token = match.group(1)
                if fence is None:
                    fence = token
                elif token[0] == fence[0] and len(token) >= len(fence):
                    fence = None
                continue
            if fence is None:
                visible.append(re.sub(r'(`+).*?\1', '', line))
        for target in re.findall(r'\[[^\]\n]*\]\(([^)\n]+)\)', '\n'.join(visible)):
            target = target.strip()
            if target.startswith('<') and target.endswith('>'):
                target = target[1:-1]
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            relative = unquote(parsed.path)
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), relative))
            if relative.startswith('/') or resolved == '..' or resolved.startswith('../') or resolved not in payload:
                raise ValueError('Packaged Markdown link has no retained local target: ' + name + ' -> ' + relative)


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
        payload[destination] = packaged_document(destination, read(source))
    validate_workbench_documents(payload)
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
        "tested_platform": "macOS arm64 source workflows (candidate 8cf4379); Windows x64 Core and bounded Qwen/MedCPT CPU HTTP retrieval (candidate c27aea0, runner windows-2025, observed 2022Server / 10.0.26100). Exact final archive acceptance is a separate external RELEASE_ACCEPTANCE.json; candidate evidence/limits remain in VALIDATION.md.",
        "other_platforms": "Physical Windows 11 NOT_RUN; Linux installation unverified; Intel Mac and Windows ARM unqualified; native executables withheld",
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
                                     for p in (archive, manifest_path)), encoding='utf-8')
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
