import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import {HybridPassages} from "../components/hybrid-passages";
import {RetrievalPacks} from "../components/retrieval-packs";
import type {Schema} from "../lib/api";
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,window:{addEventListener(){},removeEventListener(){}}});
const text=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(text).join("");
const button=(renderer:ReactTestRenderer,label:string)=>renderer.root.findAllByType("button").find(node=>text(node)===label)!;
const workspace={id:"progress-software-test",current_preparation_id:"prep",source_revision:1} as Schema<"WorkspaceSummary">;
const profile="hybrid_qwen3_06b_rrf_rerank_v1";

test("dependency-needed is separate from installed weights; opening never installs or executes",async()=>{
 const calls:{path:string;method:string}[]=[];
 globalThis.fetch=async(input,options)=>{calls.push({path:String(input),method:options?.method??"GET"});return Response.json({packs:[{profile_id:profile,label:"Qwen optional pack",state:"installed",installed:true,download_bytes:3000000000,downloaded_bytes:3000000000,models:[],license:"Apache-2.0",quality_status:"experimental",message:"Installed pinned files",runtime:null,dependencies:{state:"needed",missing:["torch"],incompatible:[],install_hint:"python3 scripts/local_preview.py setup --with-retrieval"}}]});};
 let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<RetrievalPacks revision={0} disabled={false} device="cpu"/>);});
 try{assert.match(text(renderer.root),/installed · Installed pinned files/);assert.match(text(renderer.root),/dependencies needed/);assert.match(text(renderer.root),/--with-retrieval/);assert.equal(button(renderer,"Check runtime · CPU").props.disabled,true);assert.ok(calls.every(call=>call.method==="GET"));}finally{await act(async()=>renderer.unmount());}
});

test("actual-job polling shows batches and cooperative cancellation; retry creates a new explicit job",async()=>{
 const calls:{path:string;method:string;body:any}[]=[],values=new Map<string,string>();Object.assign(globalThis,{sessionStorage:{getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>values.set(key,value),removeItem:(key:string)=>values.delete(key)}});
 let resolveIndex!:(value:Response)=>void,phase="embedding",state="running",pending=new Promise<Response>(resolve=>resolveIndex=resolve);
 globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):null;calls.push({path,method,body});if(path.endsWith("/session"))return Response.json({csrf_token:"software"});if(path.endsWith("/hybrid-runs"))return Response.json({runs:[]});if(path.endsWith("/hybrid-index"))return pending;if(path.endsWith("/cancel")){phase="cancelling";return Response.json({id:path.split('/').at(-2),kind:"index",state,detail:"",progress:{phase,completed_batches:1,total_batches:4,processed_items:2,total_items:8}});}if(path.includes("/hybrid-jobs/"))return Response.json({id:path.split('/').at(-1),kind:"index",state,detail:state==="cancelled"?"hybrid_cancelled":"",retry_allowed:state==="cancelled",progress:{phase,component:"document",completed_batches:1,total_batches:4,processed_items:2,total_items:8,total_windows:8}});throw Error("Unexpected "+path);};
 let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<HybridPassages workspace={workspace} profile={profile} device="cpu" question="Software query" topK={5} ready={true} saveDraft={async()=>{}} navigate={async()=>{}}/>);});
 try{assert.ok(calls.every(call=>call.method==="GET"));act(()=>{void button(renderer,"Index these sources").props.onClick();});await act(async()=>{await new Promise<void>(resolve=>setImmediate(resolve));});assert.match(text(renderer.root),/Completed batches: 1 \/ 4/);assert.match(text(renderer.root),/processed items: 2 \/ 8/);assert.match(text(renderer.root),/not a durable background task/);await act(async()=>button(renderer,"Cancel retrieval work").props.onClick());assert.equal(button(renderer,"Cancellation requested…").props.disabled,true);state="cancelled";phase="cancelled";await act(async()=>resolveIndex(new Response(JSON.stringify({error:{code:"hybrid_cancelled",message:"Cancelled; no fallback"}}),{status:503})));assert.ok(button(renderer,"Retry indexing these sources"));const first=calls.find(call=>call.path.endsWith("/hybrid-index"))!.body.request_id;pending=Promise.resolve(Response.json({state:"ready"}));state="completed";phase="completed";await act(async()=>button(renderer,"Retry indexing these sources").props.onClick());const attempts=calls.filter(call=>call.path.endsWith("/hybrid-index"));assert.equal(attempts.length,2);assert.notEqual(attempts[1].body.request_id,first);assert.equal(calls.some(call=>call.path.endsWith("/hybrid-runs")&&call.method==="POST"),false);}finally{await act(async()=>renderer.unmount());}
});

test("comparison progress projection only reads the exact recorded job",async()=>{
 const {PollingHybridJobStatus}=await import("../components/hybrid-job-progress");const calls:{path:string;method:string}[]=[];
 globalThis.fetch=async(input,options)=>{calls.push({path:String(input),method:options?.method??"GET"});return Response.json({id:"exact-job",kind:"index",state:"interrupted",detail:"Backend restarted; explicitly start a new operation.",retry_allowed:true,progress:{phase:"interrupted",completed_batches:3,total_batches:9,processed_items:6,total_items:18}});};
 let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<PollingHybridJobStatus endpoint="workspaces/progress" jobId="exact-job" active={false}/>);});
 try{assert.deepEqual(calls,[{path:"/api/v1/workspaces/progress/hybrid-jobs/exact-job",method:"GET"}]);assert.match(text(renderer.root),/Completed batches: 3 \/ 9/);assert.match(text(renderer.root),/interrupted/);assert.match(text(renderer.root),/not a durable background task/);}finally{await act(async()=>renderer.unmount());}
});
