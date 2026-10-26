import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {act,create,type ReactTestRenderer} from 'react-test-renderer';
import {useEvidenceViews,PaperProfileDetails,type EvidenceViewsState} from '../components/evidence-views';
import {baseEvidenceConfig,evidencePreset,orderedVisibleCells} from '../lib/evidence-views';
import {flushDrafts} from '../lib/drafts';
import type {Schema} from '../lib/api';
(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
const response=(v:unknown,status=200)=>new Response(JSON.stringify(v),{status,headers:{'Content-Type':'application/json'}});
const date='2026-10-26T00:00:00Z';
const fields=['population','methods','specimen','geography','outcome'].map(id=>({id,label:id,subquestion:'Synthetic '+id,revision_id:'f-'+id}));
const config=baseEvidenceConfig(fields);
const board={definition:{workspace_id:'ws',board_id:'board',revision_id:'revision',paper_ids:['p1','p2','p3'],papers:['p1','p2','p3'].map(id=>({id,title:'Synthetic '+id,authors:[],year:2020,url:'',pmid:null,doi:null,pmcid:null})),fields,sources:[],question:'SYNTHETIC',retrieval_profile:{}},freshness:'current',cells:[],definitions:[]} as unknown as Schema<'BoardView'>;
const dimension={schema_version:'mvp.evidence-dimension.v1',id:'dimension1',workspace_id:'ws',board_id:'board',board_revision_id:'revision',dimension_id:'population',field_id:'population',field_revision_id:'f-population',label:'Population',definition:'Explicit reported population; not recruitment geography.',kind:'multi_value',supersedes_id:null,created_at:date};
const profiles={board_id:'board',board_revision_id:'revision',freshness:'current',basis_sha256:'basis',dimensions:[dimension],papers:['p1','p2','p3'].map(id=>({paper_id:id,title:'Synthetic '+id,year:2020,availability:'abstract',attributes:[],review_status:['unknown'],pending_proposal_ids:[]})),scope:'report_cooccurrence_only_not_same_cohort'};
async function settle(check:()=>boolean){for(let n=0;n<80&&!check();n++)await act(async()=>{await new Promise(r=>setTimeout(r,2));});assert.ok(check(),'Expected acknowledged UI state');}
function setup(workspace:string){
 const original=globalThis.fetch,records=new Map<string,{version:number,data:Record<string,unknown>}>(),requests:{method:string,url:string,body:any}[]=[];
 const memory=new Map<string,string>();Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:{getItem:(k:string)=>memory.get(k)??null,setItem:(k:string,v:string)=>memory.set(k,v),removeItem:(k:string)=>memory.delete(k)}});
 let namedVersion=2;
 const saved=()=>({schema_version:'mvp.saved-evidence-view.v1',revision_id:'saved-r'+namedVersion,id:'saved',workspace_id:workspace,board_id:'board',board_revision_id:'revision',version:namedVersion,name:'Overview',config,basis_sha256:'basis',paper_ids:['p1','p2','p3'],created_at:date});
 const initial={schema_version:'mvp.evidence-view-draft.v1',board_id:'board',board_revision_id:'revision',view_id:'saved',base_view_version:1,config};
 globalThis.fetch=async(input,init)=>{const url=String(input),method=init?.method??'GET',body=init?.body?JSON.parse(String(init.body)):null;requests.push({method,url,body});
  if(url.endsWith('/session'))return response({csrf_token:'software-fixture',expires_at:date});
  if(url.includes('/drafts/')){if(!records.has(url))records.set(url,{version:3,data:url.includes('board-view')?initial:{}});const old=records.get(url)!;if(method==='PUT'){assert.equal(body.version,old.version);records.set(url,{version:old.version+1,data:body.data});}return response({scope:'fixture',...records.get(url),expected_assessment_head:null,updated_at:date});}
  if(url.includes('/query'))return response({config:body,profiles,paper_ids:['p1','p2','p3'],groups:{'All reports':['p1','p2','p3']},unique_report_count:3,group_occurrences:3,facets:{population:['unknown']},filter_summary:'All reports'});
  if(url.includes('/saved/saved')&&method==='PUT'){if(body.version!==namedVersion)return response({error:{code:'stale_evidence_view',message:'Another tab changed this view.'}},409);namedVersion++;return response(saved());}
  if(url.includes('/saved'))return response([saved()]);
  throw Error('Unexpected local API '+url);
 };
 return {requests,records,restore:()=>{globalThis.fetch=original;}};
}

test('presets and visible next-cell ordering do not infer a field mapping',()=>{
 const overview=evidencePreset('Overview',fields,null),methods=evidencePreset('Methods',fields,null),needs=evidencePreset('Needs review',fields,null);
 assert.ok(overview.columns.includes('population')&&overview.columns.includes('specimen'));
 assert.deepEqual(methods.columns.filter(c=>c.startsWith('field:')),fields.map(f=>'field:'+f.id));
 assert.equal(needs.filters[0].dimension,'review_status');
 assert.deepEqual(orderedVisibleCells(['p2','p1'],fields,['field:methods']),[{paper:'p2',field:'methods'},{paper:'p1',field:'methods'}]);
});

test('reopening retains saved v1 baseline even when server has v2; only explicit inspection/rebase changes it',async()=>{
 const env=setup('view-reopen');let state:EvidenceViewsState;let renderer:ReactTestRenderer;
 function Harness(){state=useEvidenceViews('view-reopen','workspaces/view-reopen/boards/board',board);return null;}
 try{await act(async()=>{renderer=create(<Harness/>);});await settle(()=>!!state!.result&&state!.draft.ready);
  assert.equal(state!.draft.data.base_view_version,1);
  await act(async()=>{await state!.save('My stale view');});
  assert.match(state!.error,/Another tab/);assert.equal(env.requests.find(r=>r.url.includes('/saved/saved')&&r.method==='PUT')?.body.version,1);
  assert.equal(state!.draft.data.base_view_version,1);
  await act(async()=>{renderer!.unmount();renderer=create(<Harness/>);});await settle(()=>!!state!.result&&state!.draft.ready);
  assert.equal(state!.draft.data.base_view_version,1,'Refresh must not silently absorb another tab’s version');
  await act(async()=>{await state!.inspectLatest();});assert.equal(state!.inspected?.version,2);
  await act(async()=>{await state!.rebaseView();});assert.equal(state!.draft.data.base_view_version,2);
  await act(async()=>{await state!.save('Reviewed view edits');});assert.equal(state!.draft.data.base_view_version,3);
  assert.equal(env.requests.some(r=>/candidates|proposal-runs|hybrid|test-pubmed/.test(r.url)),false);
 }finally{await act(async()=>renderer!.unmount());env.restore();}
});

test('profile inputs use a separate durable scoped draft across editor navigation/remount',async()=>{
 const env=setup('profile-reopen');let state:EvidenceViewsState;let renderer:ReactTestRenderer;
 function Harness(){state=useEvidenceViews('profile-reopen','workspaces/profile-reopen/boards/board',board);return <PaperProfileDetails state={state} view={board} paperId="p1" openCell={async()=>{await flushDrafts();}}/>;}
 try{await act(async()=>{renderer=create(<Harness/>);});await settle(()=>!!state!.result);
  await act(async()=>{const details=renderer!.root.findAllByType('details')[0];const target={open:true};details.props.onToggle({target,currentTarget:target});});
  await settle(()=>env.requests.some(r=>r.url.includes('board-profile')));
  const label=()=>renderer!.root.findAllByType('label').find(n=>n.children.some(c=>c==='Dimension definition'))!.findByType('textarea');
  await settle(()=>!renderer!.root.findAllByType('fieldset')[0].props.disabled);
  await act(async()=>{label().props.onChange({target:{value:'SYNTHETIC retained classification definition'}});await flushDrafts();});
  assert.ok([...env.records.values()].some(r=>r.data.definition==='SYNTHETIC retained classification definition'));
  await act(async()=>{renderer!.unmount();renderer=create(<Harness/>);});await settle(()=>!!state!.result);
  await act(async()=>{const details=renderer!.root.findAllByType('details')[0];const target={open:true};details.props.onToggle({target,currentTarget:target});});
  await settle(()=>renderer!.root.findAllByType('label').some(n=>n.children.some(c=>c==='Dimension definition'))&&label().props.value==='SYNTHETIC retained classification definition');
  assert.equal(env.requests.some(r=>r.method==='POST'&&/attributes|dimensions/.test(r.url)),false);
 }finally{await act(async()=>renderer!.unmount());env.restore();}
});

test('reopened classification retains old provenance; value edits clear confirmation',async()=>{
 const env=setup('profile-baseline');let state:EvidenceViewsState;let renderer:ReactTestRenderer;
 const key='/api/v1/workspaces/ws/drafts/'+encodeURIComponent('board-profile:board:revision:7031');
 env.records.set(key,{version:8,data:{schema_version:'mvp.evidence-profile-draft.v1',board_id:'board',board_revision_id:'revision',paper_id:'p1',baseline_initialized:true,base_dimension_head_id:'old-dimension',base_attribute_head_id:'old-attribute',origin_cell_head_id:'old-cell',dimension_id:'population',field_id:'population',definition:'Earlier explicit definition',values:['stool'],value_state:'value',confirm:true,origin:'cell',reason:'SYNTHETIC retained earlier inputs'}});
 function Harness(){state=useEvidenceViews('profile-baseline','workspaces/profile-baseline/boards/board',board);return <PaperProfileDetails state={state} view={board} paperId="p1" openCell={async()=>{await flushDrafts();}}/>;}
 try{await act(async()=>{renderer=create(<Harness/>);});await settle(()=>!!state!.result);
  await act(async()=>{const details=renderer!.root.findAllByType('details')[0];const target={open:true};details.props.onToggle({target,currentTarget:target});});
  const input=()=>renderer!.root.findAllByType('label').find(n=>n.children.filter(c=>typeof c==='string'||typeof c==='number').join('')==='Value 1')!.findByType('input');
  await settle(()=>renderer!.root.findAllByType('label').some(n=>n.children.filter(c=>typeof c==='string'||typeof c==='number').join('')==='Value 1')&&input().props.value==='stool');
  const confirmation=()=>renderer!.root.findAllByType('label').find(n=>n.children.some(c=>typeof c==='string'&&c.startsWith('I explicitly confirm')))!.findByType('input');
  assert.equal(confirmation().props.checked,true);assert.equal(confirmation().props.disabled,true);
  await act(async()=>{input().props.onChange({target:{value:'oral'}});await flushDrafts();});assert.equal(confirmation().props.checked,false);
  const saved=env.records.get(key)!.data;assert.equal(saved.base_dimension_head_id,'old-dimension');assert.equal(saved.base_attribute_head_id,'old-attribute');assert.equal(saved.origin_cell_head_id,'old-cell');assert.deepEqual(saved.values,['oral']);
  assert.equal(env.requests.some(r=>r.method==='POST'&&/attributes|dimensions/.test(r.url)),false);
 }finally{await act(async()=>renderer!.unmount());env.restore();}
});

test('global navigation waits for held view mutation ACK and persisted baseline update',async()=>{
 const env=setup('view-held-ack');let state:EvidenceViewsState;let renderer:ReactTestRenderer;let release=()=>{};let saving:Promise<void>|undefined;
 function Harness(){state=useEvidenceViews('view-held-ack','workspaces/view-held-ack/boards/board',board);return null;}
 try{await act(async()=>{renderer=create(<Harness/>);});await settle(()=>!!state!.result&&state!.draft.ready);
  await act(async()=>{await state!.inspectLatest();});await settle(()=>state!.inspected?.version===2);await act(async()=>{await state!.rebaseView();});assert.equal(state!.draft.data.base_view_version,2);
  const mocked=globalThis.fetch;const held=new Promise<void>(resolve=>{release=resolve;});let entered=false;
  globalThis.fetch=async(input,init)=>{if(String(input).includes('/saved/saved')&&init?.method==='PUT'){entered=true;await held;}return mocked(input,init);};
  await act(async()=>{saving=state!.save('Explicit held save');await Promise.resolve();});await settle(()=>entered);
  let navigated=false;const leaving=flushDrafts().then(()=>{navigated=true;});
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,2));});assert.equal(navigated,false);
  release();await act(async()=>{await Promise.all([saving,leaving]);});
  assert.equal(navigated,true);assert.equal(state!.draft.data.base_view_version,3);assert.equal(state!.draft.state,'saved');
  assert.ok([...env.records.values()].some(record=>record.data.base_view_version===3));
 }finally{release();await saving?.catch(()=>{});await act(async()=>renderer!.unmount());env.restore();}
});
