#!/usr/bin/env python3
"""Opt-in HTTP acceptance of optional features in a REAL extracted local beta.

Run this from the source checkout, not from inside the installed app. Configure
its supported loopback adapters with SOFTWARE_MOCK_PLANNER and
SOFTWARE_MOCK_PROPOSALS, revision fixture-v1, at the supplied unused mock port.
This runner never starts the application, installs dependencies, downloads
weights, executes a literature search, or calls a remote model/provider.
The optional --real-map step explicitly computes local embeddings of the saved
public example. Software mocks and real embeddings are reported separately.
"""
from __future__ import annotations

import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
from urllib.parse import quote, urlencode, urlsplit
from uuid import uuid4

from check_installed_preview import Browser, FORBIDDEN_PORTS, P, digest, private_json

PLANNER = 'SOFTWARE_MOCK_PLANNER'
PROPOSALS = 'SOFTWARE_MOCK_PROPOSALS'
REVISION = 'fixture-v1'
BGE_REVISION = '5c38ec7c405ec4b44b94cc5a9bb96e735b38267a'
RESERVED_PORTS = FORBIDDEN_PORTS | {3088, 3099, 8501, 8502}
TRACK_B_ONLY = ('src/review/pilot.py', 'src/mvp/review_pilot.py',
    'src/web_api/pilot_routes.py', 'src/web_api/pilot_contracts.py',
    'apps/web/components/review-pilot.tsx', 'examples/review/researcher-pilot.template.json')


def mock_output(body):
    """Protocol fixture, deliberately not an intelligent or scientific model."""
    model = body['model']
    assert model in {PLANNER, PROPOSALS}
    assert body.get('temperature') == 0 and body.get('stream') is False
    assert body.get('response_format') == {'type': 'json_object'}
    assert 'tools' not in body and 'tool_choice' not in body
    assert len(body['messages']) == 2
    assert [item['role'] for item in body['messages']] == ['system', 'user']
    packet = json.loads(body['messages'][1]['content'])
    if model == PLANNER:
        assert body['max_tokens'] == 4096 and set(packet) == {'original_question'}
        # Empty concepts are intentionally unresolved, reviewable intent, not an
        # invented working Boolean query or a claim of retrieval quality.
        output = {'original_question': packet['original_question'], 'input_mode': 'natural_question',
            'manual_strategy': None, 'concepts': [], 'variants': [], 'ambiguities': [],
            'date_filter': None, 'sort': 'relevance'}
    else:
        assert body['max_tokens'] == 2048
        assert packet['schema_version'] == 'mvp.proposal-packet.v1'
        assert packet['context_scope'] == 'retrieved_context_only'
        evidence = {item['evidence_id']: item for item in packet['evidence']}
        cells = []
        for field in packet['fields']:
            refs = []
            value = None
            missing = 'This software fixture supplies no value; retrieved context is incomplete.'
            if field['field_id'] == 'population' and field['evidence_ids']:
                candidate = evidence[field['evidence_ids'][0]]
                assert candidate['reference']['paper_id'] == packet['paper_id']
                refs = [{'evidence_id': candidate['evidence_id'], 'quote': candidate['reference']['quote']}]
                value = 'SYNTHETIC SOFTWARE SUGGESTION: edit and assess against the exact source.'
                missing = ''
            cells.append({'field_id': field['field_id'], 'value': value, 'references': refs,
                'reason': 'Local software mock only. Exact quotation does not establish support.',
                'missing_information': missing, 'context_scope': 'retrieved_context_only'})
        output = {'cells': cells}
    return {'model': model, 'choices': [{'finish_reason': 'stop', 'message': {
        'role': 'assistant', 'content': json.dumps(output)}}],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}}


class MockServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, port):
        self.calls, self.errors = Counter(), []
        self.call_lock = threading.Lock()
        owner = self
        class Handler(BaseHTTPRequestHandler):
            # Existing bounded adapters retain their transport socket while
            # checking the finite response. Keep this explicit fixture HTTP/1.1
            # with Content-Length instead of BaseHTTPRequestHandler's HTTP/1.0.
            protocol_version = 'HTTP/1.1'

            def log_message(self, *_):
                pass  # Never log source packets, credentials or cookies.

            def do_POST(self):
                try:
                    assert self.path == '/v1/chat/completions'
                    size = int(self.headers.get('Content-Length', '0'))
                    assert 0 < size <= 262144
                    assert self.headers.get('Authorization') is None
                    body = json.loads(self.rfile.read(size))
                    with owner.call_lock:
                        owner.calls[body.get('model', 'UNKNOWN')] += 1
                    raw = json.dumps(mock_output(body)).encode()
                    self.send_response(200)
                except Exception as error:
                    # Keep errors generic: exception text may include source data.
                    owner.errors.append(type(error).__name__)
                    raw = b'{"error":"software mock protocol assertion failed"}'
                    self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        super().__init__(('127.0.0.1', port), Handler)

    def counts(self):
        with self.call_lock:
            return dict(self.calls)


def exact_context(context, reference):
    assert context['reference'] == reference
    assert context['paper']['id'] == reference['paper_id']
    chunk = context['block']
    assert chunk['text'][reference['start']-chunk['start']:reference['end']-chunk['start']] == reference['quote']
    assert reference['integrity'] == 'checked'


def model_profile(profile, model, endpoint):
    assert profile['model'] == model and profile['model_revision'] == REVISION
    assert profile['endpoint'] == endpoint
    assert profile['retries'] == 0 and profile['paid_calls'] is False
    assert profile['spend_cap_usd'] == 0 and profile['temperature'] == 0
    if model == PLANNER:
        assert profile['max_runtime_seconds'] == 10 and profile['max_output_bytes'] == 24576
    else:
        assert profile['max_runtime_seconds'] == 35 and profile['timeout_seconds'] == 10
        assert profile['max_response_bytes'] == 32768


def installed_checks(path):
    assert path.is_dir() and not path.is_symlink()
    assert all(not (path / item).exists() for item in TRACK_B_ONLY), 'Track B must not enter Track A distribution'
    release = json.loads((path / 'RELEASE.json').read_text())
    assert release['version'] == '0.3.0-beta.1' and release['product_track'] == 'A'
    assert release['spdx_license'] == 'MIT' and release['source_state'] == 'clean committed checkout'
    assert re.fullmatch('[0-9a-f]{40}', release['source_commit'])
    return {'source_commit': release['source_commit'], 'track_b_absent': True,
        'version': release['version'], 'license': release['spdx_license']}


def check(browser, server, endpoint, real_map, map_timeout):
    browser.bootstrap()
    caps = browser.call('GET', P + '/capabilities').json()
    assert caps['live_available'] is False
    assert browser.call('GET', P + '/admission/status').json() == {'mode': 'local', 'admitted': True}
    question = 'PUBLIC SOFTWARE QA: microbiome women; unresolved intent and no scientific assessment'
    workspace = browser.call('POST', P + '/workspaces', {'request_id': str(uuid4()),
        'mode': 'saved_example', 'question': question}).json()
    root = P + '/workspaces/' + workspace['id']
    planner_caps = browser.call('GET', root + '/search-plan-capabilities').json()
    assert planner_caps['manual_enabled'] and not planner_caps['execution_enabled']
    assert planner_caps['planner']['enabled'] is True
    model_profile(planner_caps['planner']['model_profile'], PLANNER, endpoint)
    assert planner_caps['planner']['model_profile']['max_calls'] == 1
    browser.call('GET', root)
    browser.call('GET', '/', base=browser.origin)
    assert server.counts() == {}, 'Reads, startup and navigation must not call model adapters'
    plan = browser.call('POST', root + '/search-plans', {'request_id': str(uuid4()),
        'draft': {'original_question': question, 'input_mode': 'natural_question'}}).json()
    plan_path = root + '/search-plans/' + plan['revision']['plan_id']
    request = {'request_id': str(uuid4()), 'expected_revision_id': plan['revision']['revision_id'],
        'original_question': question}
    receipt = browser.call('POST', plan_path + '/propose', request).json()
    assert server.counts() == {PLANNER: 1}
    assert receipt['result']['draft']['original_question'] == question
    assert receipt['result']['draft']['concepts'] == []
    assert browser.call('POST', plan_path + '/propose', request).json() == receipt
    reopened_plan = browser.call('GET', plan_path).json()
    assert reopened_plan['executions'] == [] and reopened_plan['approvals'] == []
    assert reopened_plan['revision'] == plan['revision'] and len(reopened_plan['proposals']) == 1
    assert browser.call('GET', root).json()['searches'] == []
    assert server.counts() == {PLANNER: 1}, 'Exact replay must not generate twice'

    search = browser.call('POST', root + '/searches', {'request_id': str(uuid4()),
        'query': 'saved public example only', 'max_results': 30}).json()
    assert search['mode'] == 'saved_example' and len(search['papers']) == 30
    papers = [item['id'] for item in search['papers'][:3]]
    prep = browser.call('POST', root + '/source-preparations', {'request_id': str(uuid4()),
        'search_id': search['id'], 'paper_ids': papers}).json()
    assert prep['selected_paper_ids'] == papers and len(prep['sources']) == 3
    fields = [{'id': 'population', 'label': 'Population', 'subquestion': 'microbiome women'},
        {'id': 'missing', 'label': 'Missing information fixture', 'subquestion': 'microbiome'}]
    board = browser.call('POST', root + '/boards', {'request_id': str(uuid4()),
        'question': question, 'preparation_id': prep['id'], 'paper_ids': papers, 'fields': fields}).json()
    definition = board['definition']; revision = definition['revision_id']
    path = root + '/boards/' + definition['board_id']
    capability = browser.call('GET', path + '/proposal-capabilities').json()
    assert capability['enabled'] and capability['retries'] == 0 and capability['paid_calls'] is False
    assert capability['max_calls'] == 3 and capability['max_papers'] == 3 and capability['max_cells'] == 9
    model_profile(capability['model_profile'], PROPOSALS, endpoint)
    before = browser.call('GET', root + '/exports?format=json').json()
    browser.call('GET', path)
    browser.call('GET', path + '/proposals?' + urlencode({'revision_id': revision}))
    assert server.counts() == {PLANNER: 1}
    request = {'request_id': str(uuid4()), 'expected_revision_id': revision,
        'paper_ids': [papers[0]], 'field_ids': [item['id'] for item in fields]}
    run = browser.call('POST', path + '/proposal-runs', request).json()
    assert run['state'] == 'succeeded' and len(run['calls']) == 1 and len(run['proposals']) == 2
    assert server.counts() == {PLANNER: 1, PROPOSALS: 1}
    assert run['retrieval_profile_sha256'] == definition['retrieval_profile_sha256']
    assert browser.call('POST', path + '/proposal-runs', request).json() == run
    proposal = next(item for item in run['proposals'] if item['field_id'] == 'population')
    empty = next(item for item in run['proposals'] if item['field_id'] == 'missing')
    assert proposal['value'] and proposal['references'] and empty['value'] is None and empty['missing_information']
    for item in (proposal, empty):
        assert item['semantic_assessment'] == 'unassessed'
        assert item['status'] == 'pending' and item['context_scope'] == 'retrieved_context_only'
        assert item['review_state'] == 'ai_suggestion_needs_review_not_independently_verified'
        assert item['board_revision_id'] == revision and item['source_manifest_sha256'] == definition['source_manifest_sha256']
    reference = proposal['references'][0]
    context = browser.call('GET', path + '/proposals/' + proposal['id'] + '/references/' + reference['id'] + '/context').json()
    exact_context(context, reference)
    adopt = {'request_id': str(uuid4()), 'expected_revision_id': revision, 'draft_version': 0,
        'expected_cell_head_id': None, 'value': 'SYNTHETIC researcher-edited software draft; not a research judgment',
        'reason': 'Explicit software QA action; inspection and support remain unassessed', 'missing_information': ''}
    adopt_path = path + '/proposals/' + proposal['id'] + '/adopt'
    browser.call('POST', adopt_path, dict(adopt, semantic_assessment='human_supported'), expected=422)
    draft = browser.call('POST', adopt_path, adopt).json()
    assert draft['data']['value'] == adopt['value'] and draft['version'] == 1
    assert draft['data']['semantic_assessment'] == 'unassessed'
    assert draft['data']['inspected_ranges'] == [] and draft['data']['scope_result'] == 'not_assessed'
    assert len(draft['data']['references']) == len(proposal['references'])
    dismissed = browser.call('POST', path + '/proposals/' + empty['id'] + '/dismiss', {
        'request_id': str(uuid4()), 'expected_revision_id': revision, 'reason': 'Explicit software fixture dismissal'}).json()
    assert dismissed['status'] == 'dismissed'
    browser.call('POST', path + '/cell-revisions', {'request_id': str(uuid4()),
        'expected_revision_id': revision, 'paper_id': papers[0], 'field_id': 'population',
        'draft_version': draft['version']}, expected=422)
    reopened = Browser(browser.origin, browser.saved()); reopened.bootstrap()
    saved = reopened.call('GET', path + '/drafts/' + quote(papers[0], safe='') + '/population').json()
    assert saved == draft and all(item['head'] is None for item in reopened.call('GET', path).json()['cells'])
    audit = reopened.call('GET', path + '/proposal-audit?' + urlencode({'revision_id': revision})).json()
    assert audit['schema_version'] == 'mvp.proposal-audit.v1'
    assert {item['action'] for item in audit['events']} == {'adopted', 'dismissed'}
    after = reopened.call('GET', root + '/exports?format=json').json()
    assert {k:v for k,v in before.items() if k != 'exported_at'} == {k:v for k,v in after.items() if k != 'exported_at'}
    assert server.counts() == {PLANNER: 1, PROPOSALS: 1} and not server.errors
    result = {'status': 'PASS', 'transport': 'real extracted production HTTP; supported configured loopback adapters',
        'software_mock_llm': {'status': 'PASS', 'models': [PLANNER, PROPOSALS], 'revision': REVISION,
            'actual_calls': server.counts(), 'reported_fixture_usage_not_measured_model_tokens': True,
            'remote_calls': 0, 'paid_calls': 0, 'no_read_triggered_generation': True,
            'request_replay_no_extra_calls': True, 'plan_not_executed': True,
            'proposal_exact_source_context': True, 'adopt_is_unassessed_unsubmitted_draft': True,
            'dismissal_and_cookie_preserving_reopen': True},
        'saved_public_example': {'records': len(search['papers']), 'prepared_reports': len(prep['sources']),
            'board_cells': len(board['cells']), 'source_types': sorted({s['source_type'] for s in prep['sources']})},
        'real_local_map': {'status': 'NOT_RUN', 'reason': '--real-map not selected'},
        'live_pubmed': {'status': 'NOT_RUN', 'reason': 'Disabled offline QA configuration'},
        'real_llm': {'status': 'NOT_RUN', 'reason': 'Only explicit protocol fixtures, no real model'},
        'scientific_quality': 'NOT_EVALUATED', 'human_usefulness': 'NOT_EVALUATED',
        'browser_visual_walkthrough': 'NOT_RUN: this is API software acceptance',
        'workspace_id': workspace['id'], 'search_id': search['id'], 'board_id': definition['board_id'],
        'api_requests': browser.requests + reopened.requests}
    if real_map:
        assert caps['map']['ready'] is True, 'Cached optional mapping dependencies/model are not ready'
        start = time.monotonic()
        submitted = browser.call('POST', root + '/maps', {'request_id': str(uuid4()),
            'search_id': search['id'], 'profile_id': 'paper_bge_v1', 'rebuild': True}).json()
        assert submitted['reused'] is False
        job = submitted['job']
        while job['status'] in {'queued', 'running'} and time.monotonic()-start < map_timeout:
            time.sleep(1)
            job = browser.call('GET', root + '/jobs/' + job['id']).json()
        assert job['status'] == 'succeeded', {'map_status': job['status'], 'error': job.get('error')}
        mapped = browser.call('GET', root + '/maps/' + job['map_id']).json()
        artifact = mapped['artifact']; profile = artifact['embedding_profile']
        assert profile['model'] == 'BAAI/bge-small-en-v1.5' and profile['model_revision'] == BGE_REVISION
        assert profile['local_files_only'] is True and profile['trust_remote_code'] is False
        assert mapped['counts']['map_points'] == 30 and len(artifact['ordered_paper_ids']) == 30
        assert set(artifact['ordered_paper_ids']) == {item['id'] for item in search['papers']}
        assert profile['files_sha256'] and profile['runtime_versions']
        assert server.counts() == {PLANNER: 1, PROPOSALS: 1}
        result['real_local_map'] = {'status': 'PASS', 'new_job': True, 'reused': False,
            'model': profile['model'], 'revision': profile['model_revision'], 'map_points': 30,
            'model_files_sha256': profile['files_sha256'], 'runtime_versions': profile['runtime_versions'],
            'elapsed_seconds': round(time.monotonic()-start, 3), 'map_id': job['map_id'],
            'local_files_only': True, 'scientific_quality': 'NOT_EVALUATED'}
    result['api_requests'] = browser.requests + reopened.requests
    return result, browser.saved()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--mock-port', type=int, required=True)
    parser.add_argument('--qa-root', type=Path, required=True)
    parser.add_argument('--installed-app', type=Path)
    parser.add_argument('--real-map', action='store_true')
    parser.add_argument('--map-timeout', type=int, default=240)
    args = parser.parse_args()
    origin = urlsplit(args.origin)
    assert origin.scheme == 'http' and origin.hostname == '127.0.0.1'
    assert origin.port and origin.port not in RESERVED_PORTS and origin.path in {'', '/'}
    assert not origin.username and not origin.password and not origin.query and not origin.fragment
    assert 1024 <= args.mock_port <= 65535 and args.mock_port not in RESERVED_PORTS | {origin.port}
    assert 5 <= args.map_timeout <= 600
    qa = args.qa_root.expanduser().absolute()
    assert qa.is_absolute() and not qa.exists() and not qa.is_symlink(), 'Use a new private QA directory'
    if args.installed_app:
        app = args.installed_app.resolve()
        assert app not in (qa, *qa.parents) and qa not in app.parents
    qa.mkdir(mode=0o700, parents=False)
    assert stat.S_IMODE(qa.stat().st_mode) == 0o700
    report = {'status': 'FAIL', 'live_pubmed': {'status': 'NOT_RUN'}, 'real_llm': {'status': 'NOT_RUN'},
        'scientific_quality': 'NOT_EVALUATED', 'human_usefulness': 'NOT_EVALUATED'}
    server = None
    try:
        if args.installed_app:
            report['installed_package'] = installed_checks(args.installed_app.resolve())
        # Binding with address reuse disabled proves this is not an existing
        # user endpoint. No request is sent to any other model service.
        server = MockServer(args.mock_port)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        browser = Browser(args.origin.rstrip('/'))
        findings, cookies = check(browser, server, 'http://127.0.0.1:' + str(args.mock_port) + '/v1/chat/completions',
            args.real_map, args.map_timeout)
        report.update(findings)
        private_json(qa / 'session.private.json', cookies)
        private_json(qa / 'report.json', report)
        print(json.dumps({'status': report['status'], 'report': str(qa / 'report.json'),
            'mock_calls': server.counts(), 'real_local_map': report['real_local_map']['status']}))
    except Exception as error:
        report['failure_type'] = type(error).__name__
        # Intentionally omit error text: HTTP assertion bodies can contain
        # quotations and session details. Reproduce locally to inspect them.
        if server:
            report['mock_calls'] = server.counts(); report['mock_protocol_errors'] = server.errors
        private_json(qa / 'report.json', report)
        raise
    finally:
        if server:
            server.shutdown(); server.server_close()


if __name__ == '__main__':
    main()
