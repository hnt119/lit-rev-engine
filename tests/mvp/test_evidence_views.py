"""Offline additive view/classification checks, not scientific usefulness."""
import json
from uuid import uuid4
import pytest
from pydantic import ValidationError
from test_boards import case, ref_from
from src.mvp.evidence_views import EvidenceViewService, TABLES
from src.mvp.evidence_view_contracts import DimensionPut, AttributePut, EvidenceViewConfig, FacetFilter, SavedViewPut
from src.mvp.board_contracts import BoardCandidatesRequest, BoardCellData, BoardDraftPutRequest, BoardSubmitRequest
from src.mvp.ports import MvpError

def fixture(case):
    boards,handle,engine,store,registry,_,view=case
    return EvidenceViewService(boards),boards,handle,engine,store,registry,view.definition

def binding(service,handle,d,dimension='specimen',field='diet',expected=None):
    return service.bind_dimension('test',handle,d.board_id,d.revision_id,DimensionPut(request_id=str(uuid4()),expected_head_id=expected,
        dimension_id=dimension,field_id=field,label='Explicit '+dimension,definition='SYNTHETIC report-level classification, no cohort relationship inferred.'))

def submit(boards,handle,d,paper=None,field='diet',supported=True):
    paper=paper or d.paper_ids[0]
    found=boards.candidates('test',handle,d.board_id,BoardCandidatesRequest(request_id=str(uuid4()),expected_revision_id=d.revision_id,paper_id=paper,field_id=field))
    ref=ref_from(found.candidates[0].reference)
    current=boards.get_draft('test',handle,d.board_id,paper,field)
    draft=boards.put_draft('test',handle,d.board_id,paper,field,BoardDraftPutRequest(expected_revision_id=d.revision_id,version=current.version,
        expected_cell_head_id=current.expected_cell_head_id,data=BoardCellData(value='SYNTHETIC manual value',references=[ref],inspected_ranges=[ref],
        semantic_assessment='human_supported' if supported else 'unassessed',scope_result='value_found',reason='Software fixture; not a researcher finding.')))
    return boards.submit('test',handle,d.board_id,BoardSubmitRequest(request_id=str(uuid4()),expected_revision_id=d.revision_id,paper_id=paper,field_id=field,
        draft_version=draft.version,supersedes_id=current.expected_cell_head_id))

def classify(service,handle,d,dimension,cell,values=('stool','vaginal'),state='confirmed',expected=None):
    return service.classify('test',handle,d.board_id,d.revision_id,AttributePut(request_id=str(uuid4()),expected_head_id=expected,
        dimension_revision_id=dimension.id,paper_id=cell.paper_id,origin_kind='cell',origin_id=cell.id,values=list(values),review_state=state,reason='SYNTHETIC explicit normalization.'))

def test_scalar_cells_never_infer_dimensions_and_reads_leave_science_unchanged(case):
    service,boards,h,engine,store,_,d=fixture(case)
    submit(boards,h,d)
    before=boards.export('test',h,d.board_id).model_dump_json()
    first=service.profiles('test',h,d.board_id,d.revision_id)
    assert all(a.state=='unknown' and not a.values for p in first.papers for a in p.attributes)
    service.query('test',h,d.board_id,d.revision_id,EvidenceViewConfig())
    assert boards.export('test',h,d.board_id).model_dump_json()==before
    assert first==service.profiles('test',h,d.board_id,d.revision_id)

def test_explicit_multivalue_filters_or_within_and_across_unknown_and_overlap(case):
    service,boards,h,_,_,_,d=fixture(case)
    specimen=binding(service,h,d);design=binding(service,h,d,'design','methods')
    classify(service,h,d,specimen,submit(boards,h,d))
    classify(service,h,d,design,submit(boards,h,d,field='methods'),('cohort',))
    config=EvidenceViewConfig(filters=[FacetFilter(dimension='specimen',values=['oral','vaginal']),FacetFilter(dimension='design',values=['cohort'])],group_by='specimen')
    result=service.query('test',h,d.board_id,d.revision_id,config)
    assert result.paper_ids==d.paper_ids[:1] and result.unique_report_count==1 and result.group_occurrences==2
    assert set(result.groups)=={'stool','vaginal'} and result.profiles.scope=='report_cooccurrence_only_not_same_cohort'
    unknown=service.query('test',h,d.board_id,d.revision_id,EvidenceViewConfig(filters=[FacetFilter(dimension='specimen',values=['unknown'])]))
    assert unknown.paper_ids==d.paper_ids[1:]

def test_unassessed_is_not_confirmed_and_opt_in_includes_only_typed_unreviewed(case):
    service,boards,h,_,_,_,d=fixture(case)
    dim=binding(service,h,d);cell=submit(boards,h,d,supported=False)
    with pytest.raises(MvpError,match='human-supported'):classify(service,h,d,dim,cell)
    item=classify(service,h,d,dim,cell,state='unreviewed')
    config=EvidenceViewConfig(filters=[FacetFilter(dimension='specimen',values=['stool'])])
    assert not service.query('test',h,d.board_id,d.revision_id,config).paper_ids
    assert service.query('test',h,d.board_id,d.revision_id,config.model_copy(update={'include_unreviewed':True})).paper_ids==d.paper_ids[:1]
    assert item.review_state=='unreviewed' and 'quote' not in item.references[0].model_dump()

def test_dimension_and_annotation_cas_and_wrong_paper_are_rejected(case):
    service,boards,h,_,_,_,d=fixture(case)
    dim=binding(service,h,d);cell=submit(boards,h,d);a=classify(service,h,d,dim,cell)
    with pytest.raises(MvpError,match='Another tab'):classify(service,h,d,dim,cell)
    with pytest.raises(MvpError,match='Another tab'):binding(service,h,d)
    bad=AttributePut(request_id=str(uuid4()),dimension_revision_id=dim.id,paper_id=d.paper_ids[1],origin_kind='cell',origin_id=cell.id,
        values=['stool'],review_state='confirmed',reason='Wrong paper software check')
    with pytest.raises(MvpError,match='exact current'):service.classify('test',h,d.board_id,d.revision_id,bad)
    second=classify(service,h,d,dim,cell,values=('oral',),expected=a.id)
    assert second.supersedes_id==a.id

def test_binding_change_marks_old_annotation_outdated_without_rebase(case):
    service,boards,h,_,_,_,d=fixture(case)
    dim=binding(service,h,d);classify(service,h,d,dim,submit(boards,h,d))
    binding(service,h,d,expected=dim.id)
    result=service.profiles('test',h,d.board_id,d.revision_id)
    attribute=result.papers[0].attributes[2]
    assert attribute.state=='outdated' and attribute.values==['stool','vaginal']
    assert not service.query('test',h,d.board_id,d.revision_id,EvidenceViewConfig(filters=[FacetFilter(dimension='specimen',values=['stool'])])).paper_ids

def test_named_views_append_history_cas_and_do_not_make_board_revisions(case):
    service,boards,h,_,store,_,d=fixture(case)
    before=boards.view('test',h,d.board_id).model_dump_json()
    view=service.save_view('test',h,d.board_id,d.revision_id,SavedViewPut(request_id='v1',version=0,name='Overview',config=EvidenceViewConfig(columns=['specimen','field:diet'])))
    changed=service.save_view('test',h,d.board_id,d.revision_id,SavedViewPut(request_id='v2',version=1,name='Methods',config=EvidenceViewConfig(columns=['design'])),view.id)
    assert changed.id==view.id and changed.revision_id!=view.revision_id and changed.version==2
    assert service.views('test',h,d.board_id,d.revision_id)==[changed]
    with pytest.raises(MvpError,match='Another tab'):service.save_view('test',h,d.board_id,d.revision_id,SavedViewPut(request_id='stale',version=1,name='Old tab',config=EvidenceViewConfig()),view.id)
    assert boards.view('test',h,d.board_id).model_dump_json()==before
    with store.connection()as db:assert db.execute('SELECT COUNT(*) FROM evidence_views_v1').fetchone()[0]==2

def test_current_view_export_explicit_scope_and_original_export_unchanged(case):
    service,boards,h,_,_,_,d=fixture(case)
    dim=binding(service,h,d);classify(service,h,d,dim,submit(boards,h,d))
    old=boards.export('test',h,d.board_id).model_dump_json()
    config=EvidenceViewConfig(filters=[FacetFilter(dimension='specimen',values=['stool'])])
    exported=json.loads(service.export('test',h,d.board_id,d.revision_id,config,'json'))
    assert exported['schema_version']=='mvp.evidence-view-export.v1' and exported['view']['paper_ids']==d.paper_ids[:1]
    assert 'view_config' in service.export('test',h,d.board_id,d.revision_id,config,'csv')
    assert boards.export('test',h,d.board_id).model_dump_json()==old

def test_lifecycle_delete_includes_new_tables_and_tombstone(case):
    service,boards,h,_,store,registry,d=fixture(case)
    dim=binding(service,h,d);classify(service,h,d,dim,submit(boards,h,d))
    service.save_view('test',h,d.board_id,d.revision_id,SavedViewPut(request_id='save',version=0,name='Overview',config=EvidenceViewConfig()))
    boards.delete_workspace(h.workspace_id)
    with store.connection()as db:
        assert all(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0 for table in TABLES)
    with pytest.raises(MvpError):service.profiles('test',h,d.board_id,d.revision_id)

@pytest.mark.parametrize('values,state',[([], 'value'),(['No'], 'unknown'),(['unknown'],'value'),(['stool','STOOL'],'value')])
def test_unknown_not_false_and_multivalue_bounds(values,state):
    with pytest.raises(ValidationError):AttributePut(request_id='r',dimension_revision_id='d',paper_id='p',origin_kind='cell',origin_id='c',values=values,value_state=state,reason='Software fixture')
