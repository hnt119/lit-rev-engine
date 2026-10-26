#!/usr/bin/env python3
"""Independent, read-only audit of a prepared local-preview source archive.

Does not extract, install, run, publish or contact any external service.
"""
import argparse
import csv
import io
import posixpath
from urllib.parse import unquote, urlsplit
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import runpy
import stat
import subprocess
import zipfile

VERSION = '0.3.0-beta.4'
PREFIX = 'lit-rev-engine-' + VERSION + '/'
TREES = ('src/platform_support/', 'src/mvp/', 'src/review/', 'src/web_api/', 'apps/web/app/', 'apps/web/components/',
         'apps/web/lib/', 'examples/mvp/offline_microbiome_30_v1/')
EXACT = {'HISTORICAL_EXCERPT_VALIDATION.md','WINDOWS_SOURCE.md','requirements-windows-bootstrap.txt','USER_MANUAL.md','HISTORICAL_RETRIEVAL_VALIDATION.md','VALIDATION.md','RETRIEVAL.md','MODEL_REFERENCES.md','notices/QWEN_APACHE_LICENSE.txt','notices/MEDCPT_PUBLIC_DOMAIN_NOTICE.txt','requirements-retrieval.txt','scripts/retrieval_pack.py','README.md', 'DISTRIBUTION_TERMS.md', 'RELEASE.json', 'MANIFEST.json', 'requirements-hosted.txt', 'requirements-web-lock.txt', 'requirements-map.txt', 'requirements-map-lock.txt',
         'LICENSE', 'THIRD_PARTY_NOTICES.md', 'OPTIONAL_FEATURES.md', 'CAPABILITIES.md', 'SETTINGS.md', 'config/local-beta.example.json',
         'scripts/run_web.py', 'scripts/local_preview.py', 'scripts/license_policy.py',
         'scripts/local_beta_settings.py', 'scripts/check_local_beta.py', 'scripts/run_map_worker.py', 'apps/web/package.json', 'apps/web/pnpm-lock.yaml',
         'apps/web/tsconfig.json', 'apps/web/next-env.d.ts', 'apps/web/next.config.ts', 'apps/streamlit/theme/tokens.css'}
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
EXACT.update(WORKBENCH_DOCUMENTS)
BANNED = {'node_modules', '__pycache__', '.next', '.git', '.cache', 'tests', 'reports', 'evaluations',
          'workflow', 'data', '.mvp-web-state', '.mvp-state', 'browser-state', 'backups', 'private-exports',
          'model-cache', '.venv', '.venv-map', '.venv-preview', '.venv-bootstrap', '.local-preview-setup.json'}
BAD_SUFFIXES = ('.sqlite', '.sqlite3', '.sqlite3-wal', '.sqlite3-shm', '.db', '.db-wal', '.db-shm',
                '.pem', '.key', '.crt', '.cer', '.p12', '.pfx', '.pyc', '.safetensors', '.gguf', '.pt', '.pth', '.bin',
                '.tsbuildinfo', '.map', '.log', '.xlsx', '.zip', '.tar', '.tar.gz', '.bak')
PRIVATE = [rb'-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----',
           rb'(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})',
           rb'/Users/[A-Za-z][A-Za-z0-9._-]+/',
           rb'/home/[A-Za-z][A-Za-z0-9._-]+/', rb'[A-Za-z]:\\{1,2}Users\\{1,2}[A-Za-z][A-Za-z0-9._-]+\\{1,2}']
LICENSE_NAME = re.compile(r'(?:LICEN[CS]E|COPYING|COPYRIGHT|NOTICE)(?:\.(?:md|txt|rst))?', re.I)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def audit_markdown_links(payload):
    # Independent file-target check over copied Markdown only; never fetch URLs.
    for name, raw in payload.items():
        if not name.endswith('.md'):
            continue
        prose, fence = [], None
        for line in raw.decode('utf-8').splitlines():
            token = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
            if token:
                value = token.group(1)
                if fence is None: fence = value
                elif value[0] == fence[0] and len(value) >= len(fence): fence = None
                continue
            if fence is None: prose.append(re.sub(r'(`+).*?\1', '', line))
        for raw_target in re.findall(r'\[[^\]\n]*\]\(([^)\n]+)\)', '\n'.join(prose)):
            target = raw_target.strip().removeprefix('<').removesuffix('>')
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path: continue
            relative = unquote(parsed.path)
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), relative))
            assert not relative.startswith('/') and target != '..' and not target.startswith('../') and target in payload, 'Packaged Markdown link has no retained target: ' + name


def audit(archive, expected_source_commit, source_checkout):
    assert re.fullmatch('[0-9a-f]{40}', expected_source_commit), 'Use the exact full source commit SHA'
    source_checkout = Path(source_checkout).resolve()
    def git(*arguments):
        return subprocess.check_output(['git', *arguments], cwd=source_checkout)
    assert git('rev-parse', 'HEAD').decode().strip() == expected_source_commit, 'Source checkout HEAD mismatch'
    assert not git('status', '--porcelain=v1', '--untracked-files=all'), 'Audit against a clean source checkout'
    tracked = set(git('ls-files', '-z').decode().split('\0')) - {''}
    licenses = {name for name in tracked if '/' not in name and LICENSE_NAME.fullmatch(name)}
    expected_names = {name for name in tracked if name in EXACT or name.startswith(TREES)} | EXACT | licenses
    # README is the dedicated installation guide in this purpose-built archive.
    translations = {'WINDOWS_SOURCE.md':'docs/windows_source.md','VALIDATION.md':'docs/source_beta4_validation.md','HISTORICAL_EXCERPT_VALIDATION.md':'docs/excerpt_first_validation.md','USER_MANUAL.md':'docs/user_manual.md','HISTORICAL_RETRIEVAL_VALIDATION.md':'docs/combined_beta_validation.md','RETRIEVAL.md':'docs/hybrid_retrieval.md','MODEL_REFERENCES.md':'docs/hybrid_model_references.md',
                    'notices/QWEN_APACHE_LICENSE.txt':'docs/notices/QWEN_APACHE_LICENSE.txt',
                    'notices/MEDCPT_PUBLIC_DOMAIN_NOTICE.txt':'docs/notices/MEDCPT_PUBLIC_DOMAIN_NOTICE.txt', 'README.md': 'docs/local_preview.md', 'DISTRIBUTION_TERMS.md': 'docs/local_preview_distribution_terms.md',
                    'OPTIONAL_FEATURES.md': 'docs/local_beta_optional_features.md', 'CAPABILITIES.md': 'docs/local_beta_capabilities.md', 'SETTINGS.md':'docs/research_ai_settings.md'}
    translations.update(WORKBENCH_DOCUMENTS)
    archive = Path(archive)
    assert archive.suffix == '.zip' and archive.is_file() and not archive.is_symlink()
    names, payload = set(), {}
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            assert entry.filename.startswith(PREFIX), 'Archive has unexpected root'
            relative = entry.filename[len(PREFIX):]
            path = PurePosixPath(relative)
            assert relative and not entry.is_dir() and not path.is_absolute() and '..' not in path.parts
            assert '\\' not in relative and relative not in names, 'Unsafe or duplicate archive member'
            assert stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFREG, 'Only ordinary files may be distributed'
            assert not (set(path.parts) & BANNED)
            assert not any(part.startswith('.env') for part in path.parts)
            assert not relative.lower().endswith(BAD_SUFFIXES)
            assert relative in EXACT or relative in licenses or relative.startswith(TREES), 'Unexpected source payload: ' + relative
            assert entry.file_size <= 20 * 1024 * 1024
            raw = bundle.read(entry)
            assert not any(re.search(pattern, raw) for pattern in PRIVATE), 'Possible private data in ' + relative
            names.add(relative); payload[relative] = raw
    assert sum(map(len, payload.values())) <= 100 * 1024 * 1024
    assert EXACT <= names, 'Required source entry missing'
    assert names == expected_names, 'Archive file list differs from the committed release allowlist'
    manifest_raw = payload['MANIFEST.json']; manifest = json.loads(manifest_raw)
    assert manifest['schema'] == 'litrev.local-preview.manifest.v1' and manifest['version'] == VERSION
    assert set(manifest['files']) == names - {'MANIFEST.json'}
    for name, record in manifest['files'].items():
        assert set(record) == {'bytes', 'sha256'}
        assert record == {'bytes': len(payload[name]), 'sha256': sha(payload[name])}, 'Manifest mismatch: ' + name
    release = json.loads(payload['RELEASE.json'])
    assert release['schema'] == 'litrev.local-preview.release.v1' and release['version'] == VERSION
    assert release['source_commit'] == expected_source_commit and release['source_state'] == 'clean committed checkout'
    assert release['label'] == 'Local beta — setup required'
    assert release['product_track'] == 'A' and release['spdx_license'] == 'MIT'
    policy = runpy.run_path(str(source_checkout / "scripts/license_policy.py"))
    MIT_LICENSE_TEXT, MIT_LICENSE_SHA256, THIRD_PARTY_BOUNDARY = (policy[key] for key in ("MIT_LICENSE_TEXT", "MIT_LICENSE_SHA256", "THIRD_PARTY_BOUNDARY"))
    assert payload['LICENSE'] == MIT_LICENSE_TEXT.encode()
    assert release['license_sha256'] == MIT_LICENSE_SHA256
    assert THIRD_PARTY_BOUNDARY in payload['THIRD_PARTY_NOTICES.md'].decode()
    assert 'SPDX-License-Identifier: MIT' in payload['DISTRIBUTION_TERMS.md'].decode()
    assert THIRD_PARTY_BOUNDARY in payload['DISTRIBUTION_TERMS.md'].decode()
    package_metadata = json.loads(payload['apps/web/package.json'])
    assert package_metadata['license'] == 'MIT' and package_metadata['version'] == VERSION
    assert not any(name in names for name in ('src/review/pilot.py','src/mvp/review_pilot.py','src/web_api/pilot_routes.py','src/web_api/pilot_contracts.py','apps/web/components/review-pilot.tsx'))
    assert release['runtimes_bundled'] is False and release['models_bundled'] is False
    assert release['root_notice_files'] == sorted(licenses | {'THIRD_PARTY_NOTICES.md'})
    assert release['code_license_present'] == any(re.fullmatch(r'(?:LICEN[CS]E|COPYING)(?:\.(?:md|txt|rst))?', name, re.I) for name in licenses)
    for name, raw in payload.items():
        if name in {'RELEASE.json', 'MANIFEST.json'}:
            continue
        original = translations.get(name, name)
        assert original in tracked, 'Archive input was never committed: ' + original
        expected_raw = git('show', expected_source_commit + ':' + original)
        if name == 'question_evidence_user_guide.md':
            expected_raw = expected_raw.replace(b'](user_manual.md', b'](USER_MANUAL.md')
        assert expected_raw == raw, 'Archive input differs from committed source: ' + name
    for name, header in BLANK_TEMPLATE_HEADERS.items():
        rows = list(csv.reader(io.StringIO(payload['question_evidence_evaluation/templates/' + name].decode('utf-8'), newline='')))
        assert rows == [header.split(',')], 'Evaluation template contains observations or changed headers: ' + name
    audit_markdown_links(payload)
    snapshot = {name: sha(raw) for name, raw in payload.items() if name not in {'RELEASE.json', 'MANIFEST.json'}}
    canonical = (json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()
    assert release['source_snapshot_sha256'] == sha(canonical)
    sibling_manifest = archive.with_suffix('.manifest.json')
    assert sibling_manifest.read_bytes() == manifest_raw
    sums = archive.with_suffix('.SHA256SUMS')
    lines = sums.read_text(encoding='utf-8').splitlines()
    assert lines == [sha(archive.read_bytes()) + '  ' + archive.name,
                     sha(manifest_raw) + '  ' + sibling_manifest.name]
    # Known public fixture only: every retained blob is identified by its own manifest.
    fixture_root = 'examples/mvp/offline_microbiome_30_v1/'
    fixture = json.loads(payload[fixture_root + 'manifest.json'])
    expected_fixture = {fixture_root+'manifest.json', fixture_root+'README.md'}
    for source in fixture['sources']:
        assert source['license'] in {'https://creativecommons.org/licenses/by/4.0/', 'http://creativecommons.org/licenses/by/4.0/',
                                     'https://creativecommons.org/publicdomain/zero/1.0/', 'http://creativecommons.org/publicdomain/zero/1.0/'}
        assert source['attribution'] and source['source_url'] and source['transformations'], 'Required public-source attribution missing'
        for field in ('xml', 'metadata'):
            key = source[field + '_file']; expected_fixture.add(fixture_root + key)
            assert sha(payload[fixture_root + key]) == source[field + '_sha256']
    fixture_files = {name for name in names if name.startswith(fixture_root)}
    # Query capture/vector files listed by the reviewed public manifest are also bounded and source-only.
    assert len(fixture['sources']) == 30 and len(fixture_files) == 67
    assert expected_fixture <= fixture_files
    readme = payload['README.md'].decode()
    assert 'setup' in readme.lower() and 'local' in readme.lower()
    return {'status': 'PASS', 'archive_sha256': sha(archive.read_bytes()), 'archive_bytes': archive.stat().st_size,
            'files': len(names), 'uncompressed_bytes': sum(map(len, payload.values())),
            'manifest_and_sidecar_exact': True, 'source_snapshot_exact': True, 'public_fixture_files': len(fixture_files),
            'public_papers': len(fixture['sources']), 'runtimes_or_models_bundled': False,
            'private_state_or_credentials_observed': False, 'source_commit': expected_source_commit,
            'all_payload_files_match_commit': True, 'code_license_present': release['code_license_present'],
            'distribution_terms_included': True,
            'source_state': release['source_state'], 'extract_install_or_publish': 'NOT_RUN_BY_AUDIT'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--expected-source-commit', required=True, help='Exact full source SHA selected for this release')
    parser.add_argument('--source-checkout', required=True, type=Path, help='Clean checkout at that exact source SHA')
    args = parser.parse_args()
    result = audit(args.archive, args.expected_source_commit, args.source_checkout)
    args.report.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
