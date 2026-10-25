import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Compare from "../components/compare.tsx";
import {emptyCell,type CellData} from "../lib/board-drafts.tsx";
import {flushDrafts} from "../lib/drafts.tsx";
import type {Schema} from "../lib/api.ts";

// Independently authored UI acceptance fixtures. Quotations are synthetic;
// these checks do not validate retrieval relevance or human interpretation.
const pending=new Map<string,string>();
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,sessionStorage:{getItem:(key:string)=>pending.get(key)??null,setItem:(key:string,value:string)=>pending.set(key,value),removeItem:(key:string)=>pending.delete(key)}});
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}});
function text(node:ReactTestInstance):string{return node.children.map(child=>typeof child==="string"?child:text(child)).join("");}
function button(renderer:ReactTestRenderer,label:string){const node=renderer.root.findAllByType("button").find(node=>text(node)===label);assert.ok(node,"Missing button: "+label);return node;}
function control(renderer:ReactTestRenderer,label:string,type:"textarea"|"select"|"input"="textarea"){const node=renderer.root.findAllByType("label").find(node=>node.children.some(child=>child===label));assert.ok(node,"Missing control: "+label);return node.findByType(type);}
function disabled(node:ReactTestInstance){for(let n:ReactTestInstance|null=node;n;n=n.parent)if(n.props.disabled)return true;return false;}
function step(renderer:ReactTestRenderer){return text(renderer.root.findByProps({"aria-label":"Cell review steps"}).findByProps({"aria-current":"step"}));}
async function click(renderer:ReactTestRenderer,label:string){
 // Event handlers deliberately return void. Observe the rendered, enabled
 // control rather than assuming an earlier asynchronous action has finished.
 let target:ReactTestInstance|undefined;
 for(let attempt=0;attempt<100;attempt++){
  target=renderer.root.findAllByType("button").find(node=>text(node)===label&&!disabled(node));
  if(target)break;
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,10));});
 }
 assert.ok(target,"Missing enabled button: "+label);
 await act(async()=>{await target.props.onClick();});
}
async function change(renderer:ReactTestRenderer,label:string,value:string,type:"textarea"|"select"|"input"="textarea"){await act(async()=>control(renderer,label,type).props.onChange({target:{value}}));}

async function fixture(id:string,{historical=false,long=false,empty=false,providerFailure=false}={}){
 const sourceText=long?"女性😀 exact canonical evidence. ".repeat(230):"女性😀 participants were adults. Allocation details were not retained.";
 const chars=Array.from(sourceText),date="2026-10-25T00:00:00Z";
 const papers=[1,2,3].map(i=>({id:"p"+i,title:"SYNTHETIC SOFTWARE REPORT "+i,authors:["Fixture"],year:2026,pmid:null,doi:null,pmcid:null,url:null}));
 const sources=papers.map((p,i)=>({source_id:"s"+(i+1),paper_id:p.id,version:"v1",source_sha256:"a".repeat(64),blocks_sha256:"b".repeat(64),parser_id:"synthetic",source_type:i===2?"none":i===1?"abstract":"full_text",status:i===2?"unavailable":i===1?"abstract_only":"full_text_available",block_count:i===2?0:1}));
 const fields=[{id:"finding",revision_id:"field-v1",label:"Finding",subquestion:"SOFTWARE TEST: what exact detail is retained?"}];
 const definition={board_id:"board",revision_id:"rev",workspace_id:id,parent_revision_id:null,search_id:"search",search_sha256:"c".repeat(64),question:"SYNTHETIC SOFTWARE EVALUATION ONLY",question_sha256:"d".repeat(64),preparation_id:"prep",source_revision:1,source_manifest_sha256:"e".repeat(64),papers,paper_ids:papers.map(p=>p.id),sources,fields,retrieval_profile:{method:"lexical"},retrieval_profile_sha256:"f".repeat(64),created_at:date};
 const summary={board_id:"board",revision_id:"rev",question:definition.question,paper_count:3,field_count:1,created_at:date};
 const view={definition,current_revision_id:"rev",freshness:historical?"historical":"current",freshness_reasons:historical?["Retained historical definition"]:[],cells:papers.map(p=>({paper_id:p.id,field_id:"finding",head:null as any,draft_version:0})),definitions:[summary],limits:{max_fields:6}};
 const workspace={id,question:definition.question,mode:"saved_example",created_at:date,source_revision:1,current_preparation_id:"prep",selected_paper_ids:definition.paper_ids,current_run_id:null,current_assessment_ids:{},searches:[],preparations:[{id:"prep",search_id:"search",selected_paper_ids:definition.paper_ids,source_revision:1,prepared_at:date}],runs:[],assessments:[]} as unknown as Schema<"WorkspaceSummary">;
 const drafts=new Map<string,any>(),editorDrafts=new Map<string,any>(),requests:{path:string;method:string;body:any}[]=[],revisions:any[]=[],navigation:any[]=[],focus:string[]=[];
 let gate:Promise<void>|null=null,releaseAck:(()=>void)|null=null,hintConflict=false,wrongPaper=false;
 const reference=(paper:string,start=0,end=Math.min(chars.length,long?4500:chars.length))=>({id:"ref-"+paper+"-"+start,paper_id:paper,source_id:"s"+paper.slice(1),source_version:"v1",source_sha256:"a".repeat(64),blocks_sha256:"b".repeat(64),block_id:"block-"+paper,start,end,quote:chars.slice(start,end).join(""),locator:{section:"Synthetic source"},integrity:"checked"});
 globalThis.fetch=async(url,options)=>{
  const path=String(url),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):null;requests.push({path,method,body});
  if(path.endsWith("/session"))return response({csrf_token:"fixture"});
  if(path.endsWith("/boards"))return response({boards:[summary],limits:{max_fields:6}});
  if(path.endsWith("/boards/board"))return response(view);
  if(path.includes("/drafts/board-editor%3A")){
   let old=editorDrafts.get(path)??{version:0,data:{},expected_assessment_head:null};
   if(method==="GET")return response(old);
   if(hintConflict){hintConflict=false;old={...old,version:old.version+1};editorDrafts.set(path,old);return response({detail:{code:"stale_draft",message:"Another tab changed the editor view"}},409);}
   assert.equal(body.version,old.version);const saved={...body,version:old.version+1};editorDrafts.set(path,saved);return response(saved);
  }
  if(path.includes("/drafts/")){
   const match=path.match(/\/drafts\/([^/]+)\/([^/?]+)/)!;const paper=decodeURIComponent(match[1]),field=decodeURIComponent(match[2]),key=paper+"/"+field;
   const old=drafts.get(key)??{board_id:"board",board_revision_id:"rev",paper_id:paper,field_id:field,version:0,expected_cell_head_id:null,data:emptyCell(),updated_at:null};
   if(method==="GET")return response(old);
   if(gate&&body.data.references.length)await gate;
   assert.equal(body.expected_revision_id,"rev");assert.equal(body.version,old.version);const saved={...old,version:old.version+1,expected_cell_head_id:body.expected_cell_head_id,data:body.data};drafts.set(key,saved);return response(saved);
  }
  if(path.endsWith("/candidates")){
   if(providerFailure)return response({detail:{code:"fixture_failure",message:"SYNTHETIC provider unavailable; no fallback"}},503);
   const candidates=empty?[]:[{rank:1,score:1,reference:reference(body.paper_id),total_block_characters:chars.length,omitted_characters:Math.max(0,chars.length-4500)},{rank:2,score:.5,reference:reference(body.paper_id,12,24),total_block_characters:chars.length,omitted_characters:0}];
   return response({id:"candidate-run",board_id:"board",board_revision_id:"rev",paper_id:body.paper_id,field_id:body.field_id,field_revision_id:"field-v1",indexed_blocks:1,matched_blocks:candidates.length,returned_count:candidates.length,omitted_matched_blocks:0,candidates});
  }
  if(path.includes("/sources/")){
   const source=sources.find(s=>path.includes("/sources/"+s.source_id+"/"))!;assert.ok(source);assert.notEqual(source.source_type,"none");
   const start=Number(new URL(path,"http://fixture").searchParams.get("start")??0),end=Math.min(chars.length,start+4000),ref=reference(source.paper_id,start,end);
   return response({board_revision_id:"rev",source,freshness:view.freshness,blocks:[{source_id:source.source_id,paper_id:wrongPaper?"p2":source.paper_id,block_id:ref.block_id,ordinal:0,locator:ref.locator,start,end,total_characters:chars.length,text:chars.slice(start,end).join(""),omitted_before:start,omitted_after:chars.length-end,reference:ref}],offset:0,limit:3,total_blocks:1});
  }
  if(path.endsWith("/cell-revisions")){
   const key=body.paper_id+"/"+body.field_id,draft=drafts.get(key);assert.ok(draft);assert.equal(body.draft_version,draft.version);assert.equal(body.supersedes_id,draft.expected_cell_head_id);
   const row={...draft.data,id:"cell-"+(revisions.length+1),board_id:"board",board_revision_id:"rev",paper_id:body.paper_id,field_id:body.field_id,field_revision_id:"field-v1",supersedes_id:body.supersedes_id,references:draft.data.references.map((r:any)=>({...reference(body.paper_id,r.start,r.end),...r})),inspected_ranges:draft.data.inspected_ranges.map((r:any)=>({...reference(body.paper_id,r.start,r.end),...r})),reference_integrity:draft.data.references.length?"checked":"not_applicable",review_state:"single_human_self_declared_not_independently_verified",created_at:date};
   revisions.push(row);view.cells.find(c=>c.paper_id===body.paper_id)!.head={...row,references:row.references.map(({quote,...r}:any)=>r),inspected_ranges:row.inspected_ranges.map(({quote,...r}:any)=>r)};drafts.delete(key);return response(row);
  }
  if(path.includes("/history?"))return response({items:revisions.filter(r=>path.includes("/cells/"+r.paper_id+"/")),offset:0,limit:10,total:revisions.length});
  assert.fail("Unexpected fixture request "+method+" "+path);
 };
 let renderer!:ReactTestRenderer;
 async function mount(paper?:string){await act(async()=>{renderer=create(<Compare workspace={workspace} requestedBoard="board" requestedPaper={paper} requestedField={paper?"finding":undefined} navigate={async value=>{await flushDrafts();navigation.push(value);}}/>,{createNodeMock:node=>({focus:()=>focus.push(String((node.props as Record<string,unknown>)["aria-label"]??node.type)),scrollIntoView:()=>{},scrollLeft:0,querySelectorAll:()=>[]})});});return renderer;}
 await mount();
 return {get renderer(){return renderer;},mount,requests,drafts,editorDrafts,revisions,navigation,focus,view,chars,reference,delayAck(){gate=new Promise<void>(resolve=>releaseAck=resolve);},releaseAck(){gate=null;releaseAck?.();},conflictHint(){hintConflict=true;},wrongPaperContext(){wrongPaper=true;},async open(paper:string){await act(async()=>renderer.root.findByProps({"aria-label":"Finding for SYNTHETIC SOFTWARE REPORT "+paper.slice(1)}).props.onClick());},async close(){await act(async()=>renderer.unmount());}};
}

test("E1: confirmation waits for research-draft acknowledgement, clips Unicode display, and never preselects support",async()=>{
 const f=await fixture("excerpt-independent-ack",{long:true});try{
  await f.open("p1");assert.equal(step(f.renderer),"1. Select evidence");assert.equal(f.requests.some(r=>r.path.endsWith("/candidates")||r.path.includes("/sources/")),false);
  await click(f.renderer,"Find excerpts in this paper");await click(f.renderer,"Read in source · passage 1");assert.equal(f.drafts.size,0,"retrieval and opening do not declare inspection");
  assert.equal(Array.from(text(f.renderer.root.findByType("mark"))).length,4000);assert.match(text(f.renderer.root),/range omits/);
  f.delayAck();await act(async()=>{button(f.renderer,"I have read this excerpt — use it").props.onClick();});
  assert.equal(step(f.renderer),"1. Select evidence");assert.equal(f.focus.includes("textarea"),false);
  await act(async()=>f.releaseAck());assert.equal(step(f.renderer),"2. Comment & judge");const d=f.drafts.get("p1/finding").data;
  assert.equal(d.references[0].end,4000);assert.equal(d.inspected_ranges[0].end,4000);assert.equal(d.semantic_assessment,"unassessed");assert.equal(d.scope_result,"not_assessed");assert.equal(f.revisions.length,0);
  assert.equal(control(f.renderer,"Human support judgment","select").props.value,"unassessed");assert.ok(f.focus.includes("textarea"));assert.equal(f.navigation.some(n=>n.page!=="compare"),false);
 }finally{await f.close();}
});

test("E1: three cells complete in comparison; abstract missing scope and unavailable source stay explicit",async()=>{
 const f=await fixture("excerpt-independent-three");try{
  await f.open("p1");await click(f.renderer,"Find excerpts in this paper");await click(f.renderer,"Read in source · passage 1");await click(f.renderer,"I have read this excerpt — use it");
  await change(f.renderer,"Manual cell value","SYNTHETIC SOFTWARE COMMENT");await change(f.renderer,"Reason","Software exercise; support remains unassessed");await change(f.renderer,"Inspected scope result","value_found","select");await click(f.renderer,"Review entry before saving");await click(f.renderer,"Save reviewed entry");
  assert.match(text(f.renderer.root),/Saved to comparison/);await click(f.renderer,"Next unfinished cell");assert.match(text(f.renderer.root.findByProps({"aria-label":"Finding cell editor"})),/REPORT 2/);assert.match(text(f.renderer.root),/Only the retained abstract/);
  await click(f.renderer,"Browse this source");await click(f.renderer,"Mark inspected without attaching");await click(f.renderer,"Continue with notes or missing information");await change(f.renderer,"Reason","Not retained in this inspected synthetic abstract");await change(f.renderer,"Missing information","Allocation details; full paper not inspected");await change(f.renderer,"Inspected scope result","not_found_in_inspected_material","select");await click(f.renderer,"Review entry before saving");await click(f.renderer,"Save reviewed entry");
  assert.equal(f.revisions[1].value,null);assert.equal(f.revisions[1].references.length,0);assert.equal(f.revisions[1].semantic_assessment,"unassessed");await click(f.renderer,"Next unfinished cell");assert.match(text(f.renderer.root),/No inspectable source was retained/);assert.equal(disabled(button(f.renderer,"Find excerpts in this paper")),true);
  await click(f.renderer,"Continue with notes or missing information");await change(f.renderer,"Reason","Source unavailable; no text was inspected");await change(f.renderer,"Missing information","No retained source for this software fixture");await click(f.renderer,"Review entry before saving");await click(f.renderer,"Save reviewed entry");
  assert.equal(f.revisions.length,3);assert.equal(f.revisions[2].value,null);assert.equal(f.revisions[2].inspected_ranges.length,0);assert.equal(f.revisions[2].scope_result,"not_assessed");assert.equal(f.navigation.every(n=>n.page==="compare"),true);assert.equal(f.requests.filter(r=>r.path.endsWith("/candidates")).length,1);
 }finally{await f.close();}
});

test("E1: a note autosaves but cannot become a new reviewed entry or a false absence declaration",async()=>{
 const f=await fixture("excerpt-independent-note");try{
  await f.open("p2");await click(f.renderer,"Continue with notes or missing information");await change(f.renderer,"Manual cell value","UNSUBMITTED SOFTWARE NOTE");await click(f.renderer,"Review entry before saving");
  assert.equal(f.drafts.get("p2/finding").data.value,"UNSUBMITTED SOFTWARE NOTE");assert.equal(disabled(button(f.renderer,"Save reviewed entry")),true);assert.match(text(f.renderer.root),/autosaved note, not a reviewed entry/);
  await click(f.renderer,"Back to comment");await change(f.renderer,"Manual cell value","");await change(f.renderer,"Reason","Missing detail");await change(f.renderer,"Missing information","Allocation");await change(f.renderer,"Inspected scope result","not_found_in_inspected_material","select");await click(f.renderer,"Review entry before saving");assert.equal(disabled(button(f.renderer,"Save reviewed entry")),true);assert.match(text(f.renderer.root),/explicitly inspected range/);assert.equal(f.revisions.length,0);
  await f.close();await f.mount("p2");assert.equal(step(f.renderer),"3. Review & save");assert.equal(f.drafts.get("p2/finding").data.reason,"Missing detail");assert.equal(f.requests.some(r=>r.path.endsWith("/candidates")||r.path.includes("/sources/")),false);
 }finally{await f.close();}
});

test("E1: adding and removing references preserves comment and human judgment while exposing unmet prerequisites",async()=>{
 const f=await fixture("excerpt-independent-removal");try{
  await f.open("p1");await click(f.renderer,"Find excerpts in this paper");await click(f.renderer,"Read in source · passage 1");await click(f.renderer,"I have read this excerpt — use it");await change(f.renderer,"Manual cell value","RETAIN THIS COMMENT");await change(f.renderer,"Human support judgment","human_supported","select");await change(f.renderer,"Inspected scope result","value_found","select");await change(f.renderer,"Reason","Synthetic explicit judgment");
  await click(f.renderer,"Add or change evidence");await click(f.renderer,"Read in source · passage 2");await click(f.renderer,"I have read this excerpt — use it");assert.equal(f.drafts.get("p1/finding").data.references.length,2);
  await click(f.renderer,"Remove selected excerpt 1");await click(f.renderer,"Remove selected excerpt 1");assert.equal(control(f.renderer,"Manual cell value").props.value,"RETAIN THIS COMMENT");assert.equal(control(f.renderer,"Human support judgment","select").props.value,"human_supported");await click(f.renderer,"Review entry before saving");assert.equal(disabled(button(f.renderer,"Save reviewed entry")),true);assert.match(text(f.renderer.root),/Human-supported needs/);assert.equal(f.revisions.length,0);
 }finally{await f.close();}
});

for(const mode of ["empty","failure"] as const)test(`E1: ${mode} candidate response preserves notes and does not trigger another retrieval`,async()=>{
 const f=await fixture("excerpt-independent-"+mode,{empty:mode==="empty",providerFailure:mode==="failure"});try{
  await f.open("p1");await click(f.renderer,"Continue with notes or missing information");await change(f.renderer,"Manual cell value","KEEP ON ERROR");await click(f.renderer,"Add or change evidence");await click(f.renderer,"Find excerpts in this paper");
  assert.equal(f.requests.filter(r=>r.path.endsWith("/candidates")).length,1);assert.equal(f.drafts.get("p1/finding").data.value,"KEEP ON ERROR");assert.equal(f.drafts.get("p1/finding").data.references.length,0);assert.equal(f.revisions.length,0);
  if(mode==="failure")assert.match(text(f.renderer.root),/SYNTHETIC provider unavailable/);assert.equal(f.navigation.every(n=>n.page==="compare"),true);
 }finally{await f.close();}
});

test("E1: editor-view CAS failure keeps acknowledged evidence and blocks automatic progression",async()=>{
 const f=await fixture("excerpt-independent-hint-conflict");try{
  await f.open("p1");await click(f.renderer,"Find excerpts in this paper");await click(f.renderer,"Read in source · passage 1");f.conflictHint();await click(f.renderer,"I have read this excerpt — use it");
  assert.equal(f.drafts.get("p1/finding").data.references.length,1);assert.equal(f.drafts.get("p1/finding").data.inspected_ranges.length,1);assert.equal(step(f.renderer),"1. Select evidence");assert.match(text(f.renderer.root),/Another tab changed the editor view/);assert.equal(f.revisions.length,0);assert.equal(f.focus.includes("textarea"),false);
 }finally{await f.close();}
});

test("E1: historical step navigation is read-only and uses ordinary button semantics",async()=>{
 const f=await fixture("excerpt-independent-historical",{historical:true});try{
  await f.open("p2");await click(f.renderer,"2. Comment & judge");await click(f.renderer,"3. Review & save");assert.equal(step(f.renderer),"3. Review & save");assert.equal(f.requests.some(r=>r.method!=="GET"),false);assert.equal(f.renderer.root.findAllByProps({role:"tablist"}).length,0);assert.equal(f.renderer.root.findByProps({"aria-label":"Cell review steps"}).findAllByType("button").length,3);assert.equal(disabled(control(f.renderer,"Manual cell value")),true);
 }finally{await f.close();}
});


test("E1: reopened selected-excerpt projection rejects wrong-paper context without changing research evidence",async()=>{
 const f=await fixture("excerpt-independent-wrong-paper");try{
  await f.open("p1");await click(f.renderer,"Find excerpts in this paper");await click(f.renderer,"Read in source · passage 1");await click(f.renderer,"I have read this excerpt — use it");await change(f.renderer,"Manual cell value","PRESERVE BOUND COMMENT");await click(f.renderer,"Review entry before saving");
  const before=structuredClone(f.drafts.get("p1/finding"));await f.close();f.wrongPaperContext();await f.mount("p1");
  assert.match(text(f.renderer.root),/could not be displayed against its exact source binding/);assert.deepEqual(f.drafts.get("p1/finding"),before);assert.equal(f.requests.filter(r=>r.path.endsWith("/candidates")).length,1);assert.equal(f.revisions.length,0);
 }finally{await f.close();}
});

test("E1: a submitted cell needs explicit revision and preserves the immutable prior entry",async()=>{
 const f=await fixture("excerpt-independent-revision");try{
  await f.open("p1");await click(f.renderer,"Browse this source");await click(f.renderer,"I have read this excerpt — use it");await change(f.renderer,"Manual cell value","FIRST SYNTHETIC ENTRY");await change(f.renderer,"Reason","Software validation only");await change(f.renderer,"Inspected scope result","value_found","select");await click(f.renderer,"Review entry before saving");await click(f.renderer,"Save reviewed entry");
  assert.equal(disabled(button(f.renderer,"Save revision")),true);assert.equal(disabled(control(f.renderer,"Manual cell value")),true);assert.equal(f.revisions.length,1);
  await click(f.renderer,"Edit saved cell");await change(f.renderer,"Manual cell value","SECOND SYNTHETIC ENTRY");await click(f.renderer,"Review entry before saving");await click(f.renderer,"Save revision");
  assert.equal(f.revisions.length,2);assert.equal(f.revisions[1].supersedes_id,f.revisions[0].id);assert.equal(f.revisions[0].value,"FIRST SYNTHETIC ENTRY");assert.equal(f.revisions[1].value,"SECOND SYNTHETIC ENTRY");await click(f.renderer,"Load immutable cell history");assert.match(text(f.renderer.root.findByProps({"aria-label":"Immutable cell history"})),/FIRST SYNTHETIC ENTRY/);assert.equal(f.navigation.every(n=>n.page==="compare"),true);
 }finally{await f.close();}
});
