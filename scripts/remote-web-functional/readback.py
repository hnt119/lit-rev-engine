#!/usr/bin/env python3
"""Independent public-fixture audit readback; emits fixed status only.

Requires the exact source tree and real browser downloads supplied by the caller.
Independent of the board export serializer; source reconstruction uses the app public-fixture adapter.
"""
import hashlib
import csv
import io
import json
import re
from datetime import datetime, timezone
import sys
from pathlib import Path

EXPECTED = 'SOFTWARE QA ONLY: public-source workflow check'
PMID = '42051515'
FIELD = 'population'
CSV_FIELDS = ('schema_version board_id board_revision_id search_id search_sha256 question preparation_id source_manifest_sha256 '
              'paper_id paper_title pmid doi authors year source_id source_type source_status source_sha256 blocks_sha256 '
              'field_id field_revision_id field_label field_subquestion cell_revision_id supersedes_id value semantic_assessment '
              'scope_result reference_integrity missing_information reason references inspected_ranges freshness review_state producer created_at').split()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def strict_loads(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def check_csv(raw, audit):
    # Parse rather than call the application's serializer. Reject duplicate,
    # missing, extra, malformed, reordered or ragged fields/rows.
    text = raw.decode('utf-8', errors='strict')
    rows = list(csv.reader(io.StringIO(text, newline=''), strict=True))
    assert rows and rows[0] == CSV_FIELDS and len(set(rows[0])) == len(rows[0])
    assert len(rows) == 10 and all(len(row) == len(CSV_FIELDS) for row in rows[1:])
    def encoded(value):
        if value is None:
            return ''
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        value = str(value)
        return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
    for cells, row in zip(rows[1:], audit['table']):
        assert set(row) == set(CSV_FIELDS)
        assert cells == [encoded(row[field]) for field in CSV_FIELDS]
        for field in ('authors', 'references', 'inspected_ranges'):
            assert strict_loads(cells[CSV_FIELDS.index(field)]) == row[field]


def public_audit(value, papers, provider):
    """Reject all non-contract or non-fixture audit content before disclosure."""
    from src.mvp.board_contracts import BoardRevision, BoardCellRevision
    from src.mvp.adapters.retrieval import LexicalRetrieval
    from src.mvp.contracts import digest
    def uid(x):
        assert isinstance(x,str) and re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",x)
    def hex64(x):
        assert isinstance(x,str) and re.fullmatch(r"[0-9a-f]{64}",x)
    def timestamp(x):
        assert isinstance(x,str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?\+00:00",x)
        assert datetime.fromisoformat(x).tzinfo == timezone.utc
    assert set(value)=={'schema_version','table_schema_version','board_id','selected_revision_id','freshness','definitions','table','cell_revisions','candidate_runs','history_included','offset_convention','review_state'}
    assert value['schema_version']=='mvp.board-audit.v1' and value['table_schema_version']=='mvp.board-table.v1'
    assert value['freshness']=='current' and value['history_included'] is False and value['candidate_runs']==[]
    assert value['offset_convention']=='half-open-unicode-codepoints' and value['review_state']=='single_human_self_declared_not_independently_verified'
    assert len(value['definitions'])==1 and len(value['cell_revisions'])==1 and len(value['table'])==9
    d=value['definitions'][0]; c=value['cell_revisions'][0]
    # Pydantic forbids extra fields at each typed model boundary; equality also
    # rejects omitted defaults and implicit coercion. Dict-valued fields are
    # checked separately below against source-derived, closed values.
    assert BoardRevision.model_validate(d).model_dump(mode='json')==d
    assert BoardCellRevision.model_validate(c).model_dump(mode='json')==c
    for k in ('board_id','revision_id','workspace_id','search_id','preparation_id'): uid(d[k])
    for k in ('search_sha256','question_sha256','source_manifest_sha256','retrieval_profile_sha256'): hex64(d[k])
    timestamp(d['created_at']); assert d['parent_revision_id'] is None
    assert d['board_id']==value['board_id'] and d['revision_id']==value['selected_revision_id']
    assert d['question']=='Remote functional software QA' and d['question_sha256']==digest(d['question'])
    assert type(d['source_revision']) is int and d['source_revision'] == 1
    profile={'method':LexicalRetrieval.method,'method_version':'lit-rev-engine.project-retrieval.v3.bm25_context_blocks','parameters':LexicalRetrieval.parameters,'scope':'one-paper-one-field','candidate_text_limit':1200}
    assert d['retrieval_profile']==profile and d['retrieval_profile_sha256']==digest(profile)
    expected_fields=[('population','Population','What population, location, sample size and age range were studied?'),('design','Study design','What study design and methods were used?'),('exposure','Exposure or intervention','What dietary or other exposures or interventions were measured?')]
    assert len(d['fields'])==3
    for f,(i,label,query) in zip(d['fields'],expected_fields):
        assert set(f)=={'id','label','subquestion','revision_id'} and (f['id'],f['label'],f['subquestion'])==(i,label,query);uid(f['revision_id'])
    fixtures={p.pmid:p for p in papers}
    assert {p['pmid'] for p in d['papers']}=={'42051515','42683105','42196995'} and len(d['papers'])==3
    assert len(d['sources'])==3 and d['paper_ids']==[p['id'] for p in d['papers']]
    prepared={}
    for paper,binding in zip(d['papers'],d['sources']):
        expected=fixtures[paper['pmid']].model_dump(mode='json',exclude={'abstract'})
        assert paper==expected and binding['paper_id']==paper['id']
        original=provider.prepare(fixtures[paper['pmid']]);prepared[paper['id']]=original
        uid(binding['source_id'])
        assert binding=={'source_id':binding['source_id'],'paper_id':paper['id'],'version':original.version,'source_sha256':original.source_sha256,'blocks_sha256':original.blocks_sha256,'parser_id':original.parser_id,'source_type':original.source_type,'status':original.status,'block_count':len(original.blocks)}
    manifest=[{k:b[k] for k in ('source_id','paper_id','version','source_sha256','blocks_sha256','parser_id','source_type')} for b in d['sources']]
    assert d['source_manifest_sha256']==digest(manifest)
    for k in ('id','board_id','board_revision_id','field_revision_id'): uid(c[k])
    timestamp(c['created_at'])
    assert c['schema_version']=='mvp.board-cell.v1' and c['board_id']==d['board_id'] and c['board_revision_id']==d['revision_id']
    assert c['paper_id']==fixtures[PMID].id and c['field_id']=='population' and c['field_revision_id']==d['fields'][0]['revision_id']
    assert c['supersedes_id'] is None and c['producer']=='manual' and c['value']==EXPECTED
    assert c['reason']=='Software fixture, not participant judgment or scientific support.' and c['missing_information']==''
    assert c['semantic_assessment']=='unassessed' and c['scope_result']=='not_assessed'
    assert c['reference_integrity']=='checked' and c['review_state']=='single_human_self_declared_not_independently_verified'
    assert len(c['references'])==1 and len(c['inspected_ranges'])==1
    source=prepared[c['paper_id']]; binding=next(x for x in d['sources'] if x['paper_id']==c['paper_id'])
    for ref in c['references']+c['inspected_ranges']:
        block=next(b for b in source.blocks if b.id==ref['block_id'])
        assert ref['source_id']==binding['source_id'] and ref['paper_id']==c['paper_id'] and ref['integrity']=='checked'
        assert ref['locator']==block.locator and ref['source_version']==source.version and ref['source_sha256']==source.source_sha256 and ref['blocks_sha256']==source.blocks_sha256
        assert type(ref['start']) is int and type(ref['end']) is int and 0<=ref['start']<ref['end']<=len(block.text) and ref['end']-ref['start']<=4000
        assert ref['quote']==block.text[ref['start']:ref['end']]
        input_keys=('source_id','source_version','source_sha256','blocks_sha256','block_id','start','end')
        assert ref['id']=='board-ref:'+digest([d['board_id'],d['revision_id'],c['paper_id'],{k:ref[k] for k in input_keys}])
    assert all(c['references'][0][k]==c['inspected_ranges'][0][k] for k in ('source_id','source_version','source_sha256','blocks_sha256','block_id','start','end'))
    expected_rows=[]
    for paper in d['papers']:
        source=next(x for x in d['sources'] if x['paper_id']==paper['id'])
        for field in d['fields']:
            cell=c if (paper['id'],field['id'])==(c['paper_id'],c['field_id']) else None
            row={'schema_version':'mvp.board-table.v1','board_id':d['board_id'],'board_revision_id':d['revision_id'],
              'search_id':d['search_id'],'search_sha256':d['search_sha256'],'question':d['question'],
              'preparation_id':d['preparation_id'],'source_manifest_sha256':d['source_manifest_sha256'],
              'paper_id':paper['id'],'paper_title':paper['title'],'pmid':paper['pmid'],'doi':paper['doi'],'authors':paper['authors'],'year':paper['year'],
              'source_id':source['source_id'],'source_type':source['source_type'],'source_status':source['status'],'source_sha256':source['source_sha256'],'blocks_sha256':source['blocks_sha256'],
              'field_id':field['id'],'field_revision_id':field['revision_id'],'field_label':field['label'],'field_subquestion':field['subquestion'],
              'cell_revision_id':cell['id'] if cell else None,'supersedes_id':cell['supersedes_id'] if cell else None,
              'value':cell['value'] if cell else None,'semantic_assessment':cell['semantic_assessment'] if cell else 'unassessed',
              'scope_result':cell['scope_result'] if cell else 'not_assessed','reference_integrity':cell['reference_integrity'] if cell else 'not_applicable',
              'missing_information':cell['missing_information'] if cell else '', 'reason':cell['reason'] if cell else '',
              'references':cell['references'] if cell else [],'inspected_ranges':cell['inspected_ranges'] if cell else [],
              'freshness':'current','review_state':cell['review_state'] if cell else 'not_assessed','producer':cell['producer'] if cell else None,'created_at':cell['created_at'] if cell else None}
            expected_rows.append(row)
    assert value['table']==expected_rows

def check(value, source):
    assert value['offset_convention'] == 'half-open-unicode-codepoints'
    definition = next(d for d in value['definitions'] if d['revision_id'] == value['selected_revision_id'])
    paper = next(p for p in definition['papers'] if p['pmid'] == PMID)
    revisions = value['cell_revisions']
    assert len(value['definitions']) == 1
    assert definition['question'] == 'Remote functional software QA'
    assert len(revisions) == 1
    cell = revisions[0]
    assert cell['value'] == EXPECTED
    assert cell['reason'] == 'Software fixture, not participant judgment or scientific support.'
    assert (cell['paper_id'], cell['field_id'], cell['board_revision_id'], cell['board_id']) == (paper['id'], FIELD, definition['revision_id'], definition['board_id'])
    assert cell['semantic_assessment'] == 'unassessed' and cell['scope_result'] == 'not_assessed'
    assert cell['references'] and cell['inspected_ranges']
    rows = [r for r in value['table'] if r['paper_id'] == paper['id'] and r['field_id'] == FIELD]
    assert len(rows) == 1 and rows[0]['cell_revision_id'] == cell['id'] and rows[0]['value'] == EXPECTED
    assert len(value['table']) == 9 and all(r['cell_revision_id'] is None for r in value['table'] if r is not rows[0])
    binding = next(s for s in definition['sources'] if s['paper_id'] == paper['id'])
    for ref in [*cell['references'], *cell['inspected_ranges']]:
        assert ref['paper_id'] == paper['id']
        for key in ('source_id', 'source_version', 'source_sha256', 'blocks_sha256'):
            assert ref[key] == binding['version' if key == 'source_version' else key]
        assert (ref['source_sha256'], ref['blocks_sha256'], ref['source_version']) == (source.source_sha256, source.blocks_sha256, source.version)
        block = next(b for b in source.blocks if b.id == ref['block_id'])
        assert 0 <= ref['start'] < ref['end'] <= len(block.text)
        assert block.text[ref['start']:ref['end']] == ref['quote']
    keys = ('source_id', 'source_version', 'source_sha256', 'blocks_sha256', 'block_id')
    for ref in cell['references']:
        assert any(all(r[k] == ref[k] for k in keys) and r['start'] <= ref['start'] and r['end'] >= ref['end'] for r in cell['inspected_ranges'])


def main():
    if len(sys.argv) != 7:
        raise ValueError('expected source tree, before and after JSON and CSV exports, receipt')
    if not __debug__:
        raise RuntimeError('Optimized Python disables validation assertions')
    root, before, after, before_csv, after_csv, receipt = map(Path, sys.argv[1:])
    sys.path.insert(0, str(root.resolve()))
    from src.mvp.adapters.saved_examples import SavedExampleProvider
    from src.mvp.contracts import SearchRequest
    provider = SavedExampleProvider(fixture_dir=root / 'examples/mvp/offline_microbiome_30_v1')
    papers = provider.search(SearchRequest(request_id='public-readback', query='public fixture', max_results=30)).papers
    source = provider.prepare(next(p for p in papers if p.pmid == PMID))
    a, b = before.read_bytes(), after.read_bytes()
    ca, cb = before_csv.read_bytes(), after_csv.read_bytes()
    for raw, csv_raw in ((a,ca),(b,cb)):
        audit=strict_loads(raw)
        public_audit(audit,papers,provider)
        check(audit,source)
        check_csv(csv_raw,audit)
    assert hashlib.sha256(a).digest() == hashlib.sha256(b).digest()
    assert hashlib.sha256(ca).digest() == hashlib.sha256(cb).digest()
    proof={'schema':'remote-functional-readback-v1','status':'PASS','before_sha256':hashlib.sha256(a).hexdigest(),'after_sha256':hashlib.sha256(b).hexdigest(),'before_csv_sha256':hashlib.sha256(ca).hexdigest(),'after_csv_sha256':hashlib.sha256(cb).hexdigest(),'pmid':PMID,'field':FIELD,'submitted_revisions':1,'table_cells':9,'source_ranges_valid':True,'csv_parity':True}
    with receipt.open('x',encoding='utf-8') as out: json.dump(proof,out,sort_keys=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'namespace': 'REMOTE_WEB_FUNCTIONAL_ACCEPTANCE', 'readback': 'BLOCKED', 'strict_j01': 'NOT_RUN'}))
        sys.exit(2)
