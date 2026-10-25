import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Compare from "../components/compare";
import {emptyCell} from "../lib/board-drafts";
import type {Schema} from "../lib/api";
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
function disabled(node:ReactTestInstance){for(let item:ReactTestInstance|null=node;item;item=item.parent)if(item.props.disabled)return true;return false;}
const buttons=(renderer:ReactTestRenderer,label:string)=>renderer.root.findAllByType("button").filter(node=>text(node)===label);
async function observed(check:()=>boolean){const deadline=Date.now()+5000;while(!check()){assert.ok(Date.now()<deadline,"Expected rendered acknowledgement");await act(async()=>{await new Promise<void>(resolve=>setImmediate(resolve));});}}
async function click(renderer:ReactTestRenderer,label:string){await observed(()=>buttons(renderer,label).some(node=>!disabled(node)));await act(async()=>{buttons(renderer,label).find(node=>!disabled(node))!.props.onClick();});}
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}});

test("independent comparison hybrid work preserves draft barriers, exact cell scope, visible cancellation and explicit retry",async()=>{
 const stored=new Map<string,string>();Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,sessionStorage:{getItem:(key:string)=>stored.get(key)??null,setItem:(key:string,value:string)=>stored.set(key,value),removeItem:(key:string)=>stored.delete(key)}});
 const profile="hybrid_qwen3_06b_rrf_rerank_v1",date="2026-10-25T00:00:00Z",workspaceId="independent-cell-hybrid-progress";
 const paper={id:"p1",title:"SYNTHETIC SOFTWARE REPORT",authors:["Fixture"],year:2026,pmid:null,doi:null,pmcid:null,url:null};
 const definition={board_id:"b",revision_id:"r",workspace_id:workspaceId,parent_revision_id:null,search_id:"search",search_sha256:"a".repeat(64),question:"SOFTWARE ONLY",question_sha256:"b".repeat(64),preparation_id:"prep",source_revision:9,source_manifest_sha256:"c".repeat(64),papers:[paper],paper_ids:[paper.id],sources:[{source_id:"source",paper_id:paper.id,version:"retained-v3",source_sha256:"d".repeat(64),blocks_sha256:"e".repeat(64),parser_id:"fixture",source_type:"abstract",status:"abstract_only",block_count:1}],fields:[{id:"age",revision_id:"field-r2",label:"Age",subquestion:"SOFTWARE fixture age"}],retrieval_profile:{method:"bm25_dense_rrf_cross_encoder",profile_id:profile,device:"cpu"},retrieval_profile_sha256:"f".repeat(64),created_at:date};
 const summary={board_id:"b",revision_id:"r",question:definition.question,paper_count:1,field_count:1,created_at:date},view={definition,current_revision_id:"r",freshness:"current",freshness_reasons:[],cells:[{paper_id:paper.id,field_id:"age",head:null,draft_version:0}],definitions:[summary],limits:{max_fields:6}};
 const workspace={id:workspaceId,question:definition.question,mode:"saved_example",created_at:date,source_revision:9,current_preparation_id:"prep",selected_paper_ids:[paper.id],current_run_id:null,current_assessment_ids:{},searches:[],preparations:[],runs:[],assessments:[]} as unknown as Schema<"WorkspaceSummary">;
 const requests:{path:string;method:string;body:any}[]=[],editorDrafts=new Map<string,any>();
 let draft={board_id:"b",board_revision_id:"r",paper_id:paper.id,field_id:"age",version:0,expected_cell_head_id:null,data:emptyCell(),updated_at:null};
 let releaseDraft!:()=>void,resolveIndex!:(value:Response)=>void,holdDraft=false,state="running",phase="embedding",indexJob="",candidateAttempts=0;
 const draftGate=new Promise<void>(resolve=>releaseDraft=resolve),indexGate=new Promise<Response>(resolve=>resolveIndex=resolve);
 globalThis.fetch=async(input,options)=>{
  const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):null;requests.push({path,method,body});
  if(path.endsWith("/session"))return response({csrf_token:"software"});
  if(path.endsWith("/boards"))return response({boards:[summary],limits:{max_fields:6}});
  if(path.endsWith("/boards/b"))return response(view);
  if(path.includes("/drafts/board-editor%3A")){const old=editorDrafts.get(path)??{version:0,data:{},expected_assessment_head:null};if(method==="GET")return response(old);assert.equal(body.version,old.version);const saved={...body,version:old.version+1};editorDrafts.set(path,saved);return response(saved);}
  if(path.includes("/drafts/p1/age")){if(method==="GET")return response(draft);if(holdDraft)await draftGate;assert.equal(body.version,draft.version);draft={...draft,version:draft.version+1,data:body.data};return response(draft);}
  if(path.endsWith("/hybrid-index")){indexJob=body.request_id;return indexGate;}
  if(path.includes("/hybrid-jobs/")){const id=path.split('/').at(path.endsWith('/cancel')?-2:-1);if(path.endsWith('/cancel')){phase="cancelling";assert.equal(id,indexJob);}return response({id,kind:id===indexJob?"index":"search",state,detail:state==="running"?"":"model_runtime_failed",retry_allowed:state!=="running",progress:{phase,component:"document",completed_batches:1,total_batches:4,processed_items:2,total_items:8,total_windows:8}});}
  if(path.endsWith("/candidates")){candidateAttempts++;if(candidateAttempts===1)return response({error:{code:"model_runtime_failed",message:"Synthetic model failure; no fallback"}},422);return response({schema_version:"mvp.board-candidates.hybrid.v1",id:"empty-run",board_id:"b",board_revision_id:"r",paper_id:paper.id,field_id:"age",field_revision_id:"field-r2",preparation_id:"prep",source_manifest_sha256:definition.source_manifest_sha256,retrieval_profile_sha256:definition.retrieval_profile_sha256,result:{returned_count:0,profile_id:profile,candidates:[]}});}
  assert.fail("Unexpected request: "+method+" "+path);
 };
 let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<Compare workspace={workspace} requestedBoard="b" navigate={async()=>{}}/>);});
 try{
  assert.ok(requests.every(request=>request.method==="GET"));
  await act(async()=>renderer.root.findByProps({"aria-label":"Age for SYNTHETIC SOFTWARE REPORT"}).props.onClick());
  assert.equal(requests.some(request=>request.path.endsWith("/hybrid-index")||request.path.endsWith("/candidates")||request.path.includes("/hybrid-jobs/")),false);
  await click(renderer,"Continue with notes or missing information");
  const label=renderer.root.findAllByType("label").find(node=>node.children.includes("Manual cell value"))!;
  await act(async()=>label.findByType("textarea").props.onChange({target:{value:"RETAIN THIS SYNTHETIC NOTE"}}));
  holdDraft=true;await click(renderer,"1. Select evidence");
  await observed(()=>requests.some(request=>request.path.endsWith("/drafts/p1/age")&&request.method==="PUT"));
  assert.equal(requests.some(request=>request.path.endsWith("/hybrid-index")||request.path.endsWith("/candidates")),false);
  assert.ok(buttons(renderer,"Index this cell’s source").every(disabled));
  await act(async()=>{holdDraft=false;releaseDraft();});
  await click(renderer,"Index this cell’s source");await observed(()=>requests.some(request=>request.path.endsWith("/hybrid-index")));
  await observed(()=>text(renderer.root).includes("Completed batches: 1 / 4"));
  const index=requests.find(request=>request.path.endsWith("/hybrid-index"))!;
  assert.deepEqual(index.body,{request_id:indexJob,profile_id:profile,device:"cpu",expected_preparation_id:"prep",expected_source_revision:9,board_context:{board_id:"b",board_revision_id:"r",paper_id:paper.id,field_id:"age"}});
  await click(renderer,"Cancel retrieval work");assert.ok(buttons(renderer,"Cancellation requested…").every(disabled));
  state="cancelled";phase="cancelled";await act(async()=>resolveIndex(response({error:{code:"hybrid_cancelled",message:"Cancelled; no result"}},503)));
  await observed(()=>buttons(renderer,"Find excerpts in this paper").some(node=>!disabled(node)));
  assert.equal(requests.filter(request=>request.path.endsWith("/hybrid-index")).length,1);
  assert.equal(candidateAttempts,0);assert.match(text(renderer.root),/Index attempt failed or was cancelled/);
  await click(renderer,"Find excerpts in this paper");await observed(()=>buttons(renderer,"Retry excerpts in this paper").some(node=>!disabled(node)));
  assert.equal(candidateAttempts,1);await act(async()=>{await new Promise<void>(resolve=>setImmediate(resolve));});assert.equal(candidateAttempts,1,"failure does not auto-retry");
  await click(renderer,"Retry excerpts in this paper");await observed(()=>text(renderer.root).includes("0 hybrid passage candidates"));
  const candidates=requests.filter(request=>request.path.endsWith("/candidates"));assert.equal(candidates.length,2);assert.notEqual(candidates[0].body.request_id,candidates[1].body.request_id);
  for(const request of candidates)assert.deepEqual({...request.body,request_id:"opaque"},{expected_revision_id:"r",paper_id:paper.id,field_id:"age",top_k:3,request_id:"opaque"});
  assert.equal(draft.data.value,"RETAIN THIS SYNTHETIC NOTE");assert.equal(draft.data.semantic_assessment,"unassessed");assert.equal(draft.data.references.length,0);assert.equal(draft.data.inspected_ranges.length,0);
  assert.equal(requests.some(request=>/generation|proposal|source-preparations|cell-revisions/.test(request.path)),false);
 }finally{await act(async()=>renderer.unmount());}
});
