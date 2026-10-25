#!/usr/bin/env python3
"""Opt-in installed application check using a new public-example workspace only.

No browser automation, live providers, models, original databases or publication.
Private test cookies are kept only in memory. This is software validation.
"""
import argparse
import json
from pathlib import Path
import time
from urllib.parse import quote, urlencode, urlsplit
from uuid import uuid4

from check_installed_preview import Browser, FORBIDDEN_PORTS, digest


def check(origin):
    first, stranger = Browser(origin), Browser(origin)
    first.bootstrap(); stranger.bootstrap()
    caps = first.call('GET', '/api/v1/capabilities').json()
    assert not caps['live_available'] and not caps['map']['ready']
    workspace = first.call('POST', '/api/v1/workspaces', {
        'request_id': str(uuid4()), 'mode': 'saved_example',
        'question': 'PUBLIC SOFTWARE QA: comparison passage round trip'}).json()
    root = '/api/v1/workspaces/' + workspace['id']
    search = first.call('POST', root + '/searches', {'request_id': str(uuid4()),
        'query': 'saved public example only', 'max_results': 30}).json()
    selected = [paper['id'] for paper in search['papers'][:4]]
    prep = first.call('POST', root + '/source-preparations', {
        'request_id': str(uuid4()), 'search_id': search['id'], 'paper_ids': selected}).json()
    fields = [{'id': 'diet', 'label': 'Diet', 'subquestion': 'microbiome diet'}]
    view = first.call('POST', root + '/boards', {'request_id': str(uuid4()),
        'question': 'microbiome diet', 'preparation_id': prep['id'],
        'paper_ids': selected[:3], 'fields': fields}).json()
    definition = view['definition']; board = root + '/boards/' + definition['board_id']
    identity = {'board_id': definition['board_id'], 'board_revision_id': definition['revision_id']}
    cell_identity = dict(identity, paper_id=selected[0], field_id='diet')
    params = {'revision_id': definition['revision_id'], 'paper_id': selected[0], 'field_id': 'diet'}
    context_path = board + '/passage-search-context?' + urlencode(params)
    scope = 'board-evidence:' + ':'.join([identity['board_id'], identity['board_revision_id'],
        selected[0].encode('utf-8').hex(), 'diet'.encode('utf-8').hex()])
    draft_path = root + '/drafts/' + quote(scope, safe='')
    cell_path = board + '/drafts/' + quote(selected[0], safe='') + '/diet'
    cell = first.call('PUT', cell_path, {'expected_revision_id': definition['revision_id'],
        'version': 0, 'expected_cell_head_id': None,
        'data': {'value': 'UNSUBMITTED software draft', 'semantic_assessment': 'unassessed'}}).json()
    exported = first.call('GET', board + '/exports?format=json&history=true').body
    state_before = first.call('GET', root).json()
    context = first.call('GET', context_path).json()
    assert context['paper_ids'] == [selected[0]] and context['board_paper_ids'] == selected[:3]
    assert context['question'] == fields[0]['subquestion']
    first.call('GET', draft_path)
    after_reads = first.call('GET', root).json()
    assert [len(state_before[key]) for key in ('searches', 'preparations', 'runs')] == [
        len(after_reads[key]) for key in ('searches', 'preparations', 'runs')]
    assert first.call('GET', cell_path).json() == cell
    assert first.call('GET', board + '/exports?format=json&history=true').body == exported
    stranger.call('GET', context_path, expected=404)
    payload = {'question': 'microbiome', 'top_k': 20,
        'expected_preparation_id': prep['id'], 'expected_source_revision': prep['source_revision']}
    unrelated = first.call('POST', root + '/evidence-runs', dict(payload, request_id=str(uuid4()))).json()
    context = first.call('GET', context_path).json()
    assert not any(item.get('board_context') == cell_identity for item in first.call('GET', root).json()['runs'])
    board_run = first.call('POST', root + '/evidence-runs', dict(payload,
        request_id=str(uuid4()), board_context=identity)).json()
    assert board_run['passages'] and {p['paper_id'] for p in board_run['passages']} <= set(selected[:3])
    run = first.call('POST', root + '/evidence-runs', dict(payload,
        request_id=str(uuid4()), board_context=cell_identity)).json()
    assert run['passages'] and {p['paper_id'] for p in run['passages']} == {selected[0]}
    assert len(run['passages']) <= 20
    context = first.call('GET', context_path).json()
    matching = [item['id'] for item in first.call('GET', root).json()['runs'] if item.get('board_context') == cell_identity]
    assert run['id'] in matching and board_run['id'] not in matching and unrelated['id'] not in matching
    draft = {'question': 'microbiome edited query', 'top_k': 20, 'selected_run_id': run['id']}
    saved = first.call('PUT', draft_path, {'version': 0, 'data': draft}).json()
    assert first.call('GET', draft_path).json()['data'] == draft
    first.call('PUT', draft_path, {'version': 0, 'data': dict(draft, question='other tab')}, expected=409)
    assert first.call('GET', draft_path).json() == saved
    # An unrelated selected run is rejected without replacing the saved draft.
    first.call('PUT', draft_path, {'version': saved['version'],
        'data': dict(draft, selected_run_id=unrelated['id'])}, expected=422)
    assert first.call('GET', draft_path).json() == saved
    passage = run['passages'][0]
    returned = first.call('GET', board + '/passage-source-context?' + urlencode(dict(params,
        run_id=run['id'], passage_id=passage['id']))).json()
    ref, block = returned['reference'], returned['block']
    assert returned['paper']['id'] == selected[0]
    assert ref['source_sha256'] == passage['source_sha256'] and ref['blocks_sha256'] == passage['blocks_sha256']
    assert block['text'][ref['start']-block['start']:ref['end']-block['start']] == ref['quote']
    assert passage['anchor']['quote'].startswith(ref['quote'])
    assert returned['passage_start'] == passage['anchor']['start'] and returned['passage_end'] == passage['anchor']['end']
    first.call('GET', board + '/passage-source-context?' + urlencode(dict(params,
        paper_id=selected[1], run_id=run['id'], passage_id=passage['id'])), expected=422)
    assert first.call('GET', cell_path).json() == cell
    assert first.call('GET', board + '/exports?format=json&history=true').body == exported
    # Zero matches are a retained empty run, never filled with unrelated passages.
    empty = first.call('POST', root + '/evidence-runs', dict(payload,
        request_id=str(uuid4()), question='zzzzunmatchableqa987654321', board_context=cell_identity)).json()
    assert not empty['passages'] and not empty['matched_passages']
    # A deliberate board revision makes the earlier search context explicit/stale.
    first.call('POST', board + '/revisions', {'request_id': str(uuid4()),
        'expected_revision_id': definition['revision_id'], 'question': 'Revised software QA question',
        'preparation_id': prep['id'], 'paper_ids': selected[:3], 'fields': fields})
    first.call('GET', context_path, expected=409)
    first.call('POST', root + '/evidence-runs', dict(payload,
        request_id=str(uuid4()), board_context=cell_identity), expected=409)
    assert first.call('GET', draft_path).json()['data'] == draft
    return {'status': 'PASS', 'requests': first.requests + stranger.requests,
        'public_fixture_only': True, 'board_scope_papers': 3, 'prepared_papers': 4,
        'cell_scope_papers': 1, 'cell_passages': len(run['passages']),
        'read_only_navigation_and_return': True, 'unsubmitted_cell_digest': digest(cell),
        'board_exports_unchanged_by_retrieval': True, 'scoped_draft_and_conflict': True,
        'unrelated_run_rejected': True, 'wrong_paper_rejected': True,
        'stale_binding_rejected': True, 'empty_results_retained': True,
        'models_and_live_calls': 'NOT_RUN', 'browser_usefulness': 'NOT_EVALUATED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--confirm-public-qa', action='store_true', required=True)
    args = parser.parse_args(); url = urlsplit(args.origin)
    if url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1'} or url.port in FORBIDDEN_PORTS or url.path not in ('', '/'):
        parser.error('Use an explicitly selected unused loopback QA origin, never the original application.')
    started = time.monotonic(); result = check(args.origin.rstrip('/'))
    result['elapsed_seconds'] = round(time.monotonic()-started, 3)
    args.report.write_text(json.dumps(result, indent=2)+'\n'); print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
