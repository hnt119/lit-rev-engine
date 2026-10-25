"""Mocked public-packet/source-contract tests; no model execution."""
import copy
import csv
import io
import pytest
from tests.windows.hybrid_http_probe import abstract_csv, exact_context


def test_public_abstract_packet_omits_resolving_identifiers_without_changing_text():
    papers=[{'id':str(i),'title':f'PUBLIC fixture {i}','authors':['Software QA'],
        'year':2026,'doi':'10.5555/fixture','pmid':str(i+1),'pmcid':'PMC123',
        'abstract':('PUBLIC abstract α 🧬\n' * (8+i))} for i in range(3)]
    payload, selected=abstract_csv(papers)
    parsed=list(csv.DictReader(io.StringIO(payload.decode('utf-8'))))
    assert len(parsed)==2
    assert [row['Abstract'] for row in parsed]==[paper['abstract'] for paper in selected]
    assert set(parsed[0])=={'Title','Authors','Year','Abstract'}
    assert not any(key in parsed[0] for key in ('PMID','PMCID','DOI'))


def test_no_generated_substitute_when_public_abstracts_exceed_bound():
    with pytest.raises(RuntimeError,match='Two bounded approved public abstracts'):
        abstract_csv([{'id':'public','abstract':'x'*2501}])


def example():
    reference={'paper_id':'paper-a','source_id':'source-a','source_version':'1',
        'source_sha256':'a'*64,'blocks_sha256':'b'*64,'block_id':'block-a',
        'start':1,'end':2,'quote':'🧬'}
    return reference,{'reference':reference.copy(),'paper':{'id':'paper-a'},
        'source':{'paper_id':'paper-a','source_id':'source-a','version':'1','source_type':'abstract',
            'source_sha256':'a'*64,'blocks_sha256':'b'*64},
        'block':{'paper_id':'paper-a','block_id':'block-a','start':0,'end':3,'text':'α🧬z'}}


def test_exact_context_reconstructs_unicode_codepoints():
    reference,context=example()
    exact_context(context,reference,'paper-a')


@pytest.mark.parametrize('change',['paper','source_hash','range','quote'])
def test_exact_context_rejects_wrong_paper_source_or_anchor(change):
    reference,context=example(); context=copy.deepcopy(context)
    if change=='paper':context['paper']['id']='paper-b'
    elif change=='source_hash':context['source']['source_sha256']='c'*64
    elif change=='range':context['reference']['end']=3
    else:context['reference']['quote']='z'
    with pytest.raises(AssertionError):exact_context(context,reference,'paper-a')
