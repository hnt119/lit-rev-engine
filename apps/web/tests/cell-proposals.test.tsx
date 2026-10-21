import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import {CellProposals,ProposalControls} from "../components/cell-proposals.tsx";
import {emptyCell,type useBoardDraft} from "../lib/board-drafts.tsx";
import type {Schema} from "../lib/api.ts";
import {flushDrafts} from "../lib/drafts.tsx";

const pending=new Map<string,string>();
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,sessionStorage:{getItem:(key:string)=>pending.get(key)??null,setItem:(key:string,value:string)=>pending.set(key,value),removeItem:(key:string)=>pending.delete(key)}});
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}});
function text(node:ReactTestInstance):string{return node.children.map(child=>typeof child==="string"?child:text(child)).join("");}
function button(renderer:ReactTestRenderer,label:string){const found=renderer.root.findAllByType("button").find(item=>text(item)===label);assert.ok(found,label);return found;}
function disabled(node:ReactTestInstance):boolean {return !!node.props.disabled||!!node.parent&&disabled(node.parent);}
function field(renderer:ReactTestRenderer,label:string){const found=renderer.root.findAllByType("label").find(node=>node.children.includes(label));assert.ok(found,label);return found.findByType("textarea");}
const view={definition:{board_id:"b",revision_id:"r",paper_ids:["p1","p2","p3"],papers:[1,2,3].map(i=>({id:"p"+i,title:"Software report "+i})),fields:[{id:"f",label:"Population"}]},freshness:"current"} as unknown as Schema<"BoardView">;
const cap={enabled:true,reason:"Software adapter only",model_profile:null,max_papers:3,max_fields:6,max_cells:9,max_calls:3,max_runtime_seconds:35} as Schema<"ProposalCapability">;
const reference={id:"ref",quote:"Chinese women 😀",start:0,end:15,block_id:"block",source_id:"s",source_version:"v1",source_sha256:"a".repeat(64),blocks_sha256:"b".repeat(64),paper_id:"p1",locator:{type:"abstract"},integrity:"checked"} as Schema<"BoardReference">;
const suggestion={id:"q",run_id:"run",paper_id:"p1",status:"pending",value:"Chinese women",reason:"Unreviewed model reason",missing_information:"Ages were not in retrieved context",references:[reference],created_at:"2026-10-21T00:00:00Z",semantic_assessment:"unassessed",review_state:"ai_suggestion_needs_review_not_independently_verified",context_scope:"retrieved_context_only"} as Schema<"CellProposal">;

test("disabled proposals remain read-only and enabled generation requires an explicit selected-cell action",async()=>{
  const writes:{path:string;body:Record<string,unknown>}[]=[];
  let enabled=false;
  globalThis.fetch=async(url,options)=>{
    const path=String(url);
    if(path.endsWith("/session"))return response({csrf_token:"test"});
    if(path.endsWith("/proposal-capabilities"))return response({...cap,enabled});
    if(path.includes("/proposals?"))return response({items:[],runs:[],offset:0,limit:1,total:0,capability:cap});
    assert.equal(options?.method,"POST");writes.push({path,body:JSON.parse(String(options?.body))});
    return response({id:"run",state:"failed",failure_message:"Software provider failure: no publication."});
  };
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<ProposalControls endpoint="test/boards/b" view={view} changed={()=>{}}/>);});
  assert.equal(writes.length,0);assert.equal(disabled(button(renderer,"Generate proposals for selected cells")),true);
  await act(async()=>renderer.unmount());enabled=true;
  await act(async()=>{renderer=create(<ProposalControls endpoint="test/boards/b" view={view} changed={()=>{}}/>);});
  assert.equal(writes.length,0);assert.equal(disabled(button(renderer,"Generate proposals for selected cells")),false);
  await act(async()=>button(renderer,"Generate proposals for selected cells").props.onClick());
  assert.equal(writes.length,1);assert.deepEqual(writes[0].body.paper_ids,["p1","p2","p3"]);assert.deepEqual(writes[0].body.field_ids,["f"]);
  assert.equal(writes[0].body.expected_revision_id,"r");assert.match(text(renderer.root),/Software provider failure/);
  await act(async()=>renderer.unmount());
});

async function cellFixture({historical=false,existing=false,conflict=false,nullValue=false}={}){
  const data={...emptyCell(),...(existing?{value:"Existing human draft"}:{})};
  const writes:{path:string;body:Record<string,unknown>}[]=[];
  let reloads=0,inspections=0,adoptions=0,proposal={...suggestion,...(nullValue?{value:null,references:[],missing_information:"Insufficient retrieved context"}:{})};
  const draft={data,ready:true,state:"saved",error:"",version:4,expectedHead:null,save:async()=>{},reload:async()=>{reloads++;},snapshot:()=>({version:4,expectedHead:null,data})} as unknown as ReturnType<typeof useBoardDraft>;
  globalThis.fetch=async(url,options)=>{
    const path=String(url);
    if(path.endsWith("/session"))return response({csrf_token:"test"});
    if(path.includes("/proposals?"))return response({items:[proposal],offset:0,limit:5,total:1,runs:[],capability:cap});
    if(path.endsWith('/proposal-runs/run'))return response({packets:[{paper_id:'p1',source_type:'abstract',evidence_characters:15,omitted_evidence:1,fields:[{field_id:'f',label:'Population',evidence_ids:['e'],matched_blocks:4,indexed_blocks:8,omitted_matched_blocks:1,omitted_evidence:1}],evidence:[]}]});
    const body=JSON.parse(String(options?.body));writes.push({path,body});
    if(conflict)return response({error:{code:"stale_board_draft",message:"Newer draft. Your edits are preserved."}},409);
    proposal={...proposal,status:path.endsWith("/dismiss")?"dismissed":"adopted"};return response(proposal);
  };
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<CellProposals endpoint="test/boards/b" view={{...view,freshness:historical?"historical":"current"}} paperId="p1" fieldId="f" draft={draft} editable={!historical} refresh={0} inspect={async()=>{inspections++;}} adopted={async()=>{adoptions++;}}/>);});
  return {renderer,writes,counts:()=>({reloads,inspections,adoptions})};
}

test("inspection, editing, adoption and dismissal remain separate from human submission",async()=>{
  const c=await cellFixture();
  assert.match(text(c.renderer.root),/AI suggestion — needs review/);assert.match(text(c.renderer.root),/HUMAN SUPPORT UNASSESSED/);assert.equal(c.writes.length,0);
  await act(async()=>button(c.renderer,"Inspect suggestion reference 1").props.onClick());
  assert.equal(c.counts().inspections,1);assert.equal(c.writes.length,0);
  await act(async()=>button(c.renderer,"Inspect generation context and coverage").props.onClick());
  assert.match(text(c.renderer.root),/abstract · incomplete retrieved context/);assert.match(text(c.renderer.root),/4 matched \/ 8 indexed/);assert.equal(c.writes.length,0);
  await act(async()=>field(c.renderer,"Proposed value · editable").props.onChange({target:{value:"Researcher-edited proposed value"}}));
  await act(async()=>button(c.renderer,"Use in draft").props.onClick());
  assert.equal(c.writes.length,1);assert.match(c.writes[0].path,/\/adopt$/);assert.equal(c.writes[0].body.value,"Researcher-edited proposed value");
  assert.equal(c.writes[0].body.draft_version,4);assert.equal("semantic_assessment" in c.writes[0].body,false);assert.equal("inspected_ranges" in c.writes[0].body,false);
  assert.deepEqual(c.counts(),{reloads:1,inspections:1,adoptions:1});assert.match(text(c.renderer.root),/does not mean the value was submitted/);
  assert.ok(c.writes.every(item=>!item.path.endsWith("/cell-revisions")));
  await act(async()=>c.renderer.unmount());
  const d=await cellFixture();await act(async()=>button(d.renderer,"Dismiss").props.onClick());assert.match(d.writes[0].path,/\/dismiss$/);assert.equal(d.counts().reloads,0);
  await act(async()=>d.renderer.unmount());
});

test("existing drafts are protected and stale adoption preserves proposal edits without rebasing",async()=>{
  const c=await cellFixture({existing:true});assert.equal(disabled(button(c.renderer,"Use in draft")),true);assert.match(text(c.renderer.root),/Existing values and edits are preserved/);assert.equal(c.writes.length,0);await act(async()=>c.renderer.unmount());
  const d=await cellFixture({conflict:true});
  await act(async()=>field(d.renderer,"Proposed value · editable").props.onChange({target:{value:"Keep these local proposal edits"}}));
  await act(async()=>button(d.renderer,"Use in draft").props.onClick());
  assert.match(text(d.renderer.root),/Newer draft/);assert.equal(field(d.renderer,"Proposed value · editable").props.value,"Keep these local proposal edits");assert.deepEqual(d.counts(),{reloads:0,inspections:0,adoptions:0});await act(async()=>d.renderer.unmount());
});

test("null suggestions retain missing information and historical suggestions cannot be adopted or dismissed",async()=>{
  const c=await cellFixture({nullValue:true});await act(async()=>button(c.renderer,"Use in draft").props.onClick());assert.equal(c.writes[0].body.value,null);assert.equal(c.writes[0].body.missing_information,"Insufficient retrieved context");assert.equal("scope_result" in c.writes[0].body,false);await act(async()=>c.renderer.unmount());
  const d=await cellFixture({historical:true});assert.equal(d.renderer.root.findAllByType("button").some(node=>text(node)==="Use in draft"||text(node)==="Dismiss"),false);await act(async()=>button(d.renderer,"Inspect suggestion reference 1").props.onClick());assert.equal(d.counts().inspections,1);assert.equal(d.writes.length,0);await act(async()=>d.renderer.unmount());
});

test("navigation waits for acknowledged adoption and the restored manual draft baseline",async()=>{
  const c=await cellFixture();const original=globalThis.fetch;
  let entered!:()=>void,release!:()=>void,adoption!:Promise<void>;
  const started=new Promise<void>(resolve=>{entered=resolve;}),gate=new Promise<void>(resolve=>{release=resolve;});
  globalThis.fetch=async(url,options)=>{if(String(url).endsWith('/adopt')){entered();await gate;}return original(url,options);};
  await act(async()=>{adoption=button(c.renderer,'Use in draft').props.onClick();await started;});
  let navigated=false;const navigation=flushDrafts().then(()=>{navigated=true;});
  assert.equal(navigated,false);assert.equal(c.counts().reloads,0);
  await act(async()=>{release();await adoption;await navigation;});
  assert.equal(navigated,true);assert.equal(c.counts().reloads,1);assert.equal(c.counts().adoptions,1);
  await act(async()=>c.renderer.unmount());
});
