import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import ReviewPilot from "../components/review-pilot";
import {flushDrafts} from "../lib/drafts";
import {response,storage,workspace,stamp} from "./import-collection-fixtures";
import type {LocationState} from "../components/workspace-app";
import {allowedRoute,allowedQuery,boundedBody,requestByteLimit,MAX_PILOT_REQUEST_BYTES,MAX_REQUEST_BYTES} from "../lib/bridge";

(globalThis as Record<string,unknown>).IS_REACT_ACT_ENVIRONMENT=true;
function text(node:ReactTestInstance|string):string{return typeof node==="string"?node:node.children.map(child=>text(child)).join("");}
function button(r:ReactTestRenderer,label:string){return r.root.findAllByType("button").find(item=>text(item)===label)!;}
function control(r:ReactTestRenderer,label:string){const row=r.root.findAllByType("label").find(item=>text(item).trimStart().startsWith(label));assert.ok(row,label);return row.findAll(item=>["input","textarea","select"].includes(String(item.type)))[0];}
async function observed(check:()=>boolean){for(let n=0;n<100;n++){if(check())return;await act(async()=>{await new Promise(resolve=>setTimeout(resolve,5));});}assert.ok(check(),"Expected asynchronous action to complete");}
function fixture(id:string,available=true){
  Object.assign(globalThis,{sessionStorage:storage(),window:{addEventListener(){},removeEventListener(){},confirm:()=>false}});
  const calls:{path:string;method:string;body:Record<string,unknown>}[]=[],locations:LocationState[]=[];
  let draft={version:0,data:{} as Record<string,unknown>,expected_assessment_head:null},conflict=false,holdSource=false,releaseSource:(()=>void)|undefined;
  const record={id:"record",title:"PUBLIC SOFTWARE QA REPORT",abstract:"Saved abstract for software checks only.",pmid:"10001",title_abstract_state:"include",full_text_status:"not_requested",full_text_state:"pending"};
  const source={id:"document",record_id:record.id,version:1,format:"txt",source_kind:"abstract",active:true,source_sha256:"a".repeat(64),blocks_sha256:"b".repeat(64)};
  let view={available,project:{id:"project",question:"SOFTWARE QA QUESTION",title:"SOFTWARE QA"},purpose:"software_usability",current_protocol:{id:"protocol",number:1,created_at:stamp,content:{reference:"SOFTWARE QA ONLY",eligibility:{supplied_criteria:"Synthetic workflow criteria"},reviewer_roles:{declared_reviewer:"SOFTWARE QA"},fields:[{id:"exposure",label:"Diet",subquestion:"SOFTWARE QA DIET"}],unresolved:[],ready_for_screening:true}},protocols:[] as unknown[],ledger_digest:"c".repeat(64),records:[record],total_records:1,sources:[source],decisions:[],retrieval_events:[],handoffs:[] as unknown[],intakes:[],counts:{records_identified:1,unique_records:1,included_studies:null},workspace_source_revision:0,current_preparation_id:null};
  globalThis.fetch=async(input,init)=>{
    const path=String(input),method=init?.method??"GET",body=init?.body?JSON.parse(String(init.body)):{};calls.push({path,method,body});
    if(path.endsWith("/session"))return response({csrf_token:"software"});
    if(path.includes("/drafts/")){
      if(method==="PUT"){if(conflict)return response({detail:{code:"draft_conflict",message:"A newer pilot draft exists in another tab."}},409);assert.equal(body.version,draft.version);draft={...draft,version:draft.version+1,data:body.data};}return response(draft);
    }
    if(method==="GET"&&path.includes("/sources/document")){if(holdSource)await new Promise<void>(resolve=>{releaseSource=resolve;});return response({document:source,blocks:[{id:"block",ordinal:1,text:"Saved exact source text."}],total:1,next_offset:null});}
    if(method==="GET"&&path.includes("/review-pilot"))return response(path.includes("offset=50")?{...view,records:[{...record,id:"second-page",title:"SECOND PAGE SOFTWARE REPORT"}]}:view);
    if(method==="POST"&&path.endsWith("/review-pilot")){view={...view,available:true,current_protocol:{...view.current_protocol,content:body.protocol as typeof view.current_protocol.content}};return response(view);}
    if(method==="POST"&&path.endsWith("/handoffs"))return response({...view,result:{receipt:{board_id:"board",revision_id:"revision",preparation_id:"preparation"}}});
    if(method==="POST"&&path.includes("/review-pilot/"))return response({...view,ledger_digest:"d".repeat(64)});
    throw new Error("Unexpected request: "+method+" "+path);
  };
  const navigate=async(next:LocationState)=>{await flushDrafts();locations.push(next);return {status:"success" as const};};
  return {calls,locations,view,source,navigate,getDraft:()=>draft,setConflict:()=>{conflict=true;},delaySource:()=>{holdSource=true;},resolveSource:()=>{releaseSource?.();},workspace:workspace(id)};
}
async function mount(f:ReturnType<typeof fixture>){let r!:ReactTestRenderer;await act(async()=>{r=create(<ReviewPilot workspace={f.workspace} refresh={async()=>{}} navigate={f.navigate}/>);});return r;}
async function reviewer(r:ReactTestRenderer){await act(async()=>{control(r,"Reviewer label").props.onChange({target:{value:"SOFTWARE QA"}});control(r,"Reason / audit note").props.onChange({target:{value:"Explicit synthetic workflow action"}});});}

test("pilot bridge admits implemented methods only and keeps questions and ambiguous pagination out of URLs",()=>{
  const base="workspaces/owned/review-pilot";
  for(const path of [base,base+"/sources/exact",base+"/exports"])assert.equal(allowedRoute("GET",path),true);
  for(const suffix of ["","/protocols","/decisions","/retrieval-status","/sources","/handoffs","/intakes/file","/intakes/public-example","/intakes/pubmed-capture"])assert.equal(allowedRoute("POST",base+suffix),true);
  for(const suffix of ["/automatic-exclusion","/sources/exact","/exports","/intakes/live-search"])assert.equal(allowedRoute("POST",base+suffix),false);
  assert.equal(allowedRoute("DELETE",base),false);assert.equal(allowedRoute("PUT",base+"/decisions"),false);
  assert.equal(allowedQuery(base,new URLSearchParams("offset=50&limit=50")),true);
  for(const query of ["question=private","quote=private","offset=1&offset=2","limit=51","limit=0","offset=-1","offset=abc"])assert.equal(allowedQuery(base,new URLSearchParams(query)),false,query);
  assert.equal(allowedQuery(base+"/exports",new URLSearchParams("path=private")),false);
});
test("pilot body capacity is narrowly scoped to implemented JSON intake/source requests",async()=>{
  const base="workspaces/owned/review-pilot";
  for(const suffix of ["/intakes/file","/intakes/pubmed-capture","/sources"])assert.equal(requestByteLimit("POST",base+suffix,"application/json"),MAX_PILOT_REQUEST_BYTES);
  for(const suffix of ["/intakes/public-example","/decisions","/protocols","/handoffs"])assert.equal(requestByteLimit("POST",base+suffix,"application/json"),MAX_REQUEST_BYTES);
  assert.equal(requestByteLimit("POST",base+"/sources","text/plain"),MAX_REQUEST_BYTES);
  await assert.rejects(boundedBody(new Request("http://localhost",{method:"POST",headers:{"Content-Length":String(MAX_PILOT_REQUEST_BYTES+1)}}),MAX_PILOT_REQUEST_BYTES),RangeError);
});

test("pilot navigation reads retained state without executing intake, screening, retrieval or inference",async()=>{
  const f=fixture("pilot-read");const r=await mount(f);
  try{assert.match(text(r.root),/not establish authenticated, independent or dual review/);assert.match(text(r.root),/does not prove a complete query capture/);assert.match(text(r.root),/Unresolved \/ not established/);assert.equal(f.calls.some(c=>c.method==="POST"),false);assert.equal(f.calls.some(c=>/evidence-runs|preparation-jobs|proposal-runs/.test(c.path)),false);}finally{await act(async()=>r.unmount());}
});
test("isolated project creation retains unresolved protocol choices and structured self-declared roles",async()=>{
  const f=fixture("pilot-protocol",false);const r=await mount(f);
  try{await reviewer(r);await act(async()=>button(r,"Create isolated review project").props.onClick());await observed(()=>f.calls.some(c=>c.path.endsWith("/review-pilot")&&c.method==="POST"));const sent=f.calls.find(c=>c.path.endsWith("/review-pilot")&&c.method==="POST")!.body;const p=sent.protocol as {unresolved:string[];ready_for_screening:boolean;eligibility:object;reviewer_roles:object};assert.ok(p.unresolved.length>0);assert.equal(p.ready_for_screening,false);assert.equal(typeof p.eligibility,"object");assert.equal(typeof p.reviewer_roles,"object");assert.equal(sent.purpose,"research_pilot");assert.equal(f.calls.some(c=>c.path.endsWith("/decisions")),false);}finally{await act(async()=>r.unmount());}
});
test("public sample intake requires an explicit action and sends protocol and ledger heads",async()=>{
  const f=fixture("pilot-intake");const r=await mount(f);
  try{await reviewer(r);await act(async()=>button(r,"Import approved 30-record usability sample").props.onClick());await observed(()=>f.calls.some(c=>c.path.endsWith("/intakes/public-example")));const sent=f.calls.find(c=>c.path.endsWith("/intakes/public-example"))!.body;assert.equal(sent.expected_protocol_id,"protocol");assert.equal(sent.expected_ledger_digest,"c".repeat(64));assert.equal(sent.reviewer,"SOFTWARE QA");assert.ok(sent.reason);assert.equal(f.calls.some(c=>/searches|evidence-runs|decisions/.test(c.path)),false);}finally{await act(async()=>r.unmount());}
});
test("a two-tab draft conflict blocks screening and retains the editable reason",async()=>{
  const f=fixture("pilot-conflict");const r=await mount(f);
  try{await act(async()=>button(r,"PUBLIC SOFTWARE QA REPORT").props.onClick());await reviewer(r);f.setConflict();await act(async()=>button(r,"Record my screening decision").props.onClick());await observed(()=>text(r.root).includes("newer pilot draft"));assert.equal(f.calls.some(c=>c.path.endsWith("/decisions")),false);assert.equal(control(r,"Reason / audit note").props.value,"Explicit synthetic workflow action");}finally{await act(async()=>r.unmount());}
});
test("source inspection and choosing a working subset do not attach or screen; explicit handoff carries exact bindings",async()=>{
  const f=fixture("pilot-handoff");const r=await mount(f);
  try{await reviewer(r);await act(async()=>button(r,"PUBLIC SOFTWARE QA REPORT").props.onClick());await act(async()=>button(r,"Inspect retained source version 1").props.onClick());await observed(()=>text(r.root).includes("Saved exact source text."));assert.equal(f.calls.some(c=>c.path.endsWith("/sources")&&c.method==="POST"),false);await act(async()=>control(r,"Choose this exact source").props.onChange({target:{checked:true}}));assert.equal(f.calls.some(c=>c.path.endsWith("/handoffs")),false);await act(async()=>control(r,"I acknowledge any pending").props.onChange({target:{checked:true}}));await act(async()=>button(r,"Create comparison from selected exact sources").props.onClick());await observed(()=>f.locations.length===1);const sent=f.calls.find(c=>c.path.endsWith("/handoffs"))!.body;assert.deepEqual(sent.sources,[{record_id:"record",document_id:"document",source_sha256:f.source.source_sha256}]);assert.equal(sent.acknowledge_provisional,true);assert.equal(sent.expected_source_revision,0);assert.equal(sent.expected_preparation_id,null);assert.equal(f.calls.some(c=>c.path.endsWith("/decisions")||c.path.endsWith("/retrieval-status")),false);assert.deepEqual(f.locations[0],{page:"compare",workspace:f.workspace.id,board:"board",revision:"revision"});assert.equal(JSON.stringify(f.locations).includes("SOFTWARE QA"),false);}finally{await act(async()=>r.unmount());}
});


test("a library mutation preserves the selected second page rather than displaying first-page rows",async()=>{
  const f=fixture("pilot-page");f.view.total_records=60;const r=await mount(f);
  try{
    await act(async()=>button(r,"Next records").props.onClick());await observed(()=>text(r.root).includes("SECOND PAGE SOFTWARE REPORT"));
    await act(async()=>button(r,"SECOND PAGE SOFTWARE REPORT").props.onClick());await reviewer(r);
    await act(async()=>button(r,"Record my screening decision").props.onClick());await observed(()=>f.calls.some(c=>c.path.endsWith("/decisions"))&&f.calls.filter(c=>c.method==="GET"&&c.path.includes("offset=50")).length===2);
    assert.equal(r.root.findAllByProps({"aria-label":"Selected screening report"}).length,1);
    assert.equal(f.getDraft().data.offset,50);assert.equal(f.getDraft().data.record_id,"second-page");
    assert.match(text(r.root),/51–60/);assert.match(text(r.root),/SECOND PAGE SOFTWARE REPORT/);
  }finally{await act(async()=>r.unmount());}
});

test("bibliography upload preserves the exact UTF-8 BOM and Unicode input bytes",async()=>{
  const f=fixture("pilot-utf8-bytes");const r=await mount(f);
  const bytes=new TextEncoder().encode('\ufeff[ {"title":"SOFTWARE 🧬 café","authors":[]} ]\n');
  const file={name:"software.json",size:bytes.byteLength,arrayBuffer:async()=>bytes.buffer};
  try{
    await reviewer(r);await act(async()=>control(r,"File format").props.onChange({target:{value:"json"}}));
    await act(async()=>r.root.findByProps({"aria-label":"Bibliography file"}).props.onChange({target:{files:[file]}}));
    await act(async()=>button(r,"Import complete supplied file").props.onClick());await observed(()=>f.calls.some(c=>c.path.endsWith("/intakes/file")));
    const sent=f.calls.find(c=>c.path.endsWith("/intakes/file"))!.body;
    assert.deepEqual(new TextEncoder().encode(sent.content_utf8 as string),bytes);
    assert.equal(sent.filename,"software.json");assert.equal(sent.scope,"supplied_file");
  }finally{await act(async()=>r.unmount());}
});
test("invalid UTF-8 is rejected before intake instead of retaining silently replaced bytes",async()=>{
  const f=fixture("pilot-invalid-utf8");const r=await mount(f);const bytes=new Uint8Array([0xc3,0x28]);
  try{
    await reviewer(r);await act(async()=>r.root.findByProps({"aria-label":"Bibliography file"}).props.onChange({target:{files:[{name:"invalid.ris",size:2,arrayBuffer:async()=>bytes.buffer}]}}));
    await act(async()=>button(r,"Import complete supplied file").props.onClick());await observed(()=>text(r.root).includes("Choose a valid UTF-8 file"));
    assert.equal(f.calls.some(c=>c.path.endsWith("/intakes/file")),false);
    assert.equal(control(r,"Reason / audit note").props.value,"Explicit synthetic workflow action");
  }finally{await act(async()=>r.unmount());}
});


test("a delayed source response never reopens report A text beside a newly selected report B",async()=>{
  const f=fixture("pilot-delayed-source");f.view.records.push({...f.view.records[0],id:"another-record",title:"ANOTHER PUBLIC SOFTWARE REPORT"});f.view.total_records=2;f.delaySource();const r=await mount(f);
  try{
    await act(async()=>button(r,"PUBLIC SOFTWARE QA REPORT").props.onClick());
    await act(async()=>button(r,"Inspect retained source version 1").props.onClick());await observed(()=>f.calls.some(c=>c.path.includes("/sources/document")));
    await act(async()=>button(r,"ANOTHER PUBLIC SOFTWARE REPORT").props.onClick());await act(async()=>f.resolveSource());
    assert.match(text(r.root.findByProps({"aria-label":"Selected screening report"})),/ANOTHER PUBLIC SOFTWARE REPORT/);
    assert.equal(r.root.findAllByProps({"aria-label":"Retained screening source"}).length,0);assert.equal(text(r.root).includes("Saved exact source text."),false);
    assert.equal(f.calls.some(c=>c.method==="POST"),false);
  }finally{await act(async()=>r.unmount());}
});
