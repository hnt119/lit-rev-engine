import test from 'node:test';
import assert from 'node:assert/strict';
import {useState} from 'react';
import {act,create,type ReactTestInstance,type ReactTestRenderer} from 'react-test-renderer';
import Compare from '../components/compare';
import {emptyCell} from '../lib/board-drafts';
import {flushDrafts} from '../lib/drafts';
import {baseEvidenceConfig} from '../lib/evidence-views';
import type {LocationState} from '../components/workspace-app';
import type {Schema} from '../lib/api';
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(n:ReactTestInstance):string=>n.children.map(c=>typeof c==='string'?c:typeof c==='number'?String(c):text(c)).join('');
const response=(v:unknown,status=200)=>new Response(JSON.stringify(v),{status,headers:{'Content-Type':'application/json'}});
async function observed(check:()=>boolean){for(let n=0;n<200&&!check();n++)await act(async()=>{await new Promise(r=>setTimeout(r,2));});assert.ok(check(),'Expected matching view/focus acknowledgement');}

test('filtered-cell reveal waits for delayed matching result, focuses once and ignores later filters',async()=>{
 const previous={fetch:globalThis.fetch,window:(globalThis as any).window,document:(globalThis as any).document};
 const field={id:'f',revision_id:'field-revision',label:'Field',subquestion:'SYNTHETIC'},papers=['p1','p2','p3'].map(id=>({id,title:'SYNTHETIC '+id,authors:[],year:2020,pmid:null,doi:null,pmcid:null,url:''}));
 const definition={workspace_id:'focus-recovery',board_id:'board',revision_id:'revision',question:'SYNTHETIC focus case',paper_ids:papers.map(p=>p.id),papers,fields:[field],sources:[],created_at:'2026-10-26T00:00:00Z',retrieval_profile:{method:'lexical'}};
 const board={definition,current_revision_id:'revision',freshness:'current',freshness_reasons:[],cells:papers.map(p=>({paper_id:p.id,field_id:'f',head:null,draft_version:0})),definitions:[],limits:{max_fields:6}};
 const workspace={id:'focus-recovery',question:'SYNTHETIC',mode:'saved_example',searches:[],preparations:[],runs:[],assessments:[],selected_paper_ids:[]} as unknown as Schema<'WorkspaceSummary'>;
 const config={...baseEvidenceConfig([field]),filters:[{dimension:'specimen' as const,values:['stool']}]};
 const drafts=new Map<string,any>(),focus:string[]=[],calls:any[]=[];let heldRequests=0,release=()=>{},r!:ReactTestRenderer;
 const gate=new Promise<void>(resolve=>{release=resolve;});
 const target={dataset:{boardCell:'p1:f'},closest(){const row=r.root.findAllByType('tr').find(row=>row.findAllByProps({'data-board-cell':'p1:f'}).length);return row?.props.hidden?{}:null;},focus(){focus.push('original cell');},scrollIntoView(){}};
 const recovery={focus(){focus.push('recovery control');}};
 const table={scrollLeft:0,querySelectorAll(){return[target];},focus(){},scrollIntoView(){}};
 Object.assign(globalThis,{window:{history:{state:{},replaceState(v:any){this.state=v;}},location:{href:'http://localhost/'},scrollY:0,scrollTo(){},addEventListener(){},removeEventListener(){}},document:{querySelector(){return recovery;}},sessionStorage:{getItem(){return null;},setItem(){},removeItem(){}}});
 globalThis.fetch=async(input,init)=>{const url=String(input),method=init?.method??'GET',body=init?.body?JSON.parse(String(init.body)):null;calls.push({url,method,body});
  if(url.endsWith('/session'))return response({csrf_token:'synthetic'});
  if(url.endsWith('/boards'))return response({boards:[],limits:{max_fields:6}});
  if(/\/boards\/board(?:\?|$)/.test(url))return response(board);
  if(url.includes('/boards/board/drafts/'))return response({version:0,expected_cell_head_id:null,data:emptyCell()});
  if(url.includes('/drafts/')){if(!drafts.has(url))drafts.set(url,{version:1,data:url.includes('board-view')?{schema_version:'mvp.evidence-view-draft.v1',board_id:'board',board_revision_id:'revision',view_id:null,base_view_version:0,config}:{},expected_assessment_head:null});const old=drafts.get(url);if(method==='PUT')drafts.set(url,{...old,version:old.version+1,data:body.data});return response(drafts.get(url));}
  if(url.includes('/evidence-views/query')){if(!body.filters.length){heldRequests++;await gate;}const ids=body.filters.length?['p2','p3']:['p1','p2','p3'];return response({config:body,profiles:{board_id:'board',board_revision_id:'revision',freshness:'current',basis_sha256:'basis',dimensions:[],scope:'report_cooccurrence_only_not_same_cohort',papers:papers.map(p=>({paper_id:p.id,title:p.title,year:2020,availability:'abstract',attributes:[],review_status:['unknown'],pending_proposal_ids:[]}))},paper_ids:ids,groups:{'All reports':ids},unique_report_count:ids.length,group_occurrences:ids.length,facets:{specimen:['unknown']},filter_summary:body.filters.length?'specimen = stool':'All reports'});}
  if(url.includes('/evidence-views/saved'))return response([]);
  if(url.includes('/proposal-capabilities'))return response({enabled:false,reason:'Disabled software fixture'});
  if(url.includes('/proposals?'))return response({items:[],offset:0,total:0,limit:10,capability:{enabled:false,reason:'Disabled'}});
  return response({items:[],offset:0,total:0,limit:20});
 };
 function Harness(){const [location,setLocation]=useState<LocationState>({page:'compare',workspace:workspace.id,board:'board',revision:'revision',paper:'p1',field:'f'});return <Compare workspace={workspace} requestedBoard="board" requestedPaper={location.paper} requestedField={location.field} navigate={async next=>{await flushDrafts();setLocation(next);return{status:'success'};}}/>;}
 try{await act(async()=>{r=create(<Harness/>,{createNodeMock(element){return(element.props as any).className==='board-table-scroll'?table:{focus(){},scrollIntoView(){}};}});});
  await observed(()=>r.root.findAllByType('button').some(b=>text(b)==='Show this cell in the table'));
  const button=(name:string)=>r.root.findAllByType('button').find(b=>text(b)===name)!;
  await act(async()=>{await button('Back to table').props.onClick();});assert.equal(focus.at(-1),'recovery control');
  await act(async()=>{button('Show this cell in the table').props.onClick();});await observed(()=>heldRequests>0);
  assert.equal(focus.includes('original cell'),false,'Old filtered result cannot consume the queued reveal focus');
  release();await observed(()=>focus.at(-1)==='original cell');const once=focus.filter(v=>v==='original cell').length;
  const sort=r.root.findAllByType('label').find(n=>n.children.some(c=>c==='Sort reports'))!.findByType('select');
  await act(async()=>{sort.props.onChange({target:{value:'title'}});});await observed(()=>calls.some(c=>c.url.includes('/query')&&c.body.sort_by==='title'));
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,5));});assert.equal(focus.filter(v=>v==='original cell').length,once,'Consumed focus must not recur on later view changes');
 }finally{release();if(r)await act(async()=>r.unmount());globalThis.fetch=previous.fetch;for(const name of ['window','document']as const){if(previous[name]===undefined)delete(globalThis as any)[name];else(globalThis as any)[name]=previous[name];}}
});
