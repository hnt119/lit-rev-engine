import assert from 'node:assert/strict';
import test from 'node:test';
import {act,create,type ReactTestInstance,type ReactTestRenderer} from 'react-test-renderer';
import WorkspaceEntry,{latestComparison} from '../components/workspace-entry';
import {WorkspaceNavigationMemory} from '../lib/workspace-navigation-memory';
import type {LocationState} from '../components/workspace-app';
import type {Schema} from '../lib/api';

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==='string'?child:text(child)).join('');
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const workspace=(id='w'):Schema<'WorkspaceSummary'>=>({id,question:'A question about imported papers',mode:'live',created_at:'2026-11-21T00:00:00Z',source_revision:0,current_preparation_id:null,selected_paper_ids:[],current_run_id:null,current_assessment_ids:{},searches:[],preparations:[],runs:[],assessments:[]});
const board=(id='b',created_at='2026-11-21T00:00:00Z'):Schema<'BoardSummary'>=>({board_id:id,revision_id:'r/'+id,question:'Saved comparison '+id,paper_count:3,field_count:3,created_at,preparation_id:'prep',paper_ids:['p1','p2','p3']});
function button(renderer:ReactTestRenderer,label:string){const found=renderer.root.findAllByType('button').find(node=>text(node)===label);assert.ok(found,'Missing '+label);return found;}

test('page switching keeps exact historical comparison and passage scope in this session',()=>{
  const memory=new WorkspaceNavigationMemory();
  const comparison:LocationState={page:'compare',workspace:'w',board:'b',revision:'historic-r',paper:'p',field:'f'};
  memory.remember(comparison);
  memory.remember({page:'history',workspace:'w'});
  memory.remember({...comparison,page:'settings',settingsReturn:'compare'});
  assert.deepEqual(memory.destination('compare','w'),comparison);
  const destination=memory.destination('compare','w');destination.paper='changed';
  assert.equal(memory.destination('compare','w').paper,'p','caller cannot mutate remembered context');
  memory.remember({page:'evidence',workspace:'w',run:'run',board:'b',revision:'r',paper:'p',field:'f'});
  assert.equal(memory.destination('evidence','w').run,'run');
  assert.deepEqual(memory.destination('compare','other'),{page:'compare',workspace:'other'});
  memory.retain(['other']);assert.deepEqual(memory.destination('compare','w'),{page:'compare',workspace:'w'});
});

test('returning to a page never replays preparation, board creation or source attachment handoffs',()=>{
  const memory=new WorkspaceNavigationMemory();
  memory.remember({page:'compare',workspace:'w',board:'b',revision:'r',paper:'p',field:'f',setup:'new',preparation:'prep',handoff:'handoff',run:'run',passage:'passage',returnTo:'cell',settingsReturn:'compare',settingsSection:'ai'});
  assert.deepEqual(memory.destination('compare','w'),{page:'compare',workspace:'w',board:'b',revision:'r',paper:'p',field:'f'});
  memory.remember({page:'discover',workspace:'w',collection:'imported',intake:'collections',plan:'plan',planRevision:'pr',focusResult:'one-shot'});
  assert.deepEqual(memory.destination('discover','w'),{page:'discover',workspace:'w',collection:'imported',plan:'plan',planRevision:'pr',intake:'collections'});
  assert.deepEqual(new WorkspaceNavigationMemory().destination('compare','w'),{page:'compare',workspace:'w'},'a new app session has no false last-visited claim');
});

test('latest comparison is selected by definition time without mutating the API list',()=>{
  const old=board('older','2026-11-20T00:00:00Z'),latest=board('newer');
  const listing=[old,latest];assert.equal(latestComparison(listing),latest);assert.deepEqual(listing,[old,latest]);assert.equal(latestComparison([]),undefined);
});

test('an import-only workspace reopens a pinned saved comparison through guarded navigation using only metadata reads',async()=>{
  const originalFetch=globalThis.fetch,requests:{path:string;method:string}[]=[],routes:LocationState[]=[];let renderer!:ReactTestRenderer;
  globalThis.fetch=async(url,options)=>{const path=String(url);requests.push({path,method:options?.method??'GET'});if(path.endsWith('/session'))return response({csrf_token:'fixture'});assert.equal(path,'/api/v1/workspaces/w/boards');return response({boards:[board('old','2026-11-20T00:00:00Z'),board()],limits:{max_fields:6}});};
  try{
    await act(async()=>{renderer=create(<WorkspaceEntry workspace={workspace()} comparisonDestination={{page:'compare',workspace:'w'}} navigate={async next=>{routes.push(next);return {status:'blocked',message:'Keep unsaved edits'};}}/>);});
    assert.ok(text(renderer.root).includes('2 saved comparisons'));
    await act(async()=>button(renderer,'Open latest comparison').props.onClick());
    assert.deepEqual(routes,[{page:'compare',workspace:'w',board:'b',revision:'r/b'}]);
    assert.ok(renderer.root.findAllByType('button').some(node=>text(node)==='Open latest comparison'),'blocked navigation does not remove the card');
    assert.ok(requests.every(request=>request.method==='GET'));assert.equal(requests.filter(request=>request.path.endsWith('/boards')).length,1);
  }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;}
});

test('a same-session return keeps the chosen historical revision and cell instead of replacing it with latest',async()=>{
  const originalFetch=globalThis.fetch,routes:LocationState[]=[];let renderer!:ReactTestRenderer;
  globalThis.fetch=async()=>response({boards:[board()]});
  const remembered:LocationState={page:'compare',workspace:'w',board:'b',revision:'old-revision',paper:'p2',field:'design'};
  try{
    await act(async()=>{renderer=create(<WorkspaceEntry workspace={workspace()} comparisonDestination={remembered} navigate={async next=>{routes.push(next);}}/>);});
    await act(async()=>button(renderer,'Return to comparison').props.onClick());assert.deepEqual(routes,[remembered]);
  }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;}
});

test('failed metadata loading keeps manual routes usable and an explicit retry does not infer an empty workspace',async()=>{
  const originalFetch=globalThis.fetch;let renderer!:ReactTestRenderer,calls=0;
  globalThis.fetch=async()=>++calls===1?response({detail:{code:'unavailable',message:'Saved comparisons unavailable'}},503):response({boards:[]});
  try{
    await act(async()=>{renderer=create(<WorkspaceEntry workspace={workspace()} comparisonDestination={{page:'compare',workspace:'w'}} navigate={async()=>{}}/>);});
    assert.ok(!text(renderer.root).includes('No saved comparison yet'));
    assert.equal(button(renderer,'Find or import papers').props.disabled,undefined);
    await act(async()=>button(renderer,'Retry saved comparisons').props.onClick());
    assert.ok(text(renderer.root).includes('No saved comparison yet'));assert.equal(calls,2);
  }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;}
});

test('late workspace metadata cannot expose another workspace comparison after navigation',async()=>{
  const originalFetch=globalThis.fetch;let renderer!:ReactTestRenderer,release!:(value:Response)=>void;
  globalThis.fetch=async url=>String(url).includes('/workspaces/first/')?new Promise(resolve=>{release=resolve;}):response({boards:[board('second')]});
  const props={navigate:async()=>{}};
  try{
    await act(async()=>{renderer=create(<WorkspaceEntry {...props} workspace={workspace('first')} comparisonDestination={{page:'compare',workspace:'first'}}/>);});
    await act(async()=>renderer.update(<WorkspaceEntry {...props} workspace={workspace('second')} comparisonDestination={{page:'compare',workspace:'second'}}/>));
    await act(async()=>release(response({boards:[board('wrong-workspace')]})));
    assert.ok(text(renderer.root).includes('Saved comparison second'));assert.ok(!text(renderer.root).includes('wrong-workspace'));
  }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;}
});
