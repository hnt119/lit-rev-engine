"""Read-only strategy projection and additive design notes, never provider calls."""
import html
import json
from typing import Literal
from fastapi import Depends,Query,Response
from src.mvp.contracts import digest
from src.mvp.ports import MvpError
from src.mvp.search_plan_metadata import SearchPlanMetadataPut,SearchPlanMetadataView,SearchPlanMetadataService


def strategy_projection(plans,metadata_service,mode,handle,plan_id,revision_id,candidate_id):
    view=plans.view(handle,plan_id,revision_id)
    revision=view.revision
    candidate=next((c for c in revision.compiled.candidates if c.id==candidate_id),None)
    if candidate is None:raise MvpError('stale_search_candidate','Choose a candidate from this exact saved plan revision.')
    matching=lambda item:item.revision_id==revision.revision_id and item.candidate_id==candidate.id and item.candidate_sha256==candidate.candidate_sha256
    approval=next((item for item in view.approvals if matching(item)),None)
    diagnostic=next((item for item in view.diagnostics if matching(item)),None)
    execution=next((item for item in view.executions if matching(item)),None)
    captured=None
    if execution:
        captured=plans._execution_result(handle,plan_id,execution.id).search
    metadata=metadata_service.view(mode,handle,plan_id,revision.revision_id)
    return {'schema_version':'mvp.readable-search-strategy.v1',
        'plan_id':plan_id,'revision_id':revision.revision_id,'plan_sha256':revision.compiled.plan_sha256,
        'candidate_id':candidate.id,'candidate_sha256':candidate.candidate_sha256,
        'question':revision.draft.original_question,'database':'PubMed','platform':'NCBI E-utilities',
        'compiler_version':revision.compiled.compiler_version,'local_validation':candidate.status,
        'query':candidate.query,'query_sha256':__import__('hashlib').sha256(candidate.query.encode('utf-8')).hexdigest(),
        'filters':{'date_from':candidate.date_from,'date_to':candidate.date_to,'sort':candidate.sort},
        'concepts':[c.model_dump(mode='json') for c in revision.draft.concepts],
        'variant':next((v.model_dump(mode='json') for v in revision.draft.variants if v.id==candidate.id),None),
        'differences':candidate.differences,'deferred_constraints':candidate.deferred_constraints,
        'unparsed_constraints':candidate.unparsed_constraints,
        'unresolved_issues':[i.model_dump(mode='json') for i in candidate.issues],
        'ambiguities':[i.model_dump(mode='json') for i in revision.draft.ambiguities],
        'approval':approval.model_dump(mode='json') if approval else None,
        'approval_status':'researcher_approved_intent' if approval else 'not_approved',
        'diagnostic':diagnostic.model_dump(mode='json') if diagnostic else None,
        'execution':execution.model_dump(mode='json') if execution else None,
        'capture':({'search_id':captured.id,'searched_at':captured.searched_at,'provider':captured.provider,'mode':captured.mode,
            'reported_count':captured.total_reported,'fetched_count':captured.fetched_count,
            'distinct_records':len(captured.papers),'requested_max_results':execution.requested_max_results,
            'truncated':captured.truncated,'warnings':captured.warnings,'snapshot_sha256':digest(captured.model_dump(mode='json'))} if captured else None),
        'design_notes':metadata.model_dump(mode='json'),
        'limitations':['Researcher intent approval is not provider or terminology validation.',
            'No authoritative terminology registry is available; terminology references are unverified researcher notes.',
            'Diagnostics are bounded samples and known-paper membership checks, not complete captures or recall validation.',
            'External searches are researcher-recorded and unvalidated; their platform syntax and reported counts were not executed or verified here.',
            'Extraction questions are later-reading prompts, not findings, eligibility decisions or automatic board fields.']}


def strategy_markdown(value):
    import re
    escape=lambda text:re.sub(r'([\\`*_{}\[\]()#+.!|>~-])',r'\\\1',html.escape(str(text),quote=False))
    query=value['query']
    # A dynamic fence cannot be escaped by an expert query containing backticks.
    fence='`'*max(3,max((len(x) for x in re.findall(r'`+',query)),default=0)+1)
    lines=['# Search strategy','',escape(value['question']),'',
        f"Compiler target: {value['database']} / {value['platform']} (does not establish execution)",
        f"Intent: {value['approval_status']} · local compilation: {value['local_validation']}",
        f"Plan/revision: {value['plan_id']} / {value['revision_id']}",'',
        '## Exact query','',fence+'text',query,fence,'',
        'Query SHA-256: '+value['query_sha256'],'',
        '## Concepts and later constraints','']
    for concept in value['concepts']:
        lines.append('- '+escape(concept['label'])+' · '+escape(concept['role'])+' · '+concept['requirement']+' · '+concept['retrieval_use'])
        for term in concept['terms']:
            lines.append('  - '+escape(term['text'])+' · '+term['field']+' · '+term['origin']+' · '+term['state']+' · '+escape(term['provenance_note']))
    lines+=['','## Limits and retained execution','',escape(json.dumps(value['filters'],ensure_ascii=False)),
        escape(json.dumps(value['capture'],ensure_ascii=False)) if value['capture'] else 'No execution/capture is recorded for this candidate.']
    if value['approval']:lines+=['Researcher intent approval: '+escape(value['approval']['id'])+' · '+escape(value['approval']['created_at'])]
    lines+=['','## Variant changes and explicit deferrals','']+['- '+escape(text) for text in value['differences']]
    if value.get('variant'):
        for key in ('deferral_reason','split_explanation'):
            if value['variant'].get(key):lines.append(escape(key.replace('_',' ')+': '+value['variant'][key]))
    if value['capture']:lines+=['Retained capture provider/mode: '+escape(value['capture']['provider'])+' / '+escape(value['capture']['mode'])]
    diagnostic=value['diagnostic']
    lines+=['','## Provider diagnostic','']
    if diagnostic:
        receipt=diagnostic['receipt']
        lines += [f"Status: {receipt['status']} · provider count: {receipt['reported_count']} · actual calls: {receipt['calls']}",
            'Retrieved at: '+escape(receipt['retrieved_at']),
            'Diagnostic sample: '+str(len(receipt['sample_pmids']))+'/'+str(receipt['sample_limit'])+' · PMIDs: '+escape(', '.join(receipt['sample_pmids'])),
            'Provider translation: '+escape(receipt['query_translation'] or 'unavailable')]
        lines += ['- '+escape(m['code']+': '+m['message']) for m in receipt['messages']]
        if receipt['error']:lines.append('Provider/operation error: '+escape(receipt['error']['code']+': '+receipt['error']['message']))
        if receipt['status']=='succeeded' and receipt['reported_count']==0:lines.append('Successful diagnostic reported zero matches; this is separate from a provider error.')
        for seed in receipt['seed_results']:
            identity=seed['seed'].get('pmid') or seed['seed'].get('doi') or seed['seed']['id']
            lines.append('- Seed '+escape(identity)+' · '+seed['seed']['purpose']+' · query membership '+seed['query_membership']+' · capped-preview recovery '+seed['preview_recovery']+' · '+escape(seed['reason']))
    else:lines.append('No provider diagnostic is recorded; nothing was run by this export.')
    notes=value['design_notes']['metadata']
    lines+=['','## Later extraction questions','']+['- '+escape(q['question']) for q in notes['extraction_questions']]
    lines+=['','## Unverified terminology references','']+['- '+escape(n['concept_id']+'/'+n['term_id']+': '+n['note']+' '+n['authority_reference']) for n in notes['term_notes']]
    lines+=['','## Researcher-recorded external strategies','']
    for item in notes['external_searches']:
        raw=item['query'];external_fence='`'*max(3,max((len(x) for x in re.findall(r'`+',raw)),default=0)+1)
        lines += [escape(item['database']+' / '+item['platform'])+' · UNVALIDATED RESEARCHER RECORD',
            escape(json.dumps({key:item[key] for key in ('executed_on','reported_count','limits_note','collection_ref')},ensure_ascii=False)),external_fence+'text',raw,external_fence]
    lines+=['','## Unresolved issues and limits','']
    lines+=['- '+escape(i['code']+': '+i['message']) for i in value['unresolved_issues']]
    lines+=['- '+escape(a['message']) for a in value['ambiguities'] if not a['resolved']]
    lines+=['- '+escape(text) for text in value['deferred_constraints']+value['unparsed_constraints']+value['limitations']]
    return '\n'.join(lines)+'\n'


def install_search_strategy_routes(app,*,planning,owned,session_for,dependencies,registry):
    service=SearchPlanMetadataService(planning,registry,lambda mode:app.state.collections_for(mode))
    app.state.search_plan_metadata=service
    prefix='/api/v1/workspaces/{workspace_id}/search-plans/{plan_id}'

    @app.get(prefix+'/metadata',response_model=SearchPlanMetadataView,dependencies=dependencies)
    def metadata(workspace_id:str,plan_id:str,revision_id:str|None=None,version:int|None=Query(default=None,ge=0),session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return service.view(mode,handle,plan_id,revision_id,version)

    @app.put(prefix+'/metadata',response_model=SearchPlanMetadataView,dependencies=dependencies)
    def save_metadata(workspace_id:str,plan_id:str,request:SearchPlanMetadataPut,session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return service.put(mode,handle,plan_id,request)

    @app.get(prefix+'/strategy-export',dependencies=dependencies)
    def export(workspace_id:str,plan_id:str,revision_id:str=Query(min_length=1,max_length=200),candidate_id:str=Query(min_length=1,max_length=100),format:Literal['markdown','json']='markdown',session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        value=strategy_projection(planning(mode),service,mode,handle,plan_id,revision_id,candidate_id)
        body=strategy_markdown(value) if format=='markdown' else json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
        if len(body.encode('utf-8'))>2*1024*1024:raise MvpError('export_size_limit','This strategy exceeds its bounded export size; no partial export was produced.')
        return Response(body,media_type='text/markdown' if format=='markdown' else 'application/json',headers={'Content-Disposition':'attachment; filename="search-strategy.'+('md' if format=='markdown' else 'json')+'"'})
