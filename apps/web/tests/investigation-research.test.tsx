import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import InvestigationNavigator,{type InvestigationContext} from "../components/investigation-navigator.tsx";
import {emptyCell} from "../lib/board-drafts.tsx";
import {researchDraft} from "../lib/investigation-research.ts";
import type {Schema} from "../lib/api.ts";
import {saved,draft,capability,response,stamp,workspace} from "./search-planner-fixtures.ts";

const storage=new Map<string,string>();
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,sessionStorage:{getItem:(key:string)=>storage.get(key)??null,setItem:(key:string,value:string)=>storage.set(key,value),removeItem:(key:string)=>storage.delete(key)}});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
function button(renderer:ReactTestRenderer,label:string){const node=renderer.root.findAllByType("button").find(item=>text(item)===label);assert.ok(node,`Missing button: ${label}`);return node;}
function control(renderer:ReactTestRenderer,label:string,type:"textarea"|"input"|"select"="textarea"){const node=renderer.root.findAllByType("label").find(item=>item.children.some(child=>child===label));assert.ok(node,`Missing control: ${label}`);return node.findByType(type);}
function checkbox(renderer:ReactTestRenderer,label:string){const node=renderer.root.findAllByType("label").find(item=>text(item).includes(label));assert.ok(node,`Missing checkbox: ${label}`);return node.findByType("input");}
async function click(renderer:ReactTestRenderer,label:string){const node=button(renderer,label);assert.equal(!!node.props.disabled,false,`${label} must be available`);await act(async()=>{node.props.onClick();});}
async function edit(renderer:ReactTestRenderer,label:string,value:string,type:"textarea"|"input"|"select"="textarea"){await act(async()=>control(renderer,label,type).props.onChange({target:{value}}));}
async function check(renderer:ReactTestRenderer,label:string,checked=true){await act(async()=>checkbox(renderer,label).props.onChange({target:{checked}}));}
type Call={path:string;method:string;body:any};
const paper=(id:string,title:string):Schema<"Paper">=>({id,title,authors:["Synthetic Researcher"],year:2026,pmid:id==="paper-b"?"990002":null,pmcid:null,doi:null,url:"",abstract:"Synthetic public test material only."});
function fixture(id:string){
  const paperA=paper("paper-a","Paper A · original retained report"),paperB=paper("paper-b","Paper B · related candidate");
  const plan=saved({...draft(),input_mode:"manual_strategy",manual_strategy:"microbiome[Title/Abstract]",concepts:[],variants:[]});plan.revision.workspace_id=id;plan.revision.plan_id="plan-"+id;
  const data={...emptyCell(),value:"Original draft interpretation",reason:"Population details unresolved"};
  const board={board_id:"original-board",revision_id:"original-revision",workspace_id:id,question:"Which population was studied?",fields:[{id:"population",label:"Population",subquestion:"What population was studied?"}],papers:[paperA],sources:[{paper_id:paperA.id,source_id:"original-source",source_type:"abstract",source_manifest_sha256:"a".repeat(64)}]} as unknown as Schema<"BoardView">["definition"];
  const origin={schema_version:"mvp.investigation-origin.v1",id:"investigation",workspace_id:id,board,paper_id:paperA.id,field_id:"population",cell:{id:"original-cell",value:"Not specified in inspected excerpt",semantic_assessment:"partial"},draft:{version:2,data},local_draft:data,reason:"Look for related population reports",plan_id:plan.revision.plan_id,created_at:stamp,seed_plan_id:null,seed_revision_id:null,seed_approval_ids:[],meaning:"unresolved_cell_not_proof_of_research_gap"} as unknown as Schema<"InvestigationOrigin">;
  const view={schema_version:"mvp.investigation.v1",origin,plan,capabilities:capability(),executions:[{execution:{id:"execution",requested_max_results:10},search:{searched_at:stamp,query:"microbiome[Title/Abstract]",total_reported:1,fetched_count:1,truncated:false,warnings:[],errors:[]},candidates:[{id:"candidate-b",paper:paperB,decision:"unassessed",decision_version:0}]}],decisions:[],failures:[]} as unknown as Schema<"InvestigationView">;
  const collectionRef={kind:"collection",collection_id:"followup-snapshot-1",collection_snapshot_sha256:"b".repeat(64)};
  const handoff={schema_version:"mvp.investigation-handoff.v1",id:"handoff",investigation_id:origin.id,request_id:"test-commit",selection_sha256:"c".repeat(64),collection:{id:"followup-snapshot-1",collection_id:"followup-logical",revision_id:"collection-revision-1",revision:1,name:"Follow-up research selection",origin:collectionRef,member_count:2,created_at:stamp},original_board_id:board.board_id,original_board_revision_id:board.revision_id,original_cell_revision_id:"original-cell",selected_candidate_ids:["candidate-b"],selected_original_paper_ids:[paperA.id],created_at:stamp,meaning:"explicit_collection_commit_not_source_preparation_or_scientific_judgment"} as unknown as Schema<"InvestigationHandoff">;
  const preparation={id:"prepared-followup",collection_ref:collectionRef,source_revision:2,selected_paper_ids:[paperA.id,paperB.id],sources:[{id:"source-a",paper_id:paperA.id,source_type:"abstract",status:"ready"},{id:"source-b",paper_id:paperB.id,source_type:"abstract",status:"ready"}]} as unknown as Schema<"CollectionPreparationView">;
  const passage=(id:string,paperId:string,rank:number)=>({id,paper_id:paperId,rank,source_type:"abstract",anchor:{quote:paperId===paperB.id?"Related Paper B studied 48 adults.":"Paper A excerpt lacks a population description."}});
  const run={id:"passage-run",preparation_id:preparation.id,collection_ref:collectionRef,passages:[passage("passage-a",paperA.id,1),passage("passage-b",paperB.id,2)]} as unknown as Schema<"RunView">["run"];
  const inspection={schema_version:"mvp.investigation-inspection.v1",id:"inspection-b",investigation_id:origin.id,handoff_id:handoff.id,preparation_id:preparation.id,run_id:run.id,passage_id:"passage-b",source_paper:paperB,reference:{paper_id:paperB.id,source_id:"source-b",quote:"Related Paper B studied 48 adults.",start:0,end:33},source_type:"abstract",source_status:"ready",source_manifest_sha256:"d".repeat(64),source_revision:2,created_at:stamp,meaning:"verified_displayed_passage_not_human_support"} as unknown as Schema<"InvestigationInspection">;
  const context={board_id:board.board_id,expected_board_revision_id:board.revision_id,paper_id:paperA.id,field_id:"population",expected_cell_head_id:"original-cell",expected_draft_version:2,local_draft:data} as InvestigationContext;
  return {view,context,paperA,paperB,handoff,preparation,run,inspection};
}
async function mount(id:string,{prepared=false,handler}:{prepared?:boolean;handler?:(call:Call,state:any)=>Response|Promise<Response>|undefined}={}){
  const f=fixture(id),calls:Call[]=[],drafts=new Map<string,any>();
  const state={...f,workspace:workspace(id),research:{schema_version:"mvp.investigation-research.v1",investigation_id:f.view.origin.id,handoffs:prepared?[f.handoff]:[],inspections:[],notes:[]} as Schema<"InvestigationResearchState">};
  const base="/api/v1/workspaces/"+id,researchPath=base+"/drafts/investigation-research:investigation";
  if(prepared){state.view.executions[0].candidates[0].decision="shortlist";state.view.executions[0].candidates[0].decision_version=1;state.workspace.source_revision=2;state.workspace.current_preparation_id=f.preparation.id;drafts.set(researchPath,{version:1,expected_assessment_head:null,data:{...researchDraft(f.view.origin),candidate_ids:["candidate-b"],handoff_id:f.handoff.id,preparation_id:f.preparation.id}});}
  let returned:Schema<"InvestigationOrigin">|undefined,changedDraftAtReturn:any,navigated:any;
  globalThis.fetch=async(input,init)=>{
    const call:Call={path:decodeURIComponent(String(input)),method:init?.method??"GET",body:init?.body?JSON.parse(String(init.body)):undefined};calls.push(call);
    const custom=await handler?.(call,state);if(custom)return custom;
    if(call.path.endsWith("/session"))return response({csrf_token:"offline-test"});
    if(call.path.includes("/drafts/")){const old=drafts.get(call.path)??{version:0,data:{},expected_assessment_head:null};if(call.method==="GET")return response(old);if(call.body.version!==old.version)return response({detail:{code:"draft_conflict",message:"Another tab saved this research draft"}},409);const next={...call.body,version:old.version+1};drafts.set(call.path,next);return response(next);}
    if(call.path===base)return response(state.workspace);
    if(call.path.includes("/investigations?"))return response({investigations:[state.view.origin]});
    if(call.path.endsWith("/investigations/investigation"))return response(state.view);
    if(call.path.endsWith("/research"))return response(state.research);
    if(call.path.endsWith("/decisions")){const candidate=state.view.executions[0].candidates[0];assert.equal(call.body.expected_version,candidate.decision_version);state.view={...state.view,executions:[{...state.view.executions[0],candidates:[{...candidate,decision:call.body.decision,decision_version:candidate.decision_version+1}]}]};return response(state.view);}
    if(call.path.includes("/collections/followup-snapshot-1/papers?"))return response({origin:f.handoff.collection.origin,papers:[f.paperA,f.paperB],total:2,next_offset:null});
    if(call.path.includes("/collections/followup-snapshot-1/paper?")){const member=call.path.endsWith("paper-b")?f.paperB:f.paperA;return response({origin:f.handoff.collection.origin,member:{paper:member,origins:member.id===f.paperB.id?[{kind:"investigation_candidate",investigation_id:"investigation",handoff_id:"handoff"}]:[{kind:"original_report"}]}});}
    if(call.path.includes("/collection-preparation-jobs?"))return response({jobs:[]});
    if(call.path.endsWith("/source-preparations/prepared-followup"))return response(f.preparation);
    if(call.path.endsWith("/runs/passage-run"))return response({run:f.run});
    throw new Error("Unexpected offline request: "+call.method+" "+call.path);
  };
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<InvestigationNavigator workspaceId={id} context={f.context} canCreate navigate={async route=>{navigated=route;}} onReturn={async origin=>{returned=origin;changedDraftAtReturn=structuredClone(drafts.get(researchPath));}}/>);});
  return {renderer,calls,state,drafts,researchPath,returned:()=>returned,savedAtReturn:()=>changedDraftAtReturn,navigated:()=>navigated};
}
async function openResearch(renderer:ReactTestRenderer){await click(renderer,"Reopen investigation");await click(renderer,"Add evidence or expand comparison");}
const providerCalls=(calls:Call[])=>calls.filter(call=>call.method!=="GET"&&/\/(execute|diagnose|propose|evidence-runs|collection-preparation-jobs)$/.test(call.path));

test("navigation stays local; shortlist, selection preview and collection commit are separate explicit actions",async()=>{
  const f=await mount("research-selection",{handler:(call,state)=>{
    if(call.path.endsWith("/handoff-preview"))return response({schema_version:"mvp.investigation-handoff-preview.v1",input_sha256:"e".repeat(64),members:[{selection_id:"candidate-b",paper:state.paperB,kind:"candidate"}],duplicate_groups:[],max_comparison_papers:30,original_board_id:state.view.origin.board.board_id,original_board_revision_id:state.view.origin.board.revision_id});
    if(call.path.endsWith("/handoffs")){state.research.handoffs=[state.handoff];return response(state.handoff);}
  }}),original=structuredClone(f.state.view.origin);
  try{
    await openResearch(f.renderer);assert.match(text(f.renderer.root),/Shortlist at least one candidate/);assert.equal(f.calls.some(call=>call.method!=="GET"),false);
    await click(f.renderer,"Shortlist");assert.equal(button(f.renderer,"Review selected papers for comparison").props.disabled,true);assert.equal(f.calls.some(call=>call.path.endsWith("/handoff-preview")),false);
    await check(f.renderer,"Paper B · related candidate · shortlisted candidate");await check(f.renderer,"Paper A · original retained report · original report");
    await click(f.renderer,"Review selected papers for comparison");const preview=f.calls.find(call=>call.path.endsWith("/handoff-preview"))!;assert.deepEqual(preview.body.candidates,[{candidate_id:"candidate-b",expected_decision_version:1}]);assert.deepEqual(preview.body.original_paper_ids,["paper-a"]);assert.equal(f.calls.some(call=>call.path.endsWith("/handoffs")),false);
    await edit(f.renderer,"Follow-up collection name","Reviewed follow-up","input");assert.equal(button(f.renderer,"Add selected papers to comparison workflow").props.disabled,true);assert.match(text(f.renderer.root),/Selection or duplicate-review choices changed/);
    await click(f.renderer,"Review selected papers for comparison");await click(f.renderer,"Add selected papers to comparison workflow");const commit=f.calls.find(call=>call.path.endsWith("/handoffs"))!;assert.equal(commit.body.name,"Reviewed follow-up");assert.equal(commit.body.preview_sha256,"e".repeat(64));assert.match(text(f.renderer.root),/Prepare committed sources/);
    assert.notEqual(f.state.handoff.collection.id,f.state.handoff.collection.collection_id);
    assert.deepEqual(f.calls.filter(call=>call.path.includes("/collections/")).map(call=>({method:call.method,path:call.path.split("/collections/")[1]})),[
      {method:"GET",path:"followup-snapshot-1/papers?offset=0&limit=50"},
      {method:"GET",path:"followup-snapshot-1/paper?paper_id=paper-a"},
      {method:"GET",path:"followup-snapshot-1/paper?paper_id=paper-b"},
    ]);
    assert.equal(providerCalls(f.calls).length,0);assert.deepEqual(f.state.view.origin,original);assert.equal(f.calls.some(call=>/\/boards(?:\/|$)/.test(call.path)),false);
    await click(f.renderer,"Return to original cell");assert.deepEqual(f.returned(),original);assert.equal(providerCalls(f.calls).length,0);
  }finally{await act(async()=>f.renderer.unmount());}
});

test("prepared Paper B must be inspected and explicitly attributed before saving a research evaluation",async()=>{
  const f=await mount("research-note",{prepared:true,handler:(call,state)=>{
    if(call.path.endsWith("/evidence-runs"))return response(state.run);
    if(call.path.endsWith("/inspections")){assert.equal(call.body.passage_id,"passage-b");state.research.inspections=[state.inspection];return response(state.inspection);}
    if(call.path.endsWith("/notes")){const note={id:"note-b",revision_id:"note-revision-1",revision:1,created_at:stamp,inspection:state.inspection,research_question:call.body.research_question,interpretation:call.body.interpretation};state.research.notes=[note];return response(note);}
  }}),original=structuredClone(f.state.view.origin);
  try{
    await openResearch(f.renderer);assert.equal(providerCalls(f.calls).length,0);assert.equal(button(f.renderer,"Save source-linked research evaluation").props.disabled,true);assert.match(text(f.renderer.root),/A candidate citation alone cannot support this note/);
    await click(f.renderer,"Retrieve prepared passages");assert.equal(providerCalls(f.calls).length,1);assert.match(text(f.renderer.root),/Original report context/);assert.equal(f.renderer.root.findAllByType("button").some(item=>text(item)==="Inspect related-paper passage · 1"),false);
    await click(f.renderer,"Inspect related-paper passage · 2");assert.match(text(f.renderer.root),/It does not fill a missing fact in the original paper/);assert.equal(f.calls.some(call=>call.path.endsWith("/notes")),false);
    await click(f.renderer,"Use this passage in my research evaluation");await edit(f.renderer,"My research interpretation","Paper B reports adults; Paper A remains unresolved.");
    assert.equal(button(f.renderer,"Save source-linked research evaluation").props.disabled,true);await check(f.renderer,"I inspected the displayed passage");assert.equal(button(f.renderer,"Save source-linked research evaluation").props.disabled,true);await check(f.renderer,"I am attributing this evidence to the named related paper");await click(f.renderer,"Save source-linked research evaluation");
    const note=f.calls.find(call=>call.path.endsWith("/notes"))!;assert.equal(note.body.inspection_id,"inspection-b");assert.equal(note.body.interpretation,"Paper B reports adults; Paper A remains unresolved.");assert.equal(note.body.confirm_inspected,true);assert.equal(note.body.acknowledge_related_paper,true);assert.match(text(f.renderer.root),/Saved evaluations/);assert.deepEqual(f.state.view.origin,original);assert.equal(f.calls.some(call=>/\/boards(?:\/|$)|\/cells\//.test(call.path)),false);
    await click(f.renderer,"All investigations for this cell");await openResearch(f.renderer);assert.equal(control(f.renderer,"My research interpretation").props.value,"Paper B reports adults; Paper A remains unresolved.");assert.match(text(f.renderer.root),/Evaluation revision history/);assert.match(text(f.renderer.root),/Related Paper B studied 48 adults/);assert.equal(providerCalls(f.calls).length,1);
  }finally{await act(async()=>f.renderer.unmount());}
});

test("an immediate evaluation edit is flushed by the parent list and return controls",async()=>{
  const f=await mount("research-navigation");
  try{
    await openResearch(f.renderer);await edit(f.renderer,"My research interpretation","Preserve my unsaved research interpretation.");await click(f.renderer,"All investigations for this cell");assert.equal(f.drafts.get(f.researchPath).data.interpretation,"Preserve my unsaved research interpretation.");
    await openResearch(f.renderer);assert.equal(control(f.renderer,"My research interpretation").props.value,"Preserve my unsaved research interpretation.");await edit(f.renderer,"My research interpretation","Immediate correction before return.");await click(f.renderer,"Return to original cell");assert.equal(f.savedAtReturn().data.interpretation,"Immediate correction before return.");assert.equal(f.returned()?.board.revision_id,"original-revision");assert.equal(providerCalls(f.calls).length,0);
  }finally{await act(async()=>f.renderer.unmount());}
});

test("failure and two-tab conflict retain research text and block leaving until explicit inspected resolution",async()=>{
  const f=await mount("research-failure",{handler:(call)=>call.path.endsWith("/handoff-preview")?response({detail:{code:"selection_failed",message:"Synthetic preview unavailable; selection retained"}},502):undefined});
  try{
    await openResearch(f.renderer);await click(f.renderer,"Shortlist");await check(f.renderer,"Paper B · related candidate · shortlisted candidate");await click(f.renderer,"Review selected papers for comparison");assert.match(text(f.renderer.root),/Synthetic preview unavailable/);assert.equal(checkbox(f.renderer,"Paper B · related candidate · shortlisted candidate").props.checked,true);assert.equal(f.calls.some(call=>call.path.endsWith("/handoffs")),false);
    const previous=f.drafts.get(f.researchPath);f.drafts.set(f.researchPath,{...previous,version:previous.version+1,data:{...previous.data,interpretation:"OTHER TAB'S SAVED INTERPRETATION"}});
    await edit(f.renderer,"My research interpretation","MY LOCAL RESEARCH TEXT");await click(f.renderer,"Return to original cell");assert.equal(f.returned(),undefined);assert.equal(control(f.renderer,"My research interpretation").props.value,"MY LOCAL RESEARCH TEXT");assert.match(text(f.renderer.root),/Another tab saved this research draft/);
    await click(f.renderer,"Inspect latest research draft");assert.match(text(f.renderer.root),/OTHER TAB'S SAVED INTERPRETATION/);const inspected=f.drafts.get(f.researchPath);f.drafts.set(f.researchPath,{...inspected,version:inspected.version+1});await click(f.renderer,"Keep my research edits against this inspected draft");assert.match(text(f.renderer.root),/inspected draft changed again/);assert.equal(control(f.renderer,"My research interpretation").props.value,"MY LOCAL RESEARCH TEXT");
    await click(f.renderer,"Inspect latest research draft");await click(f.renderer,"Keep my research edits against this inspected draft");await click(f.renderer,"Return to original cell");assert.equal(f.savedAtReturn().data.interpretation,"MY LOCAL RESEARCH TEXT");assert.equal(providerCalls(f.calls).length,0);
  }finally{await act(async()=>f.renderer.unmount());}
});


test("a selected candidate dismissed later remains visible for explicit removal",async()=>{
  const f=await mount("research-dismissed-selection");
  try{
    await openResearch(f.renderer);await click(f.renderer,"Shortlist");await check(f.renderer,"Paper B · related candidate · shortlisted candidate");await click(f.renderer,"Dismiss");
    assert.match(text(f.renderer.root),/Some selected candidates are no longer shortlisted/);assert.equal(button(f.renderer,"Review selected papers for comparison").props.disabled,true);
    await click(f.renderer,"Remove unavailable selection · Paper B · related candidate");assert.doesNotMatch(text(f.renderer.root),/Some selected candidates are no longer shortlisted/);await click(f.renderer,"Shortlist");assert.equal(checkbox(f.renderer,"Paper B · related candidate · shortlisted candidate").props.checked,false);assert.equal(button(f.renderer,"Review selected papers for comparison").props.disabled,true);
    await check(f.renderer,"Paper B · related candidate · shortlisted candidate");assert.equal(button(f.renderer,"Review selected papers for comparison").props.disabled,false);assert.equal(providerCalls(f.calls).length,0);assert.equal(f.calls.some(call=>call.path.endsWith("/handoffs")),false);
  }finally{await act(async()=>f.renderer.unmount());}
});

test("a reopened succeeded job does not replace the retained historical preparation or passage run",async()=>{
  const f=await mount("research-historical-preparation",{prepared:true,handler:(call,state)=>{
    const latest={...state.preparation,id:"latest-preparation",source_revision:3};
    if(call.path.endsWith("/source-preparations/latest-preparation"))return response(latest);
    if(call.path.includes("/collection-preparation-jobs?"))return response({jobs:[{schema_version:"mvp.collection-preparation-job.v1",id:"completed-latest-job",workspace_id:state.workspace.id,collection_ref:latest.collection_ref,selected_paper_ids:latest.selected_paper_ids,expected_source_revision:2,expected_preparation_id:state.preparation.id,status:"succeeded",attempt:1,max_attempts:3,progress_completed:2,progress_total:2,active_paper_id:null,elapsed_seconds:1,max_runtime_seconds:2400,interrupted_count:0,result_preparation_id:latest.id,result_source_revision:3,error:null,outcomes:latest.selected_paper_ids.map((id:string,index:number)=>({paper_id:id,position:index+1,outcome:"abstract_only",source_id:"latest-"+id,source_type:"abstract",source_status:"abstract_only",error:null})),created_at:stamp,updated_at:stamp}]});
  }});
  f.state.workspace.current_preparation_id="latest-preparation";f.state.workspace.source_revision=3;
  const initial=f.drafts.get(f.researchPath);f.drafts.set(f.researchPath,{...initial,data:{...initial.data,run_id:"passage-run",interpretation:"My retained historical interpretation",board_paper_ids:["paper-b"]}});
  const before=structuredClone(f.drafts.get(f.researchPath));
  try{
    await openResearch(f.renderer);assert.match(text(f.renderer.root),/no longer current/);assert.match(text(f.renderer.root),/Related Paper B studied 48 adults/);assert.match(text(f.renderer.root),/Reopened selections are retained until you choose/);assert.equal(button(f.renderer,"Retrieve prepared passages").props.disabled,true);assert.deepEqual(f.drafts.get(f.researchPath),before);assert.equal(f.calls.some(call=>call.method!=="GET"),false);
    await click(f.renderer,"Open committed selection · Follow-up research selection");assert.deepEqual(f.drafts.get(f.researchPath),before);
    await click(f.renderer,"Use this prepared selection");const selected=f.drafts.get(f.researchPath).data;assert.equal(selected.preparation_id,"latest-preparation");assert.equal(selected.run_id,null);assert.equal(selected.interpretation,before.data.interpretation);assert.deepEqual(selected.board_paper_ids,["paper-a","paper-b"]);assert.equal(button(f.renderer,"Retrieve prepared passages").props.disabled,false);assert.equal(providerCalls(f.calls).length,0);
  }finally{await act(async()=>f.renderer.unmount());}
});
