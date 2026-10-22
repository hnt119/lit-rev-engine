import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestRenderer,type ReactTestInstance} from "react-test-renderer";
import PreparationJobs from "../components/preparation-jobs.tsx";
import Discover from "../components/discover.tsx";
import type {Schema} from "../lib/api.ts";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
type Job=Schema<"PreparationJobView">;
type Props=Parameters<typeof PreparationJobs>[0];
const response=(value:unknown)=>new Response(JSON.stringify(value),{headers:{"Content-Type":"application/json"}});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
const button=(renderer:ReactTestRenderer,label:string)=>renderer.root.findAllByType("button").find(item=>text(item)===label)!;
const deferred=<T,>()=>{let resolve!:(value:T)=>void;const promise=new Promise<T>(done=>resolve=done);return{promise,resolve};};

function fixtures(id:string){
  const papers:Schema<"Paper">[]=Array.from({length:32},(_,index)=>({id:`software:${index}`,title:`SOFTWARE PREPARATION PAPER ${index}`,authors:[],year:2020,abstract:"Synthetic software fixture only.",pmid:null,doi:null,pmcid:null,url:""}));
  const search:Schema<"SearchPreview">={schema_version:"mvp.exploratory-preview.v1",id:"search-"+id,query:"SOFTWARE QUERY",research_question:"SOFTWARE QUESTION",query_translation:null,searched_at:"2026-10-21T00:00:00Z",sort:"relevance",date_from:null,date_to:null,total_reported:32,fetched_count:32,ordered_identifiers:papers.map(p=>p.id),papers,warnings:[],truncated:false,provider:"software-test",mode:"test",errors:[]};
  const workspace:Schema<"WorkspaceSummary">={id:"workspace-"+id,question:"SOFTWARE QUESTION",mode:"saved_example",created_at:search.searched_at,source_revision:1,current_preparation_id:"old-preparation",selected_paper_ids:[papers[0].id],current_run_id:null,current_assessment_ids:{},searches:[],preparations:[],runs:[],assessments:[]};
  const makeJob=(extra:Partial<Job>={}):Job=>({schema_version:"mvp.preparation-job.v1",id:"job-"+id,workspace_id:workspace.id,search_id:search.id,search_snapshot_sha256:"f".repeat(64),selected_paper_ids:papers.slice(0,30).map(p=>p.id),expected_source_revision:1,expected_preparation_id:"old-preparation",status:"queued",attempt:1,max_attempts:3,progress_completed:0,progress_total:30,active_paper_id:null,elapsed_seconds:0,max_runtime_seconds:2400,interrupted_count:0,result_preparation_id:null,result_source_revision:null,error:null,outcomes:papers.slice(0,30).map((p,index)=>({paper_id:p.id,position:index+1,outcome:"pending",source_id:null,source_type:null,source_status:null,error:null})),created_at:search.searched_at,updated_at:search.searched_at,...extra});
  const preparation:Schema<"PreparationView">={id:"published-preparation",search_id:search.id,source_revision:2,selected_paper_ids:papers.slice(0,30).map(p=>p.id),prepared_at:search.searched_at,selection_state:"selected_for_exploration",sources:[],errors:[]};
  return{papers,search,workspace,makeJob,preparation};
}

async function harness(id:string,handler:(request:{path:string;method:string;body:any},fixture:ReturnType<typeof fixtures>)=>unknown|Promise<unknown>,initial:Partial<Props>={}){
  const fixture=fixtures(id),requests:{path:string;method:string;body:any}[]=[],published:string[]=[];
  const originalFetch=globalThis.fetch,storageDescriptor=Object.getOwnPropertyDescriptor(globalThis,"sessionStorage"),stored=new Map<string,string>();
  Object.defineProperty(globalThis,"sessionStorage",{configurable:true,value:{getItem:(key:string)=>stored.get(key)??null,setItem:(key:string,value:string)=>stored.set(key,value),removeItem:(key:string)=>stored.delete(key)}});
  globalThis.fetch=async(url,options)=>{
    const request={path:String(url),method:options?.method??"GET",body:options?.body?JSON.parse(String(options.body)):undefined};requests.push(request);
    if(request.path.endsWith("/session"))return response({csrf_token:"software-preparation"});
    return response(await handler(request,fixture));
  };
  let flushes=0,refreshes=0;
  let props:Props={...fixture,selectedPaperIds:fixture.papers.slice(0,30).map(p=>p.id),selectionReady:true,maxSources:30,flushSelection:async()=>{flushes++;},refresh:async()=>{refreshes++;},onPublished:value=>published.push(value.id),...initial};
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<PreparationJobs {...props}/>);});
  return{...fixture,renderer,requests,published,stored,get flushes(){return flushes;},get refreshes(){return refreshes;},async update(extra:Partial<Props>){props={...props,...extra};await act(async()=>renderer.update(<PreparationJobs {...props}/>));},async cleanup(){await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;if(storageDescriptor)Object.defineProperty(globalThis,"sessionStorage",storageDescriptor);else Reflect.deleteProperty(globalThis,"sessionStorage");}};
}

test("opening/reopening reads saved jobs only, polls progress and publishes source metadata only when the result is current",async context=>{
  context.mock.timers.enable({apis:["setTimeout"]});let polls=0;
  const h=await harness("reopen",(r,f)=>{
    if(r.path.includes("preparation-jobs?"))return{jobs:[f.makeJob({status:"running",progress_completed:1})]};
    if(r.path.includes("/preparation-jobs/")){polls++;return f.makeJob({status:"succeeded",progress_completed:30,result_preparation_id:f.preparation.id,result_source_revision:2});}
    if(r.path.includes("/source-preparations/"))return f.preparation;
    if(r.path.endsWith("/"+f.workspace.id))return{...f.workspace,current_preparation_id:f.preparation.id,source_revision:2};
    assert.fail(`Unexpected ${r.method} ${r.path}`);
  });
  try{
    assert.equal(h.requests.every(r=>r.method==="GET"),true);
    assert.equal(h.published.length,0,"the previous prepared sources remain untouched while running");
    await act(async()=>context.mock.timers.tick(1500));
    assert.equal(polls,1);assert.deepEqual(h.published,[h.preparation.id]);assert.equal(h.refreshes,1);
    await act(async()=>context.mock.timers.tick(20000));assert.equal(polls,1,"terminal jobs stop automatic polling");
    assert.match(text(h.renderer.root),/Completion includes the recorded abstract-only, unavailable and failed outcomes/);
    assert.equal(h.requests.every(r=>r.method==="GET"),true);
  }finally{await h.cleanup();}
});

test("submitting thirty papers freezes ordered input before draft flushing and keeps later selection edits separate",async()=>{
  const gate=deferred<void>();let submitted:any;
  const h=await harness("frozen",(r,f)=>{
    if(r.path.includes("preparation-jobs?"))return{jobs:[]};
    if(r.method==="POST"&&r.path.endsWith("/preparation-jobs")){submitted=r.body;return{job:f.makeJob(),reused:false};}
    assert.fail(`Unexpected ${r.method} ${r.path}`);
  },{flushSelection:()=>gate.promise});
  try{
    const original=h.papers.slice(0,30).map(p=>p.id);
    let submission!:Promise<void>;
    act(()=>{submission=button(h.renderer,"Prepare selected sources").props.onClick();});
    assert.equal(submitted,undefined,"provider work cannot start before the draft flush");
    await h.update({selectedPaperIds:[h.papers[31].id]});
    await act(async()=>{gate.resolve();await submission;});
    const confirmed=h.requests.find(request=>request.method==="POST")?.body;assert.ok(confirmed);
    assert.deepEqual(confirmed.paper_ids,original);assert.equal(confirmed.expected_source_revision,1);assert.equal(confirmed.expected_preparation_id,"old-preparation");
    assert.match(text(h.renderer.root),/selection differs from this job's frozen input/);
    assert.equal(h.published.length,0);assert.equal(h.refreshes,0);
    assert.equal(h.requests.filter(r=>r.method==="POST").length,1);
    for(const value of h.stored.values())assert.deepEqual(Object.keys(JSON.parse(value)).sort(),["fingerprint","request_id"],"browser storage retains opaque retry identity, not paper metadata");
  }finally{await h.cleanup();}
});

test("an ambiguous submission retries the exact request id and original input without reflushing changed selection",async()=>{
  let posts=0;
  const h=await harness("retry",(r,f)=>{
    if(r.path.includes("preparation-jobs?"))return{jobs:[]};
    if(r.method==="POST"){if(++posts===1)throw new Error("SOFTWARE TEST connection lost after queueing");return{job:f.makeJob(),reused:true};}
    assert.fail(`Unexpected ${r.method} ${r.path}`);
  });
  try{
    await act(async()=>button(h.renderer,"Prepare selected sources").props.onClick());
    assert.match(text(h.renderer.root),/submission result is unresolved/);
    await h.update({selectedPaperIds:[h.papers[31].id]});
    await act(async()=>button(h.renderer,"Retry same submission").props.onClick());
    const submitted=h.requests.filter(r=>r.method==="POST");
    assert.equal(submitted.length,2);assert.deepEqual(submitted[0].body,submitted[1].body);assert.equal(h.flushes,1);
    assert.equal(h.renderer.root.findAllByType("button").some(b=>text(b)==="Retry same submission"),false);
  }finally{await h.cleanup();}
});

test("cancellation invalidates an older in-flight poll and never changes the clicked selection",async context=>{
  context.mock.timers.enable({apis:["setTimeout"]});const delayed=deferred<Job>();let polls=0;
  const h=await harness("cancel",(r,f)=>{
    if(r.path.includes("preparation-jobs?"))return{jobs:[f.makeJob({status:"running"})]};
    if(r.method==="POST"&&r.path.endsWith("/cancel"))return f.makeJob({status:"cancel_requested",updated_at:"2026-10-21T00:00:02Z"});
    if(r.path.includes("/preparation-jobs/")){if(++polls===1)return delayed.promise;return f.makeJob({status:"cancelled"});}
    assert.fail(`Unexpected ${r.method} ${r.path}`);
  });
  try{
    await act(async()=>context.mock.timers.tick(1500));
    await act(async()=>button(h.renderer,"Cancel preparation").props.onClick());
    await act(async()=>delayed.resolve(h.makeJob({status:"running"})));
    assert.match(text(h.renderer.root),/cancel requested/);
    assert.equal(button(h.renderer,"Cancellation requested").props.disabled,true);
    await act(async()=>context.mock.timers.tick(1500));
    assert.match(text(h.renderer.root),/cancelled/);assert.equal(h.published.length,0);
    assert.equal(h.requests.filter(r=>r.method==="POST").length,1);assert.deepEqual(h.requests.find(r=>r.method==="POST")?.body,{});
  }finally{await h.cleanup();}
});

test("a delayed poll cannot replace a newly inspected saved job, and unmount stops subsequent reads",async context=>{
  context.mock.timers.enable({apis:["setTimeout"]});const delayed=deferred<Job>();let polls=0;
  const h=await harness("switch",(r,f)=>{
    if(r.path.includes("preparation-jobs?"))return{jobs:[f.makeJob({status:"running"}),f.makeJob({id:"older-failed",status:"failed",created_at:"2026-10-20T00:00:00Z"})]};
    if(r.path.includes("/preparation-jobs/")){polls++;return delayed.promise;}
    assert.fail(`Unexpected ${r.method} ${r.path}`);
  });
  try{
    await act(async()=>context.mock.timers.tick(1500));
    await act(async()=>h.renderer.root.findByType("select").props.onChange({target:{value:"older-failed"}}));
    await act(async()=>delayed.resolve(h.makeJob({status:"running",progress_completed:12})));
    assert.match(text(h.renderer.root),/PREPARATION JOB older-failed/);
    assert.equal(h.requests.filter(r=>r.method==="POST").length,0);
  }finally{await h.cleanup();}
  context.mock.timers.tick(10000);assert.equal(polls,1);
});

test("historical successful preparations never replace newer current sources",async()=>{
  const h=await harness("historical",(r,f)=>{
    if(r.path.includes("preparation-jobs?"))return{jobs:[f.makeJob({status:"succeeded",result_preparation_id:f.preparation.id,result_source_revision:2,progress_completed:30})]};
    if(r.path.includes("/source-preparations/"))return f.preparation;
    if(r.path.endsWith("/"+f.workspace.id))return{...f.workspace,current_preparation_id:"newer-preparation",source_revision:3};
    assert.fail(`Unexpected ${r.method} ${r.path}`);
  });
  try{assert.deepEqual(h.published,[]);assert.equal(h.refreshes,1);assert.equal(h.requests.every(r=>r.method==="GET"),true);}
  finally{await h.cleanup();}
});

test("zero or thirty-one selected papers cannot submit a preparation, and draft failure starts no job",async()=>{
  const h=await harness("limits",(r)=>{assert.equal(r.method,"GET");assert.match(r.path,/preparation-jobs\?/);return{jobs:[]};},{selectedPaperIds:[]});
  try{
    assert.equal(button(h.renderer,"Prepare selected sources").props.disabled,true);
    await h.update({selectedPaperIds:h.papers.slice(0,31).map(p=>p.id)});
    assert.equal(button(h.renderer,"Prepare selected sources").props.disabled,true);
    await act(async()=>button(h.renderer,"Prepare selected sources").props.onClick());
    await h.update({selectedPaperIds:[h.papers[0].id],flushSelection:async()=>{throw new Error("SOFTWARE TEST draft conflict");}});
    await act(async()=>button(h.renderer,"Prepare selected sources").props.onClick());
    assert.match(text(h.renderer.root),/draft conflict/);assert.equal(h.requests.filter(r=>r.method==="POST").length,0);
  }finally{await h.cleanup();}
});

test("visible outcome counts distinguish full text, abstract fallback, unavailable, failed and unfinished papers",async()=>{
  const h=await harness("availability",(r,f)=>{
    assert.equal(r.method,"GET");assert.match(r.path,/preparation-jobs\?/);
    const original=f.makeJob(),states=["full_text","abstract_only","unavailable","failed","cancelled","preparing"] as const;
    const outcomes=original.outcomes.map((outcome,index)=>({...outcome,outcome:states[index]??"pending",source_type:index===0?"full_text" as const:index===1||index===3?"abstract" as const:null}));
    return{jobs:[{...original,status:"running",progress_completed:5,outcomes}]};
  });
  try{
    const summary=text(h.renderer.root.findByProps({"aria-label":"Per-paper preparation outcome counts"}));
    assert.match(summary,/1 full text · 1 abstract only · 1 unavailable · 1 failed · 1 cancelled · 24 pending · 1 preparing/);
    assert.match(summary,/1 failed outcome\(s\) retain an abstract fallback/);
    assert.equal(h.requests.filter(r=>r.method==="POST").length,0);
  }finally{await h.cleanup();}
});

test("a late initial listing cannot replace the current saved-search job view",async()=>{
  const delayed=deferred<{jobs:Job[]}>();
  const h=await harness("scope",(r)=>{
    assert.equal(r.method,"GET");assert.match(r.path,/preparation-jobs\?/);
    return r.path.endsWith("search_id=other-search")?{jobs:[]}:delayed.promise;
  });
  try{
    await h.update({search:{...h.search,id:"other-search"}});
    await act(async()=>delayed.resolve({jobs:[h.makeJob({status:"running"})]}));
    assert.equal(h.renderer.root.findAllByProps({"aria-label":"Preparation job receipt"}).length,0);
    assert.equal(button(h.renderer,"Prepare selected sources").props.disabled,false);
  }finally{await h.cleanup();}
});

test("a late previous-preparation read cannot overwrite a newly published thirty-paper preparation in Discover",async()=>{
  const f=fixtures("discover-publication"),older=deferred<Schema<"PreparationView">>();
  const previous={...f.preparation,id:"old-preparation",source_revision:1,selected_paper_ids:[f.papers[0].id]};
  const workspace={...f.workspace,preparations:[previous],searches:[{...f.search,distinct_count:32}]};
  const capabilities={default_mode:"saved_example",live_available:false,saved_example:{query:f.search.query,question:f.search.research_question},limits:{max_prepared_sources:30,max_sources:30,max_synchronous_prepared_sources:10},preparation_jobs_ready:true,search_plans_ready:false,board_span_profiles:null,boards:{max_fields:6,max_cells:60,max_boards:10,max_definition_revisions:20,max_cell_revisions:50,max_references:5,max_workspace_bytes:33554432,max_candidate_characters:1200,max_inspector_characters:4000},map:{ready:false,reason:"SOFTWARE TEST no embeddings"}} as Schema<"Capabilities">;
  const original=globalThis.fetch;
  globalThis.fetch=async(url,options)=>{
    assert.equal(options?.method??"GET","GET");const path=String(url);
    if(path.endsWith("/session"))return response({csrf_token:"software-preparation"});
    if(path.endsWith("/papers"))return response(f.search);
    if(path.includes("/maps?"))return response({maps:[],jobs:[]});
    if(path.includes("/drafts/"))return response({scope:decodeURIComponent(path.split("/").at(-1)!),version:0,data:{},expected_assessment_head:null,updated_at:null});
    if(path.includes("/preparation-jobs?"))return response({jobs:[f.makeJob({status:"succeeded",progress_completed:30,result_preparation_id:f.preparation.id,result_source_revision:2})]});
    if(path.endsWith("/source-preparations/old-preparation"))return response(await older.promise);
    if(path.endsWith("/source-preparations/"+f.preparation.id))return response(f.preparation);
    if(path.endsWith("/"+workspace.id))return response({...workspace,current_preparation_id:f.preparation.id,source_revision:2});
    assert.fail(`Unexpected ${path}`);
  };
  let renderer!:ReactTestRenderer;
  try{
    await act(async()=>{renderer=create(<Discover workspace={workspace} capabilities={capabilities} refresh={async()=>{}} navigate={async()=>{}}/>);});
    assert.match(text(renderer.root),/30 prepared/);
    await act(async()=>older.resolve(previous));
    assert.match(text(renderer.root),/30 prepared/);
  }finally{await act(async()=>renderer.unmount());globalThis.fetch=original;}
});
