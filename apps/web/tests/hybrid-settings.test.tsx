import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import {RetrievalPacks} from "../components/retrieval-packs";
import {HybridPassages} from "../components/hybrid-passages";
import {allowedRoute,allowedQuery} from "../lib/bridge";
import type {Schema} from "../lib/api";
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,window:{addEventListener(){},removeEventListener(){}}});
const text=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(text).join("");
function button(renderer:ReactTestRenderer,label:string){const value=renderer.root.findAllByType("button").find(node=>text(node)===label);assert.ok(value,label);return value;}
const pack={profile_id:"hybrid_qwen3_06b_rrf_rerank_v1",label:"Qwen optional pack",state:"not_installed",installed:false,download_bytes:12345,downloaded_bytes:0,models:[{repo:"Qwen/Qwen3-Embedding-0.6B",revision:"a".repeat(40),bytes:12345}],license:"Apache-2.0",quality_status:"experimental",message:"Explicit installation required.",runtime:null};

test("pack availability reads make no model actions; install is explicit and revision bound",async()=>{
 const calls:{path:string;method:string;body:any}[]=[];
 globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):null;calls.push({path,method,body});if(path.endsWith("/session"))return Response.json({csrf_token:"test"});return Response.json(path.endsWith("/install")?pack:{packs:[pack]});};
 let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<RetrievalPacks revision={7} device="cpu" disabled={false}/>);});
 try{assert.ok(calls.every(call=>call.method==="GET"));assert.match(text(renderer.root),/12,345 bytes/);assert.equal(button(renderer,"Check runtime · CPU").props.disabled,true);await act(async()=>button(renderer,"Install Qwen optional pack").props.onClick());const writes=calls.filter(call=>call.method!=="GET");assert.equal(writes.length,1);assert.equal(writes[0].path,"/api/v1/settings/retrieval/install");assert.deepEqual(writes[0].body,{expected_revision:7,profile_id:pack.profile_id,device:"cpu"});}finally{await act(async()=>renderer.unmount());}
});

test("hybrid page reads only saved history; source indexing and retrieval are separate explicit actions",async()=>{
 const calls:{path:string;method:string}[]=[];let saves=0;
 globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET";calls.push({path,method});if(path.endsWith("/session"))return Response.json({csrf_token:"test"});if(path.endsWith("/hybrid-runs"))return Response.json({runs:[]});if(path.endsWith("/hybrid-index"))return Response.json({state:"ready"});throw new Error(path);};
 const workspace={id:"w",current_preparation_id:"prep",source_revision:1} as Schema<"WorkspaceSummary">;
 let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<HybridPassages workspace={workspace} profile={pack.profile_id} device="cpu" question="Full explicit question" topK={5} ready={true} saveDraft={async()=>{saves++;}} navigate={async()=>{}}/>);});
 try{assert.ok(calls.every(call=>call.method==="GET"));assert.match(text(renderer.root),/Index these sources/);await act(async()=>button(renderer,"Index these sources").props.onClick());assert.equal(saves,1);assert.equal(calls.filter(call=>call.method==="POST").length,1);assert.equal(calls.find(call=>call.method==="POST")?.path,"/api/v1/workspaces/w/hybrid-index");assert.match(text(renderer.root),/Source index: ready/);assert.ok(!calls.some(call=>call.path.includes("settings/retrieval/install")));}finally{await act(async()=>renderer.unmount());}
});

test("hybrid bridge routes are narrowly allowlisted without arbitrary query parameters",()=>{
 for(const [method,path] of [["GET","settings/retrieval"],["POST","settings/retrieval/install"],["POST","workspaces/w/hybrid-index"],["POST","workspaces/w/hybrid-index/status"],["POST","workspaces/w/hybrid-runs"],["GET","workspaces/w/hybrid-runs/r/candidates/c/context"],["GET","workspaces/w/hybrid-exports"],["POST","workspaces/w/hybrid-jobs/j/cancel"]])assert.equal(allowedRoute(method,path),true,path);
 assert.equal(allowedRoute("POST","settings/retrieval/arbitrary-model"),false);
 assert.equal(allowedQuery("settings/retrieval",new URLSearchParams("download=1")),false);
 assert.equal(allowedQuery("workspaces/w/hybrid-index",new URLSearchParams("device=cuda"),"POST"),false);
});

test("pending configuration cannot execute a lexical fallback before a saved hybrid selection resolves",async()=>{
 const {default:Evidence}=await import("../components/evidence");
 const writes:string[]=[];let resolveSettings!:(response:Response)=>void;
 const pending=new Promise<Response>(resolve=>{resolveSettings=resolve;});
 globalThis.fetch=async(input,options)=>{const path=String(input);if(options?.method&&options.method!=="GET")writes.push(path);if(path.endsWith("/session"))return Response.json({csrf_token:"test"});if(path.endsWith("/settings"))return pending;if(path.endsWith("/drafts/evidence"))return Response.json({version:0,data:{},expected_assessment_head:null});if(path.endsWith("/hybrid-runs"))return Response.json({runs:[]});throw new Error(path);};
 const values=new Map<string,string>();Object.assign(globalThis,{sessionStorage:{getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>values.set(key,value),removeItem:(key:string)=>values.delete(key)}});
 const workspace={id:"pending",question:"Full review question",current_preparation_id:"prep",source_revision:1,current_run_id:null,runs:[]} as unknown as Schema<"WorkspaceSummary">;
 let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<Evidence workspace={workspace} refresh={async()=>{}} navigate={async()=>{}}/>);});
 try{assert.equal(button(renderer,"Retrieve passages").props.disabled,true);await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));assert.deepEqual(writes,[]);await act(async()=>resolveSettings(Response.json({preferences:{retrieval:{profile_id:pack.profile_id,device:"cpu"}}})));assert.match(text(renderer.root),/EXPERIMENTAL LOCAL HYBRID RETRIEVAL/);assert.deepEqual(writes,[]);await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));assert.deepEqual(writes,[]);assert.match(text(renderer.root),/Use Retrieve hybrid passages below/);}finally{await act(async()=>renderer.unmount());}
});
