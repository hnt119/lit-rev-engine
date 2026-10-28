"""Core suggestions are pure, authorized and equally offline in both modes."""
import pytest
from fastapi.testclient import TestClient
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.service import MVPService
from src.web_api.app import create_app

class NoProvider:
    def search(self,*args,**kwargs):raise AssertionError('No discovery allowed')
    def prepare(self,*args,**kwargs):raise AssertionError('No source request allowed')


def browser(app):
    c=TestClient(app,base_url='http://127.0.0.1:8765')
    csrf=c.get('/api/v1/session').json()['csrf_token']
    c.headers.update({'Origin':'http://127.0.0.1:3000','X-CSRF-Token':csrf})
    return c

@pytest.mark.parametrize('mode',['saved_example','live'])
def test_suggestions_preserve_research_and_require_owner_and_csrf(tmp_path,mode):
    engine=MVPService(SQLiteWorkspaceStorage(tmp_path/'engine'/'workspaces.sqlite3'),NoProvider(),NoProvider())
    app=create_app(tmp_path/'web',services={'saved_example':engine,'live':engine})
    with browser(app) as c, browser(app) as other:
        created=c.post('/api/v1/workspaces',json={'request_id':'fixture','mode':mode,'question':'Fixture only'}).json()
        base='/api/v1/workspaces/'+created['id']
        retained=c.put(base+'/drafts/discover',json={'version':0,'data':{'question':'old','query':'retained exact query'}}).json()
        request={'original_question':'How does diet affect gut microbiome in women?'}
        first=c.post(base+'/search-plan-suggestions',json=request)
        assert first.status_code==200,first.text
        assert first.json()==c.post(base+'/search-plan-suggestions',json=request).json()
        assert c.get(base).json()==created
        assert c.get(base+'/drafts/discover').json()==retained
        assert other.post(base+'/search-plan-suggestions',json=request).status_code==404
        foreign=c.post('/api/v1/workspaces',json={'request_id':'second','mode':mode,'question':'Second'}).json()
        assert c.post('/api/v1/workspaces/'+foreign['id']+'/search-plan-suggestions',json=request).status_code==200
        c.headers.pop('X-CSRF-Token')
        assert c.post(base+'/search-plan-suggestions',json=request).status_code==403


def test_invalid_suggestions_input_never_becomes_plan_or_provider_call(tmp_path):
    engine=MVPService(SQLiteWorkspaceStorage(tmp_path/'engine'/'workspaces.sqlite3'),NoProvider(),NoProvider())
    app=create_app(tmp_path/'web',services={'saved_example':engine})
    with browser(app) as c:
        w=c.post('/api/v1/workspaces',json={'request_id':'fixture','mode':'saved_example','question':'Q'}).json()['id']
        base='/api/v1/workspaces/'+w
        for value in ('', 'x'*10001):
            assert c.post(base+'/search-plan-suggestions',json={'original_question':value}).status_code==422
        assert c.get(base+'/search-plans').json()['plans']==[]


def test_generated_plan_requires_review_and_new_revision_invalidates_old_approval(tmp_path):
    engine=MVPService(SQLiteWorkspaceStorage(tmp_path/'engine'/'workspaces.sqlite3'),NoProvider(),NoProvider())
    app=create_app(tmp_path/'web',services={'live':engine})
    with browser(app) as c:
        w=c.post('/api/v1/workspaces',json={'request_id':'fixture','mode':'live','question':'Q'}).json()['id']
        base='/api/v1/workspaces/'+w
        draft=c.post(base+'/search-plan-suggestions',json={'original_question':'How does diet affect gut microbiome in women?'}).json()['draft']
        unreviewed=c.post(base+'/search-plans',json={'request_id':'unreviewed','draft':draft}).json()
        assert not unreviewed['revision']['compiled']['candidates']
        for concept in draft['concepts']:
            concept.update(requirement='required',retrieval_use='query')
            for term in concept['terms']:term['state']='approved'
        draft['variants']=[{'id':'reviewed','label':'Reviewed focused','kind':'focused','expression':{'op':'all_of','children':[{'op':'concept_ref','concept_id':x['id']} for x in draft['concepts']]}}]
        view=c.post(base+'/search-plans',json={'request_id':'reviewed','draft':draft}).json()
        compiled=view['revision']['compiled']['candidates'][0]
        assert compiled['status']=='ready_for_approval'
        assert compiled['query']=='((diet) AND (gut microbiome OR gut microbiota) AND (women))'
        endpoint=base+'/search-plans/'+view['revision']['plan_id']
        def binding(v,request):
            candidate=v['revision']['compiled']['candidates'][0]
            return {'request_id':request,'expected_revision_id':v['revision']['revision_id'],'candidate_id':candidate['id'],'candidate_sha256':candidate['candidate_sha256']}
        approval=c.post(endpoint+'/approve',json=binding(view,'approve'))
        assert approval.status_code==200,approval.text
        draft['concepts'][0]['terms'][0].update(text='dietary intake',origin='manual')
        revised=c.put(endpoint,json={'request_id':'revised','expected_revision_id':view['revision']['revision_id'],'draft':draft}).json()
        stale=c.post(endpoint+'/execute',json={**binding(revised,'stale-execution'),'approval_id':approval.json()['id']})
        assert stale.status_code==409 and stale.json()['error']['code']=='stale_search_approval'
        assert c.get(base).json()['searches']==[]
