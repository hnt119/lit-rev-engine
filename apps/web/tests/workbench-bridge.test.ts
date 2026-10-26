import test from 'node:test';
import assert from 'node:assert/strict';
import {allowedRoute,allowedQuery} from '../lib/bridge';
const b='workspaces/w/boards/b/evidence-views',p='workspaces/w/search-plans/p';
test('workbench bridge admits only exact method/path contracts',()=>{
 for(const tail of ['profiles','saved','attributes/history','saved/v/history'])assert.equal(allowedRoute('GET',b+'/'+tail),true);
 for(const tail of ['dimensions','attributes','saved','query','exports'])assert.equal(allowedRoute('POST',b+'/'+tail),true);
 assert.equal(allowedRoute('PUT',b+'/saved/v'),true);
 for(const tail of ['metadata','strategy-export'])assert.equal(allowedRoute('GET',p+'/'+tail),true);
 assert.equal(allowedRoute('PUT',p+'/metadata'),true);
 for(const [method,route] of [['DELETE',b+'/saved/v'],['POST',p+'/strategy-export'],['POST',b+'/profiles'],['GET',b+'/unknown'],['PUT',b+'/attributes'],['GET',p+'/metadata/private']])assert.equal(allowedRoute(method,route),false);
});
test('workbench bridge bounds identifiers and excludes research text from query strings',()=>{
 const q=(x:string)=>new URLSearchParams(x);
 assert.equal(allowedQuery(b+'/query',q('revision_id=r'),'POST'),true);
 for(const text of ['revision_id=r&question=private','revision_id=r&revision_id=x','','revision_id='+'x'.repeat(201)])assert.equal(allowedQuery(b+'/query',q(text),'POST'),false);
 assert.equal(allowedQuery(b+'/exports',q('revision_id=r&format=csv'),'POST'),true);
 assert.equal(allowedQuery(b+'/exports',q('revision_id=r&format=html'),'POST'),false);
 assert.equal(allowedQuery(b+'/attributes/history',q('revision_id=r&paper_id=p&dimension_id=specimen&offset=0&limit=20')),true);
 assert.equal(allowedQuery(b+'/attributes/history',q('revision_id=r&dimension_id=specimen')),false);
 assert.equal(allowedQuery(p+'/metadata',q('revision_id=r&version=1')),true);
 assert.equal(allowedQuery(p+'/metadata',q('revision_id=r'),'PUT'),false);
 assert.equal(allowedQuery(p+'/strategy-export',q('revision_id=r&candidate_id=c&format=markdown')),true);
 assert.equal(allowedQuery(p+'/strategy-export',q('revision_id=r&candidate_id=c&query=private')),false);
 assert.equal(allowedQuery('workspaces/w/searches',q('revision_id=r'),'POST'),false);
});
