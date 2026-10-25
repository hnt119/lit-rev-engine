#!/usr/bin/env python3
"""Opt-in real local A–F development comparison; no download or cloud requests.

Run after explicit pack installation. Frozen synthetic/public development anchors
are agent-authored regression labels, not human gold or fresh held-out evidence.
Cell A–F use identical per-case source scope, component queries and displayed budgets;
B–F share the exact same tokenizer-validated query-independent window inventory.
"""
from argparse import ArgumentParser
from collections import defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.mvp.adapters.span_retrieval import LexicalSpanRetrieval
from src.mvp.contracts import SearchRequest, digest, now
from src.mvp.hybrid_contracts import QWEN_PROFILE, MEDCPT_PROFILE
from src.mvp.hybrid_retrieval import HybridRetrieval, _lexical, _quotas, RRF_C
from src.mvp.hybrid_windows import build_inventory, source_binding
from src.mvp.retrieval_packs import PackManager
from src.mvp.span_budget import budget_token_count
from src.mvp.span_evaluation import DEFAULT_MANIFEST, FROZEN_MANIFEST_SHA256, load_frozen_cases
from src.mvp.span_retrieval_contracts import SpanRequirement

LANES = ('A_existing_lexical_spans', 'B_common_window_bm25', 'C_qwen_rrf_no_reranker',
         'D_qwen_hybrid_reranker', 'E_medcpt_rrf_no_reranker', 'F_medcpt_hybrid_reranker')


def _view(reference, score, **extra):
    return dict(source_id=reference.source_id, paper_id=reference.paper_id, block_id=reference.block_id,
        start=reference.start, end=reference.end, quote=reference.quote, score=score, **extra)


def _covered(anchors, spans):
    return [anchor['id'] for anchor in anchors if any(span['block_id'] == anchor['block_id']
        and span['start'] <= anchor['start'] and span['end'] >= anchor['end'] for span in spans)]


def _overlap(left, right):
    return left['block_id'] == right['block_id'] and (max(0, min(left['end'], right['end'])-max(left['start'], right['start']))
        / min(left['end']-left['start'], right['end']-right['start']) >= .5)


def _metrics(case, source, spans, common_inventory, *, operation='cell'):
    maximum = 3 if operation == 'cell' else 10
    blocks = {value.id: value for value in source.blocks}
    if len(spans) > maximum or sum(len(v['quote']) for v in spans) > maximum*1200 or sum(budget_token_count(v['quote']) for v in spans) > maximum*400:
        raise ValueError('A lane violated its declared displayed operation budget.')
    for span in spans:
        block = blocks.get(span['block_id'])
        if (span['source_id'] != source.id or span['paper_id'] != source.paper_id or block is None
            or not 0 <= span['start'] < span['end'] <= len(block.text)
            or block.text[span['start']:span['end']] != span['quote'] or not math.isfinite(span['score'])
            or len(span['quote']) > 1200 or budget_token_count(span['quote']) > 400):
            raise ValueError('A lane violated exact source/offset/input budget integrity.')
    covered = _covered(case['anchors'], spans)
    components = [value['id'] for value in case['requirements'] if set(value['anchor_ids']) <= set(covered)]
    gains = [len(_covered(case['anchors'], [span])) for span in spans[:3]]
    ideal = sorted([len(_covered(case['anchors'], [_view(w.reference, 1)])) for w in common_inventory.windows], reverse=True)[:3] if common_inventory is not None else []
    dcg = sum(gain/math.log2(rank+2) for rank, gain in enumerate(gains))
    idcg = sum(gain/math.log2(rank+2) for rank, gain in enumerate(ideal))
    at_k = {}
    for k in (5, 10):
        anchors_at_k = _covered(case['anchors'], spans[:k])
        at_k['fixed_anchor_recall_at'+str(k)] = (len(anchors_at_k)/len(case['anchors']) if case['anchors'] else None) if operation == 'search' else 'NOT_RUN; cell maximum3'
        at_k['all_expected_anchors_at'+str(k)] = (len(anchors_at_k)==len(case['anchors']) if case['anchors'] else None) if operation == 'search' else 'NOT_RUN; cell maximum3'
        if common_inventory is not None and operation == 'search':
            gains_k = [len(_covered(case['anchors'], [span])) for span in spans[:k]]
            ideal_k = sorted([len(_covered(case['anchors'], [_view(w.reference, 1)])) for w in common_inventory.windows],reverse=True)[:k]
            denominator = sum(g/math.log2(rank+2) for rank,g in enumerate(ideal_k))
            at_k['fixed_anchor_ndcg_proxy_at'+str(k)] = sum(g/math.log2(rank+2) for rank,g in enumerate(gains_k))/denominator if denominator else None
        else: at_k['fixed_anchor_ndcg_proxy_at'+str(k)] = 'NOT_RUN; different A inventory or cell maximum3'
    return {**at_k, 'covered_anchor_ids': covered, 'anchors_covered': len(covered), 'anchors_expected': len(case['anchors']),
        'covered_component_ids': components, 'components_covered': len(components), 'components_expected': len(case['requirements']),
        'all_expected_anchors_covered': len(covered)==len(case['anchors']) if case['anchors'] else None,
        'all_declared_components_covered': len(components)==len(case['requirements']) if case['requirements'] else None,
        'fixed_anchor_count_dcg_at3': dcg, 'common_inventory_ideal_fixed_anchor_count_dcg_at3': idcg,
        'fixed_anchor_ndcg_proxy_at3': dcg/idcg if idcg else None,
        'ndcg_scope': 'agent-authored exact-anchor-count grades; overlapping windows may share anchors; not human graded relevance',
        'unsupported_question_returned_candidates': bool(spans) if case['answerability']!='answerable' else None,
        'returned_candidates':len(spans), 'delivered_characters':sum(len(v['quote']) for v in spans),
        'delivered_budget_tokens':sum(budget_token_count(v['quote']) for v in spans),
        'wrong_paper_candidates':0, 'wrong_cohort_error':'NOT_ADJUDICATED', 'numeric_error':'NOT_ADJUDICATED',
        'meaning':'fixed-development-anchor-coverage-not-entailment-or-support-judgment'}


def _ablation(inventory, requirements, *, qvectors=None, index=None, operation='cell'):
    maximum, branch_depth = (3,20) if operation == 'cell' else (10,50)
    """Controlled evaluator-only fusion/lexical ablations; no fabricated result DTO."""
    windows, stages = inventory.windows, {}
    for component, quota, position in zip(requirements, _quotas(branch_depth,len(requirements)), range(len(requirements))):
        lexical = _lexical(windows, component.query)
        lex_order = sorted(lexical,key=lambda i:(-lexical[i],windows[i].id))[:quota]
        lex_rank = {i:r for r,i in enumerate(lex_order,1)}
        if qvectors is not None:
            dense = {i:sum(a*b for a,b in zip(qvectors[position],row)) for i,row in enumerate(index.vectors)}
            dense_order = sorted(dense,key=lambda i:(-dense[i],windows[i].id))[:quota]
            dense_rank = {i:r for r,i in enumerate(dense_order,1)}
        else:
            dense, dense_rank = {}, {}
        union=set(lex_rank)|set(dense_rank)
        fusion={i:sum(1/(RRF_C+ranks[i]) for ranks in (lex_rank,dense_rank) if i in ranks) for i in union}
        order=sorted(union,key=lambda i:(-fusion[i],windows[i].id))
        for rank,i in enumerate(order[:quota],1):
            stages.setdefault(i,[]).append({'component_id':component.id,'fusion_rank':rank,'fusion_score':fusion[i],
                'bm25_rank':lex_rank.get(i),'bm25_score':lexical.get(i) if i in lex_rank else None,
                'dense_rank':dense_rank.get(i),'dense_score':dense.get(i) if i in dense_rank else None})
    selected=[]
    def add(i):
        span=_view(windows[i].reference,max(s['fusion_score'] for s in stages[i]),stages=stages[i])
        if (len(selected)<maximum and not any(_overlap(span,old) for old in selected)
            and sum(len(v['quote']) for v in selected)+len(span['quote'])<=maximum*1200
            and sum(budget_token_count(v['quote']) for v in selected)+budget_token_count(span['quote'])<=maximum*400):
            selected.append(span);return True
        return False
    for component in requirements:
        for _,_,i in sorted((s['fusion_rank'],windows[i].id,i) for i,values in stages.items() for s in values if s['component_id']==component.id):
            if add(i):break
    order=sorted(stages,key=lambda i:(min(v['fusion_rank'] for v in stages[i]),-sum(v['fusion_score'] for v in stages[i]),windows[i].id))
    for i in order:
        if not any(v['block_id']==windows[i].reference.block_id and v['start']==windows[i].reference.start and v['end']==windows[i].reference.end for v in selected):add(i)
    return selected


class _BoundRealQueryVectors:
    """Reuse the exact observed encoder output in its matched reranking lane."""
    def __init__(self, adapter, queries, vectors):
        self.adapter,self.queries,self.vectors=adapter,list(queries),vectors
    def __getattr__(self, name):return getattr(self.adapter,name)
    def encode_queries(self,queries):
        if list(queries)!=self.queries:raise ValueError('Cached real query vectors belong to another input.')
        return self.vectors


def run(cache_dir, *, device='cpu', include_public=False, case_ids=None, operation='cell'):
    started=time.perf_counter()
    manifest,sources=load_frozen_cases()
    kinds={value['id']:value['kind'] for value in manifest['sources']}
    cases=[case for case in manifest['cases'] if (include_public or kinds[case['source_id']]=='synthetic') and (not case_ids or case['id'] in case_ids)]
    if not cases or (case_ids and set(case_ids)-{value['id'] for value in cases}):raise ValueError('Select existing cases in the declared development subset.')
    manager=PackManager(cache_dir)
    adapters={profile:manager.adapter(profile,device=device) for profile in (QWEN_PROFILE,MEDCPT_PROFILE)}
    titles={source.paper_id:'Synthetic evidence fixture '+source.id for source in sources.values() if kinds[source.id]=='synthetic'}
    if include_public:
        from src.mvp.adapters.saved_examples import SavedExampleProvider
        papers=SavedExampleProvider().search(SearchRequest(request_id='hybrid-eval-local-titles',query='Local fixture metadata only',max_results=30)).papers
        titles.update({paper.id:paper.title for paper in papers})
    code_paths=['scripts/evaluate_hybrid_retrieval.py','src/mvp/adapters/neural_retrieval.py','src/mvp/hybrid_retrieval.py',
        'src/mvp/hybrid_windows.py','src/mvp/hybrid_contracts.py','src/mvp/adapters/span_retrieval.py']
    code_hashes={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in code_paths}
    inventories,indexes,index_receipts,records={}, {}, [], []
    for case in cases:
        source=sources[case['source_id']]
        if source.id in inventories:continue
        inventory=build_inventory([source],authorized_sources=[source_binding(source)],titles=titles,
            fits_document=lambda title,text:all(adapter.fits_document(title,text) for adapter in adapters.values()))
        inventories[source.id]=inventory
        for profile,adapter in adapters.items():
            tick=time.perf_counter(); index=HybridRetrieval(adapter).build_index(inventory); indexes[profile,source.id]=index
            index_receipts.append({'source_id':source.id,'profile_id':profile,'index':index.model_dump(mode='json'),
                'wall_seconds':time.perf_counter()-tick,'source_kind':kinds[source.id]})
        print(json.dumps({'event':'indexed','source_id':source.id,'common_windows':len(inventory.windows)}),flush=True)
    lexical=LexicalSpanRetrieval()
    for case in cases:
        source=sources[case['source_id']];inventory=inventories[source.id]
        required=[SpanRequirement(id=v['id'],label=v['id'],query=v['text']) for v in case['requirements']] or [SpanRequirement(id='field',label='Field question',query=case['question'])]
        for adapter in adapters.values():
            for item in required:adapter.validate_query(item.query)
        rows=[]
        tick=time.perf_counter();result=lexical.search(case['question'],[source],case['id']+':A',top_k=3,requirements=required)
        rows.append((LANES[0],[dict(source_id=v.source_id,paper_id=v.paper_id,block_id=v.block_id,start=v.start,end=v.end,quote=v.quote,score=v.score) for v in result.selections],time.perf_counter()-tick,{'result':result.model_dump(mode='json')}))
        tick=time.perf_counter();spans=_ablation(inventory,required,operation=operation)
        rows.append((LANES[1],spans,time.perf_counter()-tick,{'inventory_sha256':inventory.manifest_sha256}))
        for profile,letters in ((QWEN_PROFILE,(2,3)),(MEDCPT_PROFILE,(4,5))):
            adapter=adapters[profile];index=indexes[profile,source.id]; queries=[v.query for v in required]
            tick=time.perf_counter();qvectors=adapter.encode_queries(queries);query_seconds=time.perf_counter()-tick
            tick=time.perf_counter();spans=_ablation(inventory,required,qvectors=qvectors,index=index,operation=operation)
            rows.append((LANES[letters[0]],spans,query_seconds+time.perf_counter()-tick,
                {'query_vector_sha256':digest(qvectors),'query_encoding_seconds':query_seconds,'index_key':index.index_key,'reranker_executed':False}))
            tick=time.perf_counter();result=HybridRetrieval(_BoundRealQueryVectors(adapter,queries,qvectors)).search(case['question'],[source],case['id']+':'+str(letters[1]),top_k=3 if operation=='cell' else 10,
                authorized_sources=[source_binding(source)],titles=titles,requirements=required,operation=operation,index=index,inventory=inventory)
            rows.append((LANES[letters[1]],[_view(v.reference,v.score,stages=[s.model_dump(mode='json') for s in v.stages]) for v in result.candidates],
                query_seconds+time.perf_counter()-tick,{'result':result.model_dump(mode='json'),'query_vector_sha256':digest(qvectors),
                'query_encoding_seconds':query_seconds,'query_encoder_output_reused_from_matched_ablation':True,'reranker_executed':True}))
        for lane,spans,seconds,receipt in rows:
            records.append({'case_id':case['id'],'source_id':source.id,'paper_id':source.paper_id,'related_study_group':case['related_study_group'],
                'source_kind':kinds[source.id],'lane':lane,'question':case['question'],'explicit_requirements':[v.model_dump(mode='json') for v in required],
                'source_sha256':source.source_sha256,'blocks_sha256':source.blocks_sha256,'common_inventory_sha256':inventory.manifest_sha256,
                'delivered_selections':spans,'elapsed_seconds':seconds,'metrics':_metrics(case,source,spans,None if lane==LANES[0] else inventory,operation='cell' if lane==LANES[0] else operation),'receipt':receipt})
        print(json.dumps({'event':'case_complete','case_id':case['id'],'lanes':len(rows)}),flush=True)
    summaries=[]
    for lane in LANES:
        selected=[r for r in records if r['lane']==lane]
        summaries.append({'lane':lane,'case_count':len(selected),**{k:sum(r['metrics'][k] for r in selected) for k in ('anchors_covered','anchors_expected','components_covered','components_expected')},
            'all_expected_anchors_covered_cases':sum(r['metrics']['all_expected_anchors_covered'] is True for r in selected),
            'answerable_cases':sum(r['metrics']['all_expected_anchors_covered'] is not None for r in selected),
            'unsupported_questions_returning_candidates':sum(r['metrics']['unsupported_question_returned_candidates'] is True for r in selected),
            'unsupported_question_count':sum(r['metrics']['unsupported_question_returned_candidates'] is not None for r in selected),
            'mean_anchor_ndcg_proxy_at3':sum(values)/len(values) if (values:=[r['metrics']['fixed_anchor_ndcg_proxy_at3'] for r in selected if r['metrics']['fixed_anchor_ndcg_proxy_at3'] is not None]) else None,
            'sum_retrieval_seconds_excludes_indexing':sum(r['elapsed_seconds'] for r in selected),
            **{key:(sum(vals)/len(vals) if (vals:=[r['metrics'][key] for r in selected if isinstance(r['metrics'][key],(int,float)) and not isinstance(r['metrics'][key],bool)]) else None) for key in ('fixed_anchor_recall_at5','fixed_anchor_recall_at10','fixed_anchor_ndcg_proxy_at5','fixed_anchor_ndcg_proxy_at10')}})
    regressions=[]
    for case in cases:
        baseline=next(r for r in records if r['case_id']==case['id'] and r['lane']==LANES[0])
        for row in records:
            if row['case_id']==case['id'] and row['metrics']['anchors_covered']<baseline['metrics']['anchors_covered']:
                regressions.append({'case_id':case['id'],'lane':row['lane'],'anchors_covered':row['metrics']['anchors_covered'],
                    'lexical_anchors_covered':baseline['metrics']['anchors_covered'],'anchors_expected':row['metrics']['anchors_expected']})
    if code_hashes!={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in code_paths}:raise ValueError('Evaluation code changed during measurement; retain partial output but do not call the run frozen.')
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    try:commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    except (OSError,subprocess.CalledProcessError):commit=None
    return {'schema_version':'mvp.hybrid-development-evaluation.v1','created_at':now(),'source_commit':commit,'code_sha256':code_hashes,
        'frozen_development_manifest_sha256':FROZEN_MANIFEST_SHA256,'selected_case_ids':[v['id'] for v in cases],
        'label_status':manifest['label_status'],'source_inputs':[sources[key].model_dump(mode='json') for key in inventories],
        'title_inputs':{sources[key].paper_id:titles[sources[key].paper_id] for key in inventories},
        'operation':operation,'budgets':{'max_references':3 if operation=='cell' else 10,'max_characters':3600 if operation=='cell' else 12000,'max_budget_tokens':1200 if operation=='cell' else 4000,'each_branch_candidates':20 if operation=='cell' else 50,'rerank_pairs':20 if operation=='cell' else 50,'A_baseline_always_cell_maximum3':True,
            'hyperparameters':'frozen engineering defaults; not optimized on this run'},
        'inventories':{key:value.model_dump(mode='json') for key,value in inventories.items()},'index_receipts':index_receipts,
        'records':records,'summaries':summaries,'anchor_regressions_against_A':regressions,
        'actual_runtime':{profile:adapter.runtime_metadata() for profile,adapter in adapters.items()},
        'wall_seconds':time.perf_counter()-started,'peak_whole_process_rss_bytes':rss if sys.platform=='darwin' else rss*1024,
        'resource_scope':'process high-water memory; includes Python/model loads; not incremental model memory',
        'sufficient_support_retrieval_at5':'NOT_RUN; human support labels missing; exact-anchor search proxy reported separately' if operation=='search' else 'NOT_RUN; per-cell output maximum3', 'sufficient_support_retrieval_at10':'NOT_RUN; human support labels missing; exact-anchor search proxy reported separately' if operation=='search' else 'NOT_RUN; per-cell output maximum3',
        'human_correction_time':'NOT_RUN','held_out_validation':'NOT_RUN','human_graded_relevance':'NOT_RUN','semantic_entailment':'NOT_RUN',
        'wrong_cohort_and_numeric_error_adjudication':'NOT_RUN','generation':'NOT_RUN','paid_calls':0,'network_requests':0,
        'limitations':[*manifest['limitations'],'All selected cases are development regressions, including public saved fixtures; no fresh held-out or human-gold superiority claim.',
            'A uses the existing exact-span lexical baseline; B–F share a new common inventory. A/B isolate window differences.',
            'All six lanes use identical explicit component queries. In cell mode their displayed budgets match; in search mode A retains its native max3 and is excluded from claims about common-budget search@5/10. B–F share actual max10 search output.',
            'C/D and E/F share exactly the same real encoded query vectors and indexes; D/F add actual cross-encoder execution.',
            'nDCG proxy grades each returned span by count of fixed exact anchors, not human-assessed relevance; source windows may share anchors.',
            'Index timing is cold component work; retrieval uses an existing exact index but reloads component weights. No warmed-resident-model claim.',
            'Wrong-paper count is an integrity check, not a wrong-cohort or numeric semantic error rate. Human adjudication remains required.']}


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir',type=Path,required=True)
    parser.add_argument('--device',choices=('cpu','mps'),default='cpu')
    parser.add_argument('--include-public',action='store_true')
    parser.add_argument('--operation',choices=('cell','search'),default='cell')
    parser.add_argument('--case',action='append',dest='case_ids')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run(args.cache_dir,device=args.device,include_public=args.include_public,case_ids=args.case_ids,operation=args.operation)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'output':str(args.output),'summaries':report['summaries'],'regressions':report['anchor_regressions_against_A'],
        'wall_seconds':report['wall_seconds'],'peak_whole_process_rss_bytes':report['peak_whole_process_rss_bytes'],
        'held_out_validation':'NOT_RUN','human_usefulness':'NOT_RUN'},indent=2))

if __name__=='__main__':main()
