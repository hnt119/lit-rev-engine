"""Opt-in real local retrieval over two approved public abstract-only records.

Called only after explicit pinned-pack installation/checks. Uses the running
production HTTP adapter, never injected providers, generation or action tools.
No research judgments, inspected ranges, cell drafts or submissions are written.
"""
import csv
import io
import time
from urllib.parse import urlencode
from uuid import uuid4

PROFILES = {'hybrid_qwen3_06b_rrf_rerank_v1', 'hybrid_medcpt_passage_rrf_rerank_v1'}


def abstract_csv(papers):
    """Retain exact public title/abstract text; omit identifiers deliberately.

    The saved-example adapter resolves supplied corpus identifiers to full text.
    This explicit no-identifier import instead exercises retained-abstract-only
    behavior. It is not an assertion that the public full paper is unavailable.
    """
    selected = sorted((p for p in papers if 100 <= len(p['abstract']) <= 2500),
        key=lambda p: (len(p['abstract']), p['id']))[:2]
    if len(selected) != 2:
        raise RuntimeError('Two bounded approved public abstracts are required; no substitute text was generated.')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=['Title', 'Authors', 'Year', 'Abstract'])
    writer.writeheader()
    for paper in selected:
        writer.writerow({'Title': paper['title'], 'Authors': '; '.join(paper['authors']),
            'Year': paper['year'] or '', 'Abstract': paper['abstract']})
    return stream.getvalue().encode('utf-8'), selected


def exact_context(context, reference, paper_id):
    """Require exact paper/source/hash/range and reconstruct Unicode quotation."""
    assert context['paper']['id'] == paper_id
    actual = context['reference']
    for key in ('paper_id', 'source_id', 'source_version', 'source_sha256', 'blocks_sha256', 'block_id', 'start', 'end', 'quote'):
        assert actual[key] == reference[key], 'Exact retained reference binding changed.'
    assert actual['paper_id'] == paper_id
    source, block = context['source'], context['block']
    assert source['paper_id'] == block['paper_id'] == paper_id
    assert source['source_type'] == 'abstract'
    assert source['source_id'] == actual['source_id']
    assert source['version'] == actual['source_version']
    assert source['source_sha256'] == actual['source_sha256']
    assert source['blocks_sha256'] == actual['blocks_sha256']
    assert block['block_id'] == actual['block_id']
    assert block['start'] <= actual['start'] < actual['end'] <= block['end']
    assert block['text'][actual['start'] - block['start']:actual['end'] - block['start']] == actual['quote']


def run_case(browser, profile):
    if profile not in PROFILES:
        raise ValueError('Choose one existing pinned local retrieval profile.')
    started = time.monotonic()
    browser.bootstrap()
    root = '/api/v1/workspaces/' + browser.call('POST', '/api/v1/workspaces', {
        'request_id': str(uuid4()), 'mode': 'saved_example',
        'question': 'PUBLIC SOFTWARE QA: bounded abstract-only retrieval; no researcher finding'}).json()['id']
    public = browser.call('POST', root + '/searches', {'request_id': str(uuid4()),
        'query': 'approved saved public example only', 'max_results': 30}).json()
    assert public['mode'] == 'saved_example' and len(public['papers']) == 30
    payload, selected = abstract_csv(public['papers'])
    imported = browser.call('POST', root + '/imports/csv', payload,
        headers={'Content-Type': 'application/octet-stream', 'X-Request-ID': str(uuid4()),
            'X-Import-Filename': 'PUBLIC-ABSTRACT-ONLY-SOFTWARE-QA.csv'}).json()
    assert imported['ready_count'] == imported['row_count'] == 2
    rows = browser.call('GET', root + '/imports/' + imported['id'] + '/rows').json()['rows']
    collection = browser.call('POST', root + '/imports/' + imported['id'] + '/commit', {
        'request_id': str(uuid4()), 'expected_revision': imported['revision'],
        'name': 'PUBLIC ABSTRACTS ONLY — software QA, not review eligibility',
        'accepted_row_ids': [row['id'] for row in rows]}).json()
    page = browser.call('GET', root + '/collections/' + collection['id'] + '/papers').json()
    papers = page['papers']; ids = [p['id'] for p in papers]
    assert len(ids) == 2 and all(not any(p.get(k) for k in ('doi', 'pmid', 'pmcid')) for p in papers)
    assert {p['abstract'] for p in papers} == {p['abstract'] for p in selected}
    submitted = browser.call('POST', root + '/collection-preparation-jobs', {
        'request_id': str(uuid4()), 'collection_ref': collection['origin'], 'paper_ids': ids,
        'expected_source_revision': 0, 'expected_preparation_id': None}, expected=202).json()['job']
    job = submitted; deadline = time.monotonic() + 90
    while job['status'] in {'queued', 'running'} and time.monotonic() < deadline:
        time.sleep(.1)
        job = browser.call('GET', root + '/collection-preparation-jobs/' + submitted['id']).json()
    assert job['status'] == 'succeeded', 'Public abstract-only preparation did not complete.'
    prep = browser.call('GET', root + '/source-preparations/' + job['result_preparation_id']).json()
    assert len(prep['sources']) == 2 and all(s['source_type'] == 'abstract' for s in prep['sources'])
    view = browser.call('POST', root + '/boards', {'request_id': str(uuid4()),
        'schema_version': 'mvp.board-profile-request.v2', 'retrieval_profile_id': profile,
        'question': 'PUBLIC SOFTWARE QA: what does the retained abstract report?',
        'preparation_id': prep['id'], 'paper_ids': ids,
        'fields': [{'id': 'microbiome', 'label': 'Microbiome', 'subquestion': 'microbiome women participants'}]}).json()
    definition = view['definition']; board = root + '/boards/' + definition['board_id']
    cell = {'board_id': definition['board_id'], 'board_revision_id': definition['revision_id'],
        'paper_id': ids[0], 'field_id': 'microbiome'}
    scope = {'profile_id': profile, 'device': 'cpu', 'expected_preparation_id': prep['id'],
        'expected_source_revision': prep['source_revision'], 'board_context': cell}
    before = browser.call('GET', board + '/exports?format=json').json()
    assert all(c['head'] is None and c['draft_version'] == 0 for c in view['cells'])
    index_start = time.monotonic()
    indexed = browser.call('POST', root + '/hybrid-index', {**scope, 'request_id': str(uuid4())}).json()
    index_seconds = time.monotonic() - index_start
    assert indexed['state'] == 'ready'
    assert indexed['runtime']['executed_items']['document_encoder'] > 0
    search_request = {**scope, 'request_id': str(uuid4()), 'question': 'microbiome women participants', 'top_k': 5}
    search_start = time.monotonic()
    run = browser.call('POST', root + '/hybrid-runs', search_request).json()
    search_seconds = time.monotonic() - search_start
    result = run['result']
    assert run['board_context'] == cell and result['profile_id'] == profile
    usage = result['runtime']['executed_items']
    assert usage['query_encoder'] > 0 and usage['reranker'] > 0 and usage['document_encoder'] == 0
    assert len(result['source_manifest']) == 1
    assert result['source_manifest'][0]['paper_id'] == ids[0]
    assert result['source_manifest'][0]['source_type'] == 'abstract'
    assert result['candidates'] and {c['reference']['paper_id'] for c in result['candidates']} == {ids[0]}
    assert all(stage['rerank']['rank'] is not None for c in result['candidates'] for stage in c['stages'])
    candidate = result['candidates'][0]; reference = candidate['reference']
    inspected = browser.call('GET', root + '/hybrid-runs/' + run['id'] + '/candidates/' + candidate['candidate_id'] + '/context').json()
    exact_context(inspected, reference, ids[0])
    params = {'revision_id': definition['revision_id'], 'paper_id': ids[0], 'field_id': 'microbiome',
        'run_id': run['id'], 'passage_id': candidate['candidate_id']}
    returned = browser.call('GET', board + '/passage-source-context?' + urlencode(params)).json()
    exact_context(returned, reference, ids[0])
    wrong = browser.call('GET', board + '/passage-source-context?' + urlencode({**params, 'paper_id': ids[1]}), expected=422).json()
    assert wrong['error']['code'] == 'unrelated_comparison_run'
    assert browser.call('POST', root + '/hybrid-runs', search_request).json() == run
    assert browser.call('GET', root + '/hybrid-runs/' + run['id']).json() == run
    assert any(item == run for item in browser.call('GET', root + '/hybrid-exports').json()['runs'])
    after = browser.call('GET', board).json()
    assert all(c['head'] is None and c['draft_version'] == 0 for c in after['cells'])
    assert browser.call('GET', board + '/exports?format=json').json() == before
    return {'status': 'PASS', 'transport': 'actual_production_http', 'profile_id': profile, 'device': 'cpu',
        'source_scope': 'approved_public_abstracts_only_not_full_papers',
        'identifiers_deliberately_omitted_to_retain_abstract_only': True,
        'prepared_reports': 2, 'board_reports': 2, 'ranked_reports': 1,
        'index_wall_seconds': round(index_seconds, 3), 'search_wall_seconds': round(search_seconds, 3),
        'total_wall_seconds': round(time.monotonic() - started, 3),
        'returned_count': result['returned_count'], 'coverage': result['coverage'],
        'index_runtime': indexed['runtime'], 'search_runtime': result['runtime'],
        'exact_source_and_cell_context': 'PASS', 'wrong_paper_rejected': 'PASS',
        'replay_history_and_exports': 'PASS', 'no_cell_draft_inspection_support_submission_writes': True,
        'generation': 'NOT_RUN', 'live_providers': 'NOT_RUN', 'research_usefulness': 'NOT_EVALUATED'}
