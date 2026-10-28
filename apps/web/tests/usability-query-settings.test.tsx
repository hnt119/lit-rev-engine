import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import SearchPlanner from "../components/search-planner";
import ResearchSettings from "../components/research-settings";
import {RetrievalPacks} from "../components/retrieval-packs";
import type {RuntimeSettings} from "../lib/runtime-settings";
import {capability,draft,response,saved,workspace} from "./search-planner-fixtures";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,window:{addEventListener(){},removeEventListener(){}}});
const text=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(text).join("");
function button(renderer:ReactTestRenderer,label:string){const value=renderer.root.findAllByType("button").find(node=>text(node)===label);assert.ok(value,label);return value;}
function storage(){const values=new Map<string,string>();Object.assign(globalThis,{sessionStorage:{getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>values.set(key,value),removeItem:(key:string)=>values.delete(key)}});}
const settings:RuntimeSettings={schema_version:"runtime-settings.v1",revision:1,configured:true,preferences:{pubmed:{enabled:true,email:"public-fixture@example.org"},ai:{provider:"none",model:"",model_revision:"",local_url:"",planning_enabled:false,proposals_enabled:false},defaults:{max_results:10,sort:"relevance"},maps:{cache_dir:""}},credentials:{ncbi_api_key:false,ai_api_key:false},status:{pubmed:{state:"not_tested",message:"Not tested."},ai:{state:"disabled",message:"No model configured."},maps:{state:"disabled",message:"Optional setup."}},operator_configuration:"unchanged"};
const pack={profile_id:"hybrid_qwen3_06b_rrf_rerank_v1",label:"Qwen fixture pack",state:"not_installed",installed:false,download_bytes:10,downloaded_bytes:0,models:[],license:"Apache-2.0",quality_status:"experimental",message:"Explicit install required.",runtime:null};

test("failed pack availability stops claiming loading; retry is a local status read only",async()=>{
  const calls:{path:string;method:string}[]=[];let reads=0;
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET";calls.push({path,method});assert.equal(method,"GET");if(path.endsWith("/session"))return response({csrf_token:"test"});assert.ok(path.endsWith("/settings/retrieval"));return ++reads===1?response({detail:{code:"unavailable",message:"Local availability unavailable."}},503):response({packs:[pack]});};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<RetrievalPacks revision={1} device="cpu" disabled={false}/>);});
  try{
    assert.match(text(renderer.root),/availability could not be loaded/);assert.doesNotMatch(text(renderer.root),/Reading optional model-pack availability/);
    await act(async()=>button(renderer,"Retry retrieval availability").props.onClick());
    assert.match(text(renderer.root),/Qwen fixture pack/);assert.equal(reads,2);assert.ok(calls.every(call=>call.method==="GET"));assert.equal(button(renderer,"Check runtime · CPU").props.disabled,true);
  }finally{await act(async()=>renderer.unmount());}
});

test("an empty pack list is an honest terminal state with safe refresh",async()=>{
  globalThis.fetch=async()=>response({packs:[]});
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<RetrievalPacks revision={1} device="cpu" disabled={true}/>);});
  try{assert.match(text(renderer.root),/No optional model packs were reported/);assert.doesNotMatch(text(renderer.root),/Reading optional model-pack availability/);assert.equal(button(renderer,"Retry retrieval availability").props.disabled,undefined);}finally{await act(async()=>renderer.unmount());}
});

test("settings read failures have a GET-only retry and dirty PubMed tests explain the saved prerequisite",async()=>{
  let reads=0;const writes:string[]=[];storage();
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET";if(method!=="GET")writes.push(path);if(path.endsWith("/settings/retrieval"))return response({packs:[]});assert.ok(path.endsWith("/settings"));return ++reads===1?response({detail:{code:"unavailable",message:"Local settings unavailable."}},503):response(settings);};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<ResearchSettings onReturn={async()=>{}}/>);});
  try{
    assert.match(text(renderer.root),/settings could not be loaded/);assert.doesNotMatch(text(renderer.root),/Loading private local settings/);
    await act(async()=>button(renderer,"Retry loading settings").props.onClick());assert.equal(reads,2);assert.equal(button(renderer,"Test PubMed connection").props.disabled,false);
    const email=renderer.root.findAllByType("label").find(node=>text(node).startsWith("NCBI contact email"))!.findByType("input");
    await act(async()=>email.props.onChange({target:{value:"edited-fixture@example.org"}}));
    assert.equal(button(renderer,"Test PubMed connection").props.disabled,true);assert.match(text(renderer.root),/Save settings before testing the PubMed connection/);assert.deepEqual(writes,[]);
    await act(async()=>button(renderer,"Discard unsaved settings").props.onClick());assert.equal(button(renderer,"Test PubMed connection").props.disabled,false);
  }finally{await act(async()=>renderer.unmount());}
});

test("search-planning availability retry keeps the recovered question and cannot execute a provider or model",async()=>{
  storage();let capabilityReads=0;const calls:{path:string;method:string}[]=[],retained={...draft(),original_question:"Retained public fixture question 日本?"};
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET";calls.push({path,method});assert.equal(method,"GET");if(path.includes("/drafts/"))return response({scope:"search-plan-editor:new",version:1,data:{draft:retained,plan_id:null,base_revision_id:null},expected_assessment_head:null,updated_at:null});if(path.endsWith("/search-plan-capabilities"))return ++capabilityReads===1?response({detail:{code:"unavailable",message:"Capabilities unavailable."}},503):response(capability());assert.ok(path.endsWith("/search-plans"));return response({plans:[]});};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<SearchPlanner workspace={workspace("usability-retry-public")} initialQuestion="New question" onOpen={async()=>{}} onExecuted={async()=>{assert.fail("No execution authorized");}}/>);});
  try{
    assert.match(text(renderer.root),/availability could not be loaded/);assert.doesNotMatch(text(renderer.root),/Loading local search-planning capabilities/);
    await act(async()=>button(renderer,"Retry search-planning availability").props.onClick());
    const question=renderer.root.findAllByType("label").find(node=>text(node).startsWith("Original research question"))!.findByType("textarea");
    assert.equal(question.props.value,retained.original_question);assert.equal(capabilityReads,2);assert.equal(button(renderer,"Propose search with optional AI").props.disabled,true);assert.equal(button(renderer,"Suggest editable concepts").props.disabled,false);assert.ok(calls.every(call=>call.method==="GET"));
    assert.match(text(renderer.root),/Build reviewed Boolean strategies → Save search for review → Approve the exact query/);
  }finally{await act(async()=>renderer.unmount());}
});

test("retrying availability does not abandon an in-flight exact saved-plan read",async()=>{
  storage();let reads=0,release!:(value:Response)=>void;const plan=saved(),pending=new Promise<Response>(resolve=>{release=resolve;});
  globalThis.fetch=async(input,options)=>{const path=String(input);assert.equal(options?.method??"GET","GET");if(path.includes("/drafts/"))return response({scope:"search-plan-editor:software-plan",version:0,data:{},expected_assessment_head:null,updated_at:null});if(path.endsWith("/search-plan-capabilities"))return ++reads===1?response({detail:{message:"Availability failed."}},503):response(capability());if(path.endsWith("/search-plans/software-plan"))return pending;assert.ok(path.endsWith("/search-plans"));return response({plans:plan.revisions});};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<SearchPlanner workspace={workspace("usability-retry-pending-plan")} initialQuestion="Initial question" requestedPlan="software-plan" onOpen={async()=>{}} onExecuted={async()=>{assert.fail("No execution authorized");}}/>);});
  try{
    await act(async()=>button(renderer,"Retry search-planning availability").props.onClick());
    await act(async()=>release(response(plan)));
    assert.match(text(renderer.root),/SAVED PLAN REVISION 1/);assert.doesNotMatch(text(renderer.root),/LOADING SAVED REVISION/);assert.match(text(renderer.root),/Focused lichen query/);
  }finally{await act(async()=>renderer.unmount());}
});
