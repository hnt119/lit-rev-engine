import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import {SemanticMapSetup,type MapSetup} from "../components/semantic-map-setup";
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(text).join("");
function button(r:ReactTestRenderer,label:string){const b=r.root.findAllByType("button").find(n=>text(n)===label);assert.ok(b,label);return b;}
const fixture=():MapSetup=>({schema_version:"map-setup.v1",profile_id:"paper_bge_v1",model:"BAAI/bge-small-en-v1.5",revision:"pinned",ready:false,reason:"Pinned BGE weights missing.",runtime:{state:"available",versions:{torch:"pinned"},missing:[],incompatible:[],message:"Packages present; computation untested."},weights:{state:"missing",snapshot:"/synthetic-cache/pinned",missing:["model.safetensors"],download_bytes:133000000},configuration:{enabled:true,source:"saved session",cache_dir:"/synthetic-cache"},computation:{state:"not_tested",message:"No explicit computation yet.",tested_at:null},download:{model:"BAAI/bge-small-en-v1.5",revision:"pinned",source:"https://huggingface.co/BAAI/bge-small-en-v1.5/tree/pinned",destination:"/synthetic-cache/pinned",bytes:133000000,manifest_sha256:"pinned-manifest"}});

test("setup reads only; download discloses identity/size/location before separate consent",async()=>{
 const calls:{method:string;body:any}[]=[],busy:boolean[]=[];let current=fixture();
 globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):null;calls.push({method,body});if(path.endsWith("/session"))return Response.json({csrf_token:"synthetic"});if(path.endsWith("/install")){assert.deepEqual(body,{expected_revision:4,manifest_sha256:"pinned-manifest",accept_download:true});current={...current,ready:true,weights:{...current.weights,missing:[],state:"present"}};}return Response.json(current);};
 let r!:ReactTestRenderer;await act(async()=>{r=create(<SemanticMapSetup revision={4} disabled={false} onBusy={v=>busy.push(v)}/>);});
 try{assert.ok(calls.every(c=>c.method==="GET"));assert.match(text(r.root),/Mapping runtime/);assert.match(text(r.root),/Computation check/);assert.equal(button(r,"Verify readiness · local BGE computation").props.disabled,true);
 await act(async()=>button(r,"Review BGE download").props.onClick());assert.match(text(r.root),/133,000,000 bytes/);assert.match(text(r.root),/\/synthetic-cache\/pinned/);assert.match(text(r.root),/BAAI\/bge-small-en-v1.5/);assert.equal(button(r,"Download approved BGE weights").props.disabled,true);
 await act(async()=>button(r,"Cancel without downloading").props.onClick());assert.ok(calls.every(c=>c.method==="GET"));await act(async()=>button(r,"Review BGE download").props.onClick());await act(async()=>r.root.findByType("input").props.onChange({target:{checked:true}}));assert.ok(calls.every(c=>c.method==="GET"));await act(async()=>button(r,"Download approved BGE weights").props.onClick());assert.equal(calls.filter(c=>c.method==="POST").length,1);assert.deepEqual(busy,[true,false]);assert.equal(button(r,"Verify readiness · local BGE computation").props.disabled,false);
 }finally{await act(async()=>r.unmount());}
});

test("verification failure stays visible, explicit retry succeeds, and unsaved edits block work",async()=>{
 let current={...fixture(),ready:true,weights:{...fixture().weights,missing:[],state:"present"}},attempt=0;const writes:any[]=[];
 globalThis.fetch=async(input,options)=>{if(String(input).endsWith("/session"))return Response.json({csrf_token:"synthetic"});if(options?.method==="POST"){writes.push(JSON.parse(String(options.body)));if(++attempt===1)return Response.json({detail:{code:"map_verify_failed",message:"Synthetic verification failure; no map created."}},{status:503});current={...current,computation:{state:"succeeded",message:"Synthetic check completed.",tested_at:null}};}return Response.json(current);};
 let r!:ReactTestRenderer;const props={revision:2,disabled:false,onBusy:()=>{}};await act(async()=>{r=create(<SemanticMapSetup {...props}/>);});
 try{await act(async()=>button(r,"Verify readiness · local BGE computation").props.onClick());assert.match(text(r.root),/Synthetic verification failure/);assert.equal(writes.length,1);await act(async()=>button(r,"Verify readiness · local BGE computation").props.onClick());assert.match(text(r.root),/Synthetic check completed/);assert.deepEqual(writes,[{expected_revision:2},{expected_revision:2}]);await act(async()=>r.update(<SemanticMapSetup {...props} disabled/>));assert.equal(button(r,"Verify readiness · local BGE computation").props.disabled,true);assert.match(text(r.root),/Save or discard/);}finally{await act(async()=>r.unmount());}
});

test("unavailable readiness has GET-only recovery",async()=>{
 let fail=true;const calls:string[]=[];globalThis.fetch=async(input,options)=>{calls.push(options?.method??"GET");if(String(input).endsWith("/session"))return Response.json({csrf_token:"synthetic"});if(fail)return Response.json({detail:{code:"unavailable",message:"Synthetic backend unavailable"}},{status:503});return Response.json(fixture());};
 let r!:ReactTestRenderer;await act(async()=>{r=create(<SemanticMapSetup revision={0} disabled={false} onBusy={()=>{}}/>);});
 try{assert.match(text(r.root),/Readiness could not be read/);fail=false;await act(async()=>button(r,"Refresh map readiness").props.onClick());assert.match(text(r.root),/Pinned BGE weights missing/);assert.ok(calls.every(m=>m==="GET"));}finally{await act(async()=>r.unmount());}
});
