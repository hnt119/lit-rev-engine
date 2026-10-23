#!/usr/bin/env python3
"""Offline public-data acceptance through a real local HTTPS ingress.

This does not deploy, provision, contact PubMed, or run a model. The target must
be an HTTPS .test hostname resolving through --connect-address to loopback.
The private state file holds two browser-cookie jars; protect/delete it like a
credential. Its report contains only counts, digests and mechanical outcomes.
Run create, stop/restart or backup/restore the service, then run verify against
the same state file. Run delete to check tombstones and removal after recovery.
"""
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
import socket
import ssl
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, HTTPSHandler, ProxyHandler, Request


P = '/api/v1'


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def private_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(value, out, indent=2, sort_keys=True); out.write('\n')


@dataclass
class Reply:
    status: int
    headers: object
    body: bytes

    def json(self):
        return json.loads(self.body)


class Browser:
    def __init__(self, origin, ca_file, saved=None):
        self.origin, self.jar = origin, CookieJar()
        self.csrf = None
        if saved:
            self.csrf = saved['csrf']
            for item in saved['cookies']:
                self.jar.set_cookie(Cookie(**item))
        context = ssl.create_default_context(cafile=ca_file)
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), HTTPCookieProcessor(self.jar))
        self.requests = 0

    def serialize(self):
        items = []
        for cookie in self.jar:
            values = dict(vars(cookie)); values['rest'] = values.pop('_rest')
            items.append(values)
        return {'csrf': self.csrf, 'cookies': items}

    def call(self, method, path, payload=None, *, expected=200, headers=None):
        values = {'Origin': self.origin, 'Accept': 'application/json'}
        if self.csrf: values['X-CSRF-Token'] = self.csrf
        body = None
        if payload is not None:
            body = payload if isinstance(payload, bytes) else json.dumps(payload, separators=(',', ':')).encode()
            values['Content-Type'] = 'application/octet-stream' if isinstance(payload, bytes) else 'application/json'
        if headers: values.update(headers)
        request = Request(self.origin + path, data=body, headers=values, method=method)
        self.requests += 1
        try:
            with self.opener.open(request, timeout=120) as response:
                reply = Reply(response.status, response.headers, response.read())
        except HTTPError as failure:
            reply = Reply(failure.code, failure.headers, failure.read())
        accepted = (expected,) if isinstance(expected, int) else expected
        if reply.status not in accepted:
            # No payload/URL containing source content or cookie is printed.
            try: code = reply.json().get('error', reply.json().get('detail', {})).get('code')
            except (ValueError, AttributeError): code = None
            raise AssertionError(f'{method} route returned {reply.status}; expected {accepted}; error code={code!r}')
        if path.startswith(P) and reply.status == 200:
            assert 'no-store' in reply.headers.get('Cache-Control', ''), 'Research response may not be publicly cached'
        return reply

    def login(self, invitation):
        self.call('POST', P + '/admission/login', {'code': invitation})
        status = self.call('GET', P + '/admission/status').json()
        assert status['mode'] == 'hosted' and status['admitted'] is True
        session = self.call('GET', P + '/session')
        self.csrf = session.json()['csrf_token']
        cookies = session.headers.get_all('Set-Cookie') or []
        assert any('__Host-litrev_session=' in value and 'Secure' in value and 'HttpOnly' in value
                   and 'SameSite=strict' in value and 'Domain=' not in value for value in cookies)


def root_for(state):
    return P + '/workspaces/' + state['workspace_id']


def board_for(state):
    return root_for(state) + '/boards/' + state['board_id']


def privacy_checks(first, second, state):
    root, board = root_for(state), board_for(state)
    paper = state['paper_ids'][0]
    paths = [root, root + '/searches/' + state['search_id'] + '/papers',
             root + '/source-preparations/' + state['preparation_id'], root + '/drafts/discover',
             root + '/exports?format=json', root + '/maps/' + state['map_id'],
             board, board + '/exports?format=csv', board + '/exports?format=json&history=true',
             board + '/drafts/' + paper + '/field-0',
             board + '/sources/' + state['source_id'] + '/blocks']
    for path in paths:
        second.call('GET', path, expected=404)
    second.call('PUT', root + '/drafts/discover', {'version': 0, 'data': {}}, expected=404)
    second.call('DELETE', root, expected=404)
    first.call('PUT', root + '/drafts/discover', {'version': 0, 'data': {}},
               headers={'X-CSRF-Token': 'invalid'}, expected=403)
    first.call('PUT', root + '/drafts/discover', {'version': 0, 'data': {}},
               headers={'Origin': 'https://attacker.example'}, expected=403)
    first.call('GET', root, headers={'Host': 'attacker.example'}, expected=403)
    assert second.call('GET', P + '/workspaces').json() == {'workspaces': []}
    return len(paths) + 5


def create(first, second):
    workspace = first.call('POST', P + '/workspaces', {'request_id': 'hosted-smoke-workspace',
        'mode': 'saved_example', 'question': 'SOFTWARE HOSTED SMOKE: no scientific assessment'}).json()
    state = {'workspace_id': workspace['id']}; root = root_for(state)
    preview = first.call('POST', root + '/searches', {'request_id': 'hosted-smoke-search',
        'query': 'public retained example only', 'max_results': 30}).json()
    ids = [paper['id'] for paper in preview['papers']]
    assert len(ids) == len(set(ids)) == 30 and preview['mode'] == 'saved_example'
    listing = first.call('GET', root + '/maps?search_id=' + preview['id']).json()
    assert not listing['jobs'] and len(listing['maps']) == 1
    map_id = listing['maps'][0]['map_id']; map_path = root + '/maps/' + map_id
    mapped = first.call('GET', map_path).json()
    assert mapped['counts']['map_points'] == 30
    job = first.call('POST', root + '/preparation-jobs', {'request_id': 'hosted-smoke-preparation',
        'search_id': preview['id'], 'paper_ids': ids, 'expected_source_revision': 0,
        'expected_preparation_id': None}, expected=202).json()['job']
    deadline = time.monotonic() + 150
    while job['status'] in {'queued', 'running'}:
        assert time.monotonic() < deadline, 'Public offline preparation did not finish in bounded runtime'
        time.sleep(.25)
        job = first.call('GET', root + '/preparation-jobs/' + job['id']).json()
    assert job['status'] == 'succeeded', job['status']
    prep = first.call('GET', root + '/source-preparations/' + job['result_preparation_id']).json()
    assert prep['selected_paper_ids'] == ids and len(prep['sources']) == 30
    assert all(source['source_type'] == 'full_text' for source in prep['sources'])
    fields = [{'id': f'field-{n}', 'label': f'Software field {n}',
               'subquestion': f'SOFTWARE TEST microbiome diet question {n}'} for n in range(6)]
    view = first.call('POST', root + '/boards', {'request_id': 'hosted-smoke-board',
        'preparation_id': prep['id'], 'paper_ids': ids, 'question': workspace['question'], 'fields': fields}).json()
    assert len(view['cells']) == 180
    definition = view['definition']; board = root + '/boards/' + definition['board_id']
    revision = definition['revision_id']; refs = {}
    for source in definition['sources']:
        inspected = first.call('GET', board + '/sources/' + source['source_id'] + '/blocks').json()
        anchor = inspected['blocks'][0]['reference']
        anchor = {key: anchor[key] for key in ('source_id', 'source_version', 'source_sha256',
                    'blocks_sha256', 'block_id', 'start', 'end')}
        anchor['end'] = min(anchor['end'], anchor['start'] + 128)
        refs[source['paper_id']] = anchor
    heads = {}
    for index, paper_id in enumerate(ids):
        for field in fields:
            draft = first.call('PUT', board + '/drafts/' + paper_id + '/' + field['id'], {
                'expected_revision_id': revision, 'version': 0, 'expected_cell_head_id': None,
                'data': {'value': f'SOFTWARE TEST value {index}/{field["id"]}',
                    'references': [refs[paper_id]], 'inspected_ranges': [refs[paper_id]],
                    'semantic_assessment': 'unassessed', 'scope_result': 'value_found',
                    'reason': 'Synthetic software fixture, no human assessment.'}}).json()
            saved = first.call('POST', board + '/cell-revisions', {'request_id': f'hosted-cell-{index}-{field["id"]}',
                'expected_revision_id': revision, 'paper_id': paper_id, 'field_id': field['id'],
                'draft_version': draft['version'], 'supersedes_id': None}).json()
            assert saved['semantic_assessment'] == 'unassessed'
            heads[(paper_id, field['id'])] = saved['id']
    # One explicit revision and an independent pending draft survive restart.
    paper_id = ids[0]; field_id = fields[0]['id']; head = heads[(paper_id, field_id)]
    changed = first.call('PUT', board + '/drafts/' + paper_id + '/' + field_id, {
        'expected_revision_id': revision, 'version': 0, 'expected_cell_head_id': head,
        'data': {'value': 'SOFTWARE TEST explicit revision', 'semantic_assessment': 'unassessed'}}).json()
    revised = first.call('POST', board + '/cell-revisions', {'request_id': 'hosted-cell-revision',
        'expected_revision_id': revision, 'paper_id': paper_id, 'field_id': field_id,
        'draft_version': changed['version'], 'supersedes_id': head}).json()
    assert revised['supersedes_id'] == head
    first.call('PUT', root + '/drafts/discover', {'version': 0,
        'data': {'question': 'SOFTWARE TEST durable UI draft', 'query': 'not a live query', 'top_k': 30}})
    pending = first.call('PUT', board + '/drafts/' + ids[1] + '/field-0', {
        'expected_revision_id': revision, 'version': 0, 'expected_cell_head_id': heads[(ids[1], 'field-0')],
        'data': {'value': 'SOFTWARE TEST pending cell draft'}}).json()
    run = first.call('POST', root + '/evidence-runs', {'request_id': 'hosted-smoke-passages-30',
        'question': 'microbiome diversity', 'expected_preparation_id': prep['id'],
        'expected_source_revision': prep['source_revision'], 'top_k': 30}).json()
    assert len(run['passages']) == 30 and run['parameters']['top_k'] == 30
    state.update(search_id=preview['id'], paper_ids=ids, preparation_id=prep['id'],
        job_id=job['id'], map_id=map_id, map_digest=digest(mapped), board_id=definition['board_id'],
        revision_id=revision, source_id=definition['sources'][0]['source_id'],
        pending_draft_digest=digest(pending), run_id=run['id'])
    state['privacy_denials'] = privacy_checks(first, second, state)
    audit = first.call('GET', board + '/exports?format=json&history=true')
    exported = audit.json()
    assert len(exported['table']) == 180 and len(exported['cell_revisions']) == 181
    state['board_export_digest'] = digest(exported)
    state['board_export_bytes'] = len(audit.body)
    csv_reply = first.call('GET', board + '/exports?format=csv')
    assert len(list(csv.DictReader(io.StringIO(csv_reply.body.decode())))) == 180
    assert 'attachment' in csv_reply.headers.get('Content-Disposition', '')
    return state


def verify(first, second, state):
    root, board = root_for(state), board_for(state)
    assert first.call('GET', '/healthz').json() == {'status': 'ok'}
    landing = first.call('GET', '/?page=comparison&workspace=' + state['workspace_id'] + '&board=' + state['board_id'])
    assert b'HOSTED BETA' in landing.body and b'Invitation code' in landing.body, 'Direct navigation must render the hosted admission shell'
    capabilities = first.call('GET', P + '/capabilities').json()
    assert capabilities['live_available'] is False and capabilities['map']['ready'] is False
    session = first.call('GET', P + '/session').json()
    assert session['csrf_token'] == first.csrf
    assert first.call('GET', root).json()['id'] == state['workspace_id']
    assert digest(first.call('GET', root + '/maps/' + state['map_id']).json()) == state['map_digest']
    neighbors = first.call('GET', root + '/maps/' + state['map_id'] + '/neighbors/' + state['paper_ids'][0]).json()
    assert neighbors['map_id'] == state['map_id'] and neighbors['paper_id'] == state['paper_ids'][0]
    assert len(neighbors['neighbors']) == 5 and state['paper_ids'][0] not in [item['paper_id'] for item in neighbors['neighbors']]
    assert digest(first.call('GET', root + '/maps/' + state['map_id']).json()) == state['map_digest']
    view = first.call('GET', board).json()
    assert len(view['cells']) == 180 and all(cell['head'] for cell in view['cells'])
    assert digest(first.call('GET', board + '/exports?format=json&history=true').json()) == state['board_export_digest']
    assert first.call('GET', board + '/cells/' + state['paper_ids'][0] + '/field-0/history').json()['total'] == 2
    pending = first.call('GET', board + '/drafts/' + state['paper_ids'][1] + '/field-0').json()
    assert digest(pending) == state['pending_draft_digest']
    assert first.call('GET', root + '/drafts/discover').json()['data']['top_k'] == 30
    assert first.call('GET', root + '/preparation-jobs/' + state['job_id']).json()['status'] == 'succeeded'
    assert len(first.call('GET', root + '/runs/' + state['run_id']).json()['run']['passages']) == 30
    return privacy_checks(first, second, state)


def intake_checks(first, second, state):
    """Small public/synthetic raw upload and size/media denial; no resolution."""
    root = root_for(state)
    headers = {'Content-Type': 'application/octet-stream', 'X-Request-ID': 'hosted-smoke-csv',
               'X-Import-Filename': 'public-software-test.csv'}
    uploaded = first.call('POST', root + '/imports/csv',
        b'title,abstract\nSOFTWARE TEST PUBLIC INGESTION,Synthetic test metadata with no scientific claim\n',
        headers=headers).json()
    second.call('GET', root + '/imports/' + uploaded['id'], expected=404)
    before = first.call('GET', root + '/imports').json()
    first.call('POST', root + '/imports/csv', b'x' * (5 * 1024 * 1024 + 1),
        headers={**headers, 'X-Request-ID': 'hosted-smoke-oversized'}, expected=413)
    first.call('POST', root + '/imports/csv', b'not a citation file',
        headers={**headers, 'X-Request-ID': 'hosted-smoke-invalid-media', 'Content-Type': 'text/html'}, expected=415)
    assert first.call('GET', root + '/imports').json() == before
    return {'small_raw_csv': 'PASS', 'other_session': 404, 'five_mib_plus_one': 413,
            'invalid_media': 415, 'rejected_imports_recorded': 0, 'provider_resolution_calls': 0}


def slow_body_check(origin, ca_file):
    """Anonymous body arrives over real TLS more slowly than the 15 s bound."""
    parsed = urlsplit(origin)
    connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
        timeout=40, context=ssl.create_default_context(cafile=ca_file))
    started = time.monotonic()
    try:
        connection.putrequest('POST', P + '/admission/login')
        connection.putheader('Origin', origin)
        connection.putheader('Content-Type', 'application/json')
        connection.putheader('Content-Length', '2')
        connection.endheaders()
        connection.send(b'{')
        time.sleep(16)
        try:
            connection.send(b'}')
        except BrokenPipeError:
            pass
        response = connection.getresponse(); response.read()
        assert response.status == 408, f'Slow unauthenticated body returned {response.status}, expected 408'
        return {'status': response.status, 'elapsed_seconds': round(time.monotonic() - started, 3),
                'authenticated': False, 'declared_bytes': 2, 'second_byte_delayed_seconds': 16}
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('create', 'verify', 'delete'))
    parser.add_argument('--origin', required=True)
    parser.add_argument('--connect-address', default='127.0.0.1')
    parser.add_argument('--ca-file', required=True)
    parser.add_argument('--invite-file', help='Required for create; never paste the code into CLI args.')
    parser.add_argument('--state-file', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--check-imports', action='store_true', help='Additional synthetic raw-upload checks in verify phase.')
    parser.add_argument('--check-slow-body', action='store_true', help='Additional 16-second anonymous request-body deadline check.')
    args = parser.parse_args(); parsed = urlsplit(args.origin)
    if (parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.test')
            or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password
            or args.connect_address not in {'127.0.0.1', '::1'}):
        parser.error('Use one exact HTTPS .test origin, a loopback connection and the matching test CA.')
    real_getaddrinfo = socket.getaddrinfo
    def loopback_only(host, port, *values, **keywords):
        if host != parsed.hostname:
            raise AssertionError('HTTPS smoke attempted an unexpected network destination')
        return real_getaddrinfo(args.connect_address, port, *values, **keywords)
    socket.getaddrinfo = loopback_only
    started = time.monotonic(); report = {'phase': args.phase, 'completed': False,
        'boundary': 'Real local HTTPS to production processes/container; public retained example and synthetic unassessed cells only',
        'live_provider_calls': 0, 'model_calls': 0, 'scientific_or_human_validation': False}
    try:
        state = None if args.phase == 'create' else json.loads(Path(args.state_file).read_text())
        first = Browser(args.origin, args.ca_file, state['first'] if state else None)
        second = Browser(args.origin, args.ca_file, state['second'] if state else None)
        if args.phase == 'create':
            assert args.invite_file, '--invite-file is required for create'
            anonymous = Browser(args.origin, args.ca_file)
            for path in [P + '/session', P + '/capabilities', P + '/workspaces']:
                anonymous.call('GET', path, expected=401)
            anonymous.call('POST', P + '/admission/login', {'code': 'WRONG SOFTWARE TEST CODE 0123456789'}, expected=401)
            invitation = Path(args.invite_file).read_text().strip()
            first.login(invitation); second.login(invitation)
            state = create(first, second)
        elif args.phase == 'verify':
            state['privacy_denials_after_restart_or_restore'] = verify(first, second, state)
            if args.check_imports:
                report['intake'] = intake_checks(first, second, state)
            if args.check_slow_body:
                report['slow_body'] = slow_body_check(args.origin, args.ca_file)
        else:
            first.call('DELETE', root_for(state))
            for path in [root_for(state), board_for(state), root_for(state) + '/maps/' + state['map_id'],
                         root_for(state) + '/preparation-jobs/' + state['job_id']]:
                first.call('GET', path, expected=404)
            assert first.call('GET', P + '/workspaces').json() == {'workspaces': []}
            state['deleted'] = True
        state['first'], state['second'] = first.serialize(), second.serialize()
        private_json(args.state_file, state)
        report.update(completed=True, papers=30, fields=6, cells=180, cell_revisions=181,
            saved_map_points=30, requested_passages=30, returned_passages=30,
            research_requests=first.requests + second.requests,
            privacy_denials=state['privacy_denials'], board_export_bytes=state['board_export_bytes'])
    finally:
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        private_json(args.report, report)
        socket.getaddrinfo = real_getaddrinfo
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
