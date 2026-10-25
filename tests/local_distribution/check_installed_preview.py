#!/usr/bin/env python3
"""Explicit installed-preview acceptance against NEW public/synthetic QA only.

This is an opt-in API check, not a human/browser usefulness evaluation. It never
starts/stops services, loads model weights, or sends a literature-provider call.
Keep --qa-root outside the installed application; it holds private test cookies.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import http.client
from http.cookiejar import Cookie, CookieJar
import io
import json
import os
from pathlib import Path
import stat
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler, ProxyHandler, Request
from uuid import uuid4

P = '/api/v1'
FORBIDDEN_PORTS = {3000, 3005, 8765, 8769}
REFERENCE_KEYS = ('source_id', 'source_version', 'source_sha256', 'blocks_sha256', 'block_id', 'start', 'end')


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise AssertionError('The local acceptance check refuses redirects.')


@dataclass
class Reply:
    status: int
    headers: object
    body: bytes

    def json(self):
        return json.loads(self.body)


class Browser:
    def __init__(self, origin, saved=None):
        self.origin, self.jar, self.csrf, self.requests = origin, CookieJar(), None, 0
        if saved:
            self.csrf = saved['csrf']
            for item in saved['cookies']:
                self.jar.set_cookie(Cookie(**item))
        self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPCookieProcessor(self.jar))

    def saved(self):
        items = []
        for cookie in self.jar:
            item = dict(cookie.__dict__)
            item['rest'] = item.pop('_rest')
            items.append(item)
        return {'csrf': self.csrf, 'cookies': items}

    def call(self, method, path, value=None, *, expected=200, headers=None, base=None):
        assert path.startswith('/') and not path.startswith('//')
        body = None if value is None else value if isinstance(value, bytes) else json.dumps(value).encode()
        request_headers = {'Origin': self.origin}
        if body is not None:
            request_headers['Content-Type'] = 'application/json'
        if self.csrf:
            request_headers['X-CSRF-Token'] = self.csrf
        request_headers.update(headers or {})
        request = Request((base or self.origin) + path, data=body, method=method, headers=request_headers)
        try:
            response = self.opener.open(request, timeout=60)
        except HTTPError as error:
            response = error
        with response:
            reply = Reply(response.status, response.headers, response.read())
        self.requests += 1
        assert reply.status == expected, (method, path, reply.status, expected, reply.body[:300])
        return reply

    def bootstrap(self):
        response = self.call('GET', P + '/session')
        self.csrf = response.json()['csrf_token']
        header = response.headers.get('Set-Cookie', '')
        assert 'HttpOnly' in header and 'SameSite=strict' in header and 'Path=/' in header
        assert 'Max-Age=' in header and 'Domain=' not in header and 'Secure' not in header
        return response


def roots(state):
    root = P + '/workspaces/' + state['workspace_id']
    return root, root + '/boards/' + state['board_id']


def access_checks(first, second, state, api):
    root, board = roots(state)
    paths = [root, root + '/drafts/discover', root + '/exports?format=json',
             root + '/maps/' + state['map_id'], board, board + '/exports?format=json',
             board + '/drafts/' + state['paper_ids'][0] + '/population',
             board + '/references/' + state['reference_id'] + '/context']
    for path in paths:
        second.call('GET', path, expected=404)
    second.call('PUT', root + '/drafts/discover', {'version': 0, 'data': {}}, expected=404)
    first.call('PUT', root + '/drafts/discover', {'version': 1, 'data': {}},
               headers={'X-CSRF-Token': 'wrong-synthetic-token'}, expected=403)
    first.call('GET', P + '/capabilities', base=api, headers={'Host': 'wrong.example.test'}, expected=403)
    first.call('GET', P + '/capabilities', base=api, headers={'Origin': 'http://wrong.example.test'}, expected=403)
    # Read a deliberate early denial without urllib sending a megabyte after
    # the server has already closed its side of the upload connection.
    destination = urlsplit(first.origin)
    request = Request(first.origin + P + '/workspaces')
    first.jar.add_cookie_header(request)
    connection = http.client.HTTPConnection(destination.hostname, destination.port, timeout=5)
    try:
        connection.putrequest('POST', P + '/workspaces')
        connection.putheader('Origin', first.origin)
        connection.putheader('X-CSRF-Token', first.csrf)
        connection.putheader('Cookie', request.get_header('Cookie', ''))
        connection.putheader('Content-Type', 'application/json')
        connection.putheader('Content-Length', str(1024 * 1024 + 1))
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 413
        response.read(1024)
        first.requests += 1
    finally:
        connection.close()
    return len(paths) + 5


def create(first, second, api):
    first.bootstrap(); second.bootstrap()
    assert first.call('GET', P + '/admission/status').json() == {'mode': 'local', 'admitted': True}
    capabilities = first.call('GET', P + '/capabilities').json()
    assert capabilities['live_available'] is False and capabilities['map']['ready'] is False
    question = 'PUBLIC SOFTWARE QA: retained microbiome papers; no scientific assessment'
    workspace = first.call('POST', P + '/workspaces', {'request_id': str(uuid4()),
        'mode': 'saved_example', 'question': question}).json()
    state = {'workspace_id': workspace['id']}; root = P + '/workspaces/' + workspace['id']
    preview = first.call('POST', root + '/searches', {'request_id': str(uuid4()),
        'query': 'public retained example only', 'max_results': 30}).json()
    assert len(preview['papers']) == 30 and preview['mode'] == 'saved_example'
    ids = [paper['id'] for paper in preview['papers'][:3]]
    maps = first.call('GET', root + '/maps?search_id=' + preview['id']).json()
    assert not maps['jobs'] and len(maps['maps']) == 1
    map_id = maps['maps'][0]['map_id']
    mapped = first.call('GET', root + '/maps/' + map_id).json()
    assert mapped['counts']['map_points'] == 30
    prep = first.call('POST', root + '/source-preparations', {'request_id': str(uuid4()),
        'search_id': preview['id'], 'paper_ids': ids}).json()
    assert prep['selected_paper_ids'] == ids and len(prep['sources']) == 3
    fields = [{'id': 'population', 'label': 'Population', 'subquestion': 'women population'},
              {'id': 'diet', 'label': 'Diet', 'subquestion': 'diet food questionnaire'},
              {'id': 'fertility', 'label': 'Fertility', 'subquestion': 'fertility ovarian reserve'}]
    view = first.call('POST', root + '/boards', {'request_id': str(uuid4()), 'question': question,
        'preparation_id': prep['id'], 'paper_ids': ids, 'fields': fields}).json()
    assert len(view['cells']) == 9
    board = root + '/boards/' + view['definition']['board_id']; rev = view['definition']['revision_id']
    heads, inspected_count, candidate_count, reference_id = {}, 0, 0, None
    for index, paper in enumerate(ids):
        for field in fields:
            found = first.call('POST', board + '/candidates', {'request_id': str(uuid4()),
                'expected_revision_id': rev, 'paper_id': paper, 'field_id': field['id'], 'top_k': 3}).json()
            candidate_count += len(found['candidates']); refs = []
            if found['candidates']:
                ref = found['candidates'][0]['reference']
                context = first.call('GET', board + '/references/' + ref['id'] + '/context').json()
                chunk = context['block']
                assert chunk['text'][ref['start'] - chunk['start']:ref['end'] - chunk['start']] == ref['quote']
                assert context['reference']['source_sha256'] == ref['source_sha256']
                refs = [{key: ref[key] for key in REFERENCE_KEYS}]
                reference_id = reference_id or ref['id']; inspected_count += 1
            data = {'value': f'SOFTWARE QA unassessed value {index}/{field["id"]}' if refs else None,
                'references': refs, 'inspected_ranges': refs, 'semantic_assessment': 'unassessed',
                'scope_result': 'not_assessed', 'missing_information': '' if refs else 'No candidate returned in this bounded retrieval; no whole-paper absence claim.',
                'reason': 'Mechanical software fixture, not researcher support judgment.'}
            saved = first.call('PUT', board + '/drafts/' + paper + '/' + field['id'],
                {'expected_revision_id': rev, 'version': 0, 'expected_cell_head_id': None, 'data': data}).json()
            head = first.call('POST', board + '/cell-revisions', {'request_id': str(uuid4()),
                'expected_revision_id': rev, 'paper_id': paper, 'field_id': field['id'],
                'draft_version': saved['version']}).json()
            assert head['semantic_assessment'] == 'unassessed'
            heads[(paper, field['id'])] = head['id']
    assert reference_id is not None
    # Explicit revision and a separate unsent draft exercise distinct lifecycles.
    paper, field = ids[0], 'population'; old = heads[(paper, field)]
    changed = first.call('PUT', board + '/drafts/' + paper + '/' + field,
        {'expected_revision_id': rev, 'version': 0, 'expected_cell_head_id': old,
         'data': {'value': 'SOFTWARE QA explicit revision', 'semantic_assessment': 'unassessed'}}).json()
    revised = first.call('POST', board + '/cell-revisions', {'request_id': str(uuid4()),
        'expected_revision_id': rev, 'paper_id': paper, 'field_id': field,
        'draft_version': changed['version'], 'supersedes_id': old}).json()
    assert revised['supersedes_id'] == old
    pending = first.call('PUT', board + '/drafts/' + ids[1] + '/diet',
        {'expected_revision_id': rev, 'version': 0, 'expected_cell_head_id': heads[(ids[1], 'diet')],
         'data': {'value': 'SOFTWARE QA durable pending cell draft'}}).json()
    ui = first.call('PUT', root + '/drafts/discover', {'version': 0,
        'data': {'question': 'SOFTWARE QA durable question', 'query': 'public fixture', 'top_k': 5}}).json()
    run = first.call('POST', root + '/evidence-runs', {'request_id': str(uuid4()),
        'question': 'microbiome diversity', 'expected_preparation_id': prep['id'],
        'expected_source_revision': prep['source_revision'], 'top_k': 5}).json()
    assert run['passages'] and len(run['passages']) <= 5
    passage = run['passages'][0]
    context = first.call('GET', root + '/runs/' + run['id'] + '/passages/' + passage['id'] + '/context').json()
    assert context['block']['text'][passage['anchor']['start']:passage['anchor']['end']] == passage['anchor']['quote']
    exported = first.call('GET', board + '/exports?format=json&history=true').json()
    assert len(exported['table']) == 9 and len(exported['cell_revisions']) == 10
    assert all(item['semantic_assessment'] == 'unassessed' for item in exported['cell_revisions'])
    csv_export = first.call('GET', board + '/exports?format=csv')
    assert len(list(csv.DictReader(io.StringIO(csv_export.body.decode())))) == 9
    state.update(search_id=preview['id'], paper_ids=ids, preparation_id=prep['id'], map_id=map_id,
        map_digest=digest(mapped), board_id=view['definition']['board_id'], revision_id=rev,
        reference_id=reference_id, pending_digest=digest(pending), ui_digest=digest(ui),
        board_export_digest=digest(exported), csv_digest=digest(csv_export.body), run_id=run['id'],
        candidates_returned=candidate_count, exact_candidate_inspections=inspected_count, lexical_passages=len(run['passages']), origin=first.origin)
    state['privacy_denials'] = access_checks(first, second, state, api)
    return state


def verify(first, second, state, api):
    root, board = roots(state)
    assert urlsplit(state['origin']).hostname == urlsplit(first.origin).hostname, 'Use the same browser hostname; a workspace ID is not access recovery.'
    old = first.csrf; first.bootstrap(); assert first.csrf == old
    capabilities = first.call('GET', P + '/capabilities').json()
    assert capabilities['live_available'] is False and capabilities['map']['ready'] is False
    assert first.call('GET', P + '/admission/status').json() == {'mode': 'local', 'admitted': True}
    assert first.call('GET', root).json()['id'] == state['workspace_id']
    assert digest(first.call('GET', root + '/maps/' + state['map_id']).json()) == state['map_digest']
    neighbors = first.call('GET', root + '/maps/' + state['map_id'] + '/neighbors/' + state['paper_ids'][0]).json()
    assert len(neighbors['neighbors']) == 5
    assert digest(first.call('GET', board + '/exports?format=json&history=true').json()) == state['board_export_digest']
    assert digest(first.call('GET', board + '/exports?format=csv').body) == state['csv_digest']
    assert first.call('GET', board + '/cells/' + state['paper_ids'][0] + '/population/history').json()['total'] == 2
    assert digest(first.call('GET', board + '/drafts/' + state['paper_ids'][1] + '/diet').json()) == state['pending_digest']
    assert digest(first.call('GET', root + '/drafts/discover').json()) == state['ui_digest']
    assert first.call('GET', root + '/runs/' + state['run_id']).json()['run']['passages']
    context = first.call('GET', board + '/references/' + state['reference_id'] + '/context').json()
    ref, chunk = context['reference'], context['block']
    assert chunk['text'][ref['start'] - chunk['start']:ref['end'] - chunk['start']] == ref['quote']
    assert context['source']['source_sha256'] == ref['source_sha256']
    state['privacy_denials'] = access_checks(first, second, state, api)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['create', 'verify'])
    parser.add_argument('--origin', required=True)
    parser.add_argument('--api-origin', required=True)
    parser.add_argument('--qa-root', type=Path, required=True)
    parser.add_argument('--confirm-public-qa', action='store_true', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    for value in (args.origin, args.api_origin):
        url = urlsplit(value)
        if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost'} or url.port in FORBIDDEN_PORTS or
                url.port is None or not 1024 <= url.port <= 65535 or url.path or url.query or url.fragment or url.username or url.password):
            parser.error('Use explicitly supplied fresh QA loopback ports, never original3000/3005/8765/8769.')
    qa = args.qa_root.resolve()
    if not qa.is_relative_to(Path('/private/tmp')) or qa == Path('/private/tmp'):
        parser.error('Private QA cookies must stay in a new /private/tmp directory outside the application.')
    qa.mkdir(mode=0o700, parents=True, exist_ok=True); os.chmod(qa, 0o700)
    path = qa/'installed-preview-state.json'
    if args.phase == 'create' and path.exists():
        parser.error('Create requires a fresh state file; use verify after restart/replacement.')
    started = time.monotonic()
    state = None if args.phase == 'create' else json.loads(path.read_text())
    first, second = Browser(args.origin, state['first'] if state else None), Browser(args.origin, state['second'] if state else None)
    report = {'phase': args.phase, 'status': 'FAIL', 'live_provider_calls': 0, 'model_calls': 0,
              'actual_browser': 'NOT_RUN_BY_THIS_API_CHECK', 'scientific_or_human_usefulness_validation': False,
              'size_probe': 'Declared1MiB+1 rejected before upload with413'}
    try:
        state = create(first, second, args.api_origin) if args.phase == 'create' else verify(first, second, state, args.api_origin)
        state.update(first=first.saved(), second=second.saved())
        private_json(path, state)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        report.update(status='PASS', saved_public_papers=30, prepared_papers=3, fields=3, cells=9,
            submitted_revisions=10, saved_map_points=30, lexical_passages=state['lexical_passages'],
            candidates_returned=state['candidates_returned'], exact_candidate_inspections=state['exact_candidate_inspections'],
            privacy_denials=state['privacy_denials'], requests=first.requests+second.requests)
    finally:
        report['seconds'] = round(time.monotonic()-started, 3)
        private_json(args.report, report)
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
