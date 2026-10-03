"""Prepare a free GPU batch and grade its returned results against prospective truth."""

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.review.cloud_retrieval import _read
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.qwen import canonical, digest, read_json
from src.review.store import ReviewStore
from tools.evaluate_qwen_pilot import assess, aggregate, pin, validate_gold, validate_trace


REQUIRED = {
    'review.py', 'src/review/qwen.py', 'src/review/cloud_retrieval.py',
    'src/review/qwen_cli.py', 'src/review/qwen_batch.py', 'src/review/cli.py',
    'src/review/store.py', 'src/review/retrieval.py', 'src/review/documents.py',
    'tools/qwen_kaggle_runner.py', 'notebooks/qwen_kaggle.ipynb',
    'tools/evaluate_qwen_kaggle.py', 'tools/evaluate_qwen_pilot.py',
    'tests/test_qwen_batch.py', 'tests/test_qwen_kaggle_pilot.py',
    'docs/qwen-kaggle-milestone.md',
}
REQUIRED.update(str(path.relative_to(ROOT)) for path in (ROOT / 'src/review').glob('*.py'))
GATE = {'min_mean_support_coverage': 0.85, 'min_complete_positives': 4,
        'positive_questions': 6, 'null_questions': 2, 'top_k': 5, 'candidate_k': 20,
        'max_batch_seconds': 1800, 'paid_inference_calls': 0}


def _contained(name):
    if not isinstance(name, str) or not name or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('Freeze paths must be contained repository paths')
    path = ROOT / name
    if not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Freeze path escapes the repository')
    return path


def verify_freeze(path):
    from src.review.qwen_batch import PROFILE
    freeze = read_json(Path(path).read_bytes())
    if (not isinstance(freeze, dict) or type(freeze.get('schema_version')) is not int
            or freeze['schema_version'] != 1 or freeze.get('status') != 'frozen_before_first_kaggle_ranking'
            or type(freeze.get('ranking_runs_before_freeze')) is not int or freeze['ranking_runs_before_freeze'] != 0):
        raise ValueError('A prospective Kaggle freeze with zero previous rankings is required')
    if canonical(freeze.get('gate')) != canonical(GATE) or canonical(freeze.get('profile')) != canonical(PROFILE):
        raise ValueError('Prospective profile or acceptance gate differs')
    required = set(REQUIRED)
    for key in ('source_dir', 'source_manifest', 'questions_file'):
        _contained(freeze.get(key))
    required.update((freeze['source_manifest'], freeze['questions_file']))
    for directory in (_contained(freeze['source_dir']), _contained(freeze['questions_file']).parent):
        required.update(str(file.relative_to(ROOT)) for file in directory.rglob('*')
                        if file.is_file() and '__pycache__' not in file.parts)
    files = freeze.get('files')
    if not isinstance(files, dict) or not required.issubset(files):
        raise ValueError('Freeze omits required code, source, truth or evaluation pins')
    for name, expected in files.items():
        if canonical(pin(_contained(name))) != canonical(expected):
            raise ValueError('Frozen Kaggle input changed: ' + name)
    return freeze


def _save_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(canonical(value))


def _ledger_hash(store):
    return digest(list(store._connection.iterdump()))


def _validate_candidate(store, project, trace, query):
    from src.review.qwen_batch import PROFILE
    if trace.get('query_id') != query['id'] or trace.get('query') != query['query']:
        raise ValueError('Kaggle trace query binding differs')
    if trace.get('method') != 'qwen_kaggle_hybrid' or trace.get('method_version') != 'lit-rev-engine.project-retrieval.kaggle-qwen.v1.qwen_hybrid':
        raise ValueError('Kaggle trace method differs')
    if trace.get('profile') != PROFILE or trace.get('parameters', {}).get('profile_sha256') != digest(PROFILE):
        raise ValueError('Kaggle trace profile differs')
    if trace.get('parameters', {}).get('candidate_k') != 20 or trace.get('answerability') != 'not_assessed' or trace.get('verification') != 'human_review_required':
        raise ValueError('Kaggle trace pool or human review boundaries differ')
    # Reuse the independent source/Unicode/context validator, without altering the trace.
    check = deepcopy(trace)
    check['method'] = 'bm25_context_blocks'
    check['method_version'] = 'lit-rev-engine.project-retrieval.v3.bm25_context_blocks'
    validate_trace(store, project, check)


def prepare(freeze_path, output):
    from src.review.qwen_batch import export_job
    freeze = verify_freeze(freeze_path)
    output = Path(output)
    if output.exists():
        raise ValueError('Use a fresh Kaggle evaluation directory')
    sources = read_json(_contained(freeze['source_manifest']).read_bytes())['sources']
    questions = read_json(_contained(freeze['questions_file']).read_bytes())['questions']
    output.mkdir(parents=True)
    upload = output / 'kaggle-upload'
    upload.mkdir()
    with ReviewStore(output / 'review.sqlite3') as store:
        project = store.create_project('Prospective Qwen Kaggle software pilot', 'systematic',
                                       'Fixed source-grounded retrieval questions')['id']
        store.import_records(project, SearchRunSpec('Licensed publisher XML, fixed Qwen evaluation'),
                             [BibliographicRecord(title=source['title'], doi=source['doi']) for source in sources])
        records = {record['doi']: record for record in store.list_records(project)}
        documents = {}
        for source in sources:
            record = records[source['doi']]
            store.record_decision(project, record['id'], 'title_abstract', 'include', 'Software pilot curator')
            store.set_full_text_status(project, record['id'], 'retrieved', 'Software pilot curator')
            store.record_decision(project, record['id'], 'full_text', 'include', 'Software pilot curator')
            documents[source['id']] = store.attach_document(
                project, record['id'], (_contained(freeze['source_dir']) / source['file']).read_bytes(),
                'jats_xml', 'Software pilot curator', 'Fixed licensed XML',
                source_url=source['publisher_xml_url'])['id']
        validate_gold(store, project, questions, documents)
        before = _ledger_hash(store)
        reference_rows, reference_traces = [], []
        for question in questions:
            reference = store.search_sources(project, question['query'], top_k=5, method='bm25_context_blocks')
            validate_trace(store, project, reference)
            reference_rows.append(assess(reference, question, documents[question['source_id']]))
            reference_traces.append(reference)
        job = export_job(store, project, [{'id': q['id'], 'query': q['query']} for q in questions],
                         output_path=upload / 'job.json', scope='included', top_k=5, candidate_k=20)
        if _ledger_hash(store) != before:
            raise ValueError('Batch export changed the review ledger')
        preparation = {'schema_version': 1, 'status': 'prepared_not_ranked', 'freeze': pin(freeze_path),
                       'project_id': project, 'document_bindings': documents,
                       'job_sha256': job['payload_sha256'], 'ledger_sha256': before,
                       'reference': {'method': 'bm25_context_blocks', 'metrics': aggregate(reference_rows),
                                     'per_question': reference_rows, 'traces': reference_traces}}
    for name in ('tools/qwen_kaggle_runner.py', 'notebooks/qwen_kaggle.ipynb'):
        shutil.copyfile(ROOT / name, upload / Path(name).name)
    _save_new(output / 'preparation.json', preparation)
    return {'status': 'prepared_not_ranked', 'directory': str(output.resolve()),
            'job_sha256': job['payload_sha256'], 'upload_files': ['job.json', 'qwen_kaggle_runner.py'],
            'notebook': str((upload / 'qwen_kaggle.ipynb').resolve()),
            'instructions': 'Import notebook in Kaggle, attach the two upload files in a private dataset, enable GPU and Internet; save its run output. No gold answers or review ledger are uploaded.'}


def grade(freeze_path, prepared, results_path, results_sha256):
    from src.review.qwen_batch import import_results
    freeze = verify_freeze(freeze_path)
    prepared = Path(prepared)
    preparation = read_json((prepared / 'preparation.json').read_bytes())
    fields = {'schema_version', 'status', 'freeze', 'project_id', 'document_bindings',
              'job_sha256', 'ledger_sha256', 'reference'}
    if (not isinstance(preparation, dict) or set(preparation) != fields
            or type(preparation['schema_version']) is not int or preparation['schema_version'] != 1
            or preparation['status'] != 'prepared_not_ranked' or preparation['freeze'] != pin(freeze_path)):
        raise ValueError('Prepared inputs differ from the prospective freeze')
    if not (prepared / 'review.sqlite3').is_file():
        raise ValueError('Prepared review ledger is missing')
    if (prepared / 'result.json').exists() or (prepared / 'validation.receipt.json').exists():
        raise ValueError('This prepared batch has already been graded or imported; preserve the first result')
    raw_results = _read(results_path)
    if raw_results['payload_sha256'] != results_sha256:
        raise ValueError('Returned results differ from the supplied saved-run hash')
    questions = read_json(_contained(freeze['questions_file']).read_bytes())['questions']
    project = preparation['project_id']
    with ReviewStore(prepared / 'review.sqlite3') as store:
        before = _ledger_hash(store)
        if before != preparation['ledger_sha256']:
            raise ValueError('Prepared ledger changed before grading')
        validate_gold(store, project, questions, preparation['document_bindings'])
        imported = import_results(store, project, job_path=prepared / 'kaggle-upload/job.json',
                                  job_sha256=preparation['job_sha256'], results_path=results_path,
                                  results_sha256=results_sha256)
        replay = import_results(store, project, job_path=prepared / 'kaggle-upload/job.json',
                                job_sha256=preparation['job_sha256'], results_path=results_path,
                                results_sha256=results_sha256)
        if imported['traces'] != replay['traces'] or _ledger_hash(store) != before:
            raise ValueError('Saved-result replay or read-only check failed')
        traces = imported['traces']
        if not isinstance(traces, list) or len(traces) != len(questions):
            raise ValueError('Returned traces differ from the fixed eight-question set')
        rows = []
        for question, trace in zip(questions, traces, strict=True):
            _validate_candidate(store, project, trace, question)
            rows.append(assess(trace, question, preparation['document_bindings'][question['source_id']]))
        # Recompute the lexical reference; do not trust a preparation-file score.
        reference_rows = []
        for question in questions:
            trace = store.search_sources(project, question['query'], top_k=5, method='bm25_context_blocks')
            validate_trace(store, project, trace)
            reference_rows.append(assess(trace, question, preparation['document_bindings'][question['source_id']]))
        # Publish a receipt only after every prospective evaluation input is validated.
        import_results(store, project, job_path=prepared / 'kaggle-upload/job.json',
                       job_sha256=preparation['job_sha256'], results_path=results_path,
                       results_sha256=results_sha256, receipt_path=prepared / 'validation.receipt.json')
    metrics, reference = aggregate(rows), aggregate(reference_rows)
    elapsed = raw_results['payload']['runtime']['elapsed_seconds']['total']
    checks = {'support_coverage': metrics['mean_support_coverage'] >= GATE['min_mean_support_coverage'],
              'complete_positives': metrics['complete_positives'] >= GATE['min_complete_positives'],
              'coverage_nonregression': metrics['mean_support_coverage'] >= reference['mean_support_coverage'],
              'complete_nonregression': metrics['complete_positives'] >= reference['complete_positives'],
              'exact_anchors_scope_replay_readonly': True,
              'batch_time': elapsed <= GATE['max_batch_seconds'], 'paid_inference_calls': True}
    result = {'schema_version': 1, 'status': 'passed' if all(checks.values()) else 'failed',
              'freeze': pin(freeze_path), 'job_sha256': preparation['job_sha256'],
              'results_sha256': results_sha256, 'checks': checks,
              'reference': {'method': 'bm25_context_blocks', 'metrics': reference, 'per_question': reference_rows},
              'candidate': {'method': 'qwen_kaggle_hybrid', 'metrics': metrics, 'per_question': rows},
              'runtime': raw_results['payload']['runtime'], 'traces': traces,
              'limitations': ['Eight fixed questions from two main articles; no clinical validation',
                              'GPU provenance is recorded runtime metadata, not cryptographic attestation',
                              'Batch execution is not a permanent interactive inference service',
                              'Candidates never verify evidence or assess answerability']}
    _save_new(prepared / 'result.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', default='docs/qwen-kaggle-freeze-v2.json')
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--output', required=True)
    graded = commands.add_parser('grade')
    graded.add_argument('--prepared', required=True)
    graded.add_argument('--results', required=True)
    graded.add_argument('--results-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        result = (prepare(args.freeze, args.output) if args.command == 'prepare'
                  else grade(args.freeze, args.prepared, args.results, args.results_sha256))
        print(canonical(result))
        return 2 if result['status'] == 'failed' else 0
    except (ValueError, OSError, AssertionError, sqlite3.Error) as error:
        print('Kaggle evaluation stopped: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
