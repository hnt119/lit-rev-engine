import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import {CollectionPreparationJobs} from "../components/preparation-jobs";
import {response,storage} from "./import-collection-fixtures";
import {research} from "./collection-research-fixtures";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
const button=(renderer:ReactTestRenderer,label:string)=>renderer.root.findAllByType("button").find(item=>text(item)===label)!;
const deferred=<T,>()=>{let resolve!:(value:T)=>void;const promise=new Promise<T>(done=>resolve=done);return{promise,resolve};};

test("collection preparation freezes the exact collection digest and clicked papers before flushing; ambiguous retry cannot retarget it",async()=>{
  const f=research("frozen-collection"),gate=deferred<void>(),calls:{path:string;method:string;body:any}[]=[];let posts=0,flushes=0;
  Object.assign(globalThis,{sessionStorage:storage()});globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;calls.push({path,method,body});if(path.endsWith("/session"))return response({csrf_token:"software"});if(method==="GET"&&path.includes("/collection-preparation-jobs?"))return response({jobs:[]});if(method==="POST"&&path.endsWith("/collection-preparation-jobs")){if(posts++===0)throw new Error("Synthetic ambiguous response");return response({job:f.job(),reused:true});}throw new Error("Unexpected software-test request "+path);};
  const props={workspace:{...f.state,current_preparation_id:null,source_revision:0},collectionRef:f.collectionRef,papers:f.papers,selectedPaperIds:f.papers.map(item=>item.id),selectionReady:true,maxSources:30,flushSelection:async()=>{flushes++;await gate.promise;},refresh:async()=>{},onPublished:()=>{assert.fail("Queued sources must not become current");}};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<CollectionPreparationJobs {...props}/>);});
  try{
    let submitting!:Promise<void>;act(()=>{submitting=button(renderer,"Prepare selected sources").props.onClick();});assert.equal(calls.filter(call=>call.method==="POST").length,0);
    await act(async()=>renderer.update(<CollectionPreparationJobs {...props} selectedPaperIds={[f.papers[2].id]}/>));await act(async()=>{gate.resolve();await submitting;});
    await act(async()=>button(renderer,"Retry same submission").props.onClick());const submitted=calls.filter(call=>call.method==="POST");assert.equal(submitted.length,2);assert.deepEqual(submitted[0].body,submitted[1].body);assert.deepEqual(submitted[0].body.collection_ref,f.collectionRef);assert.deepEqual(submitted[0].body.paper_ids,f.papers.map(item=>item.id));assert.equal("search_id" in submitted[0].body,false);assert.equal(flushes,1);
  }finally{await act(async()=>renderer.unmount());}
});

test("reopened collection jobs publish only their current exact preparation and retain abstract-only outcomes",async context=>{
  context.mock.timers.enable({apis:["setTimeout"]});const f=research("reopened-collection"),published:string[]=[],calls:string[]=[];
  globalThis.fetch=async(input,options)=>{const path=String(input);calls.push(path);assert.equal(options?.method??"GET","GET");if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.includes("/collection-preparation-jobs?"))return response({jobs:[f.job({status:"running"})]});if(path.includes("/collection-preparation-jobs/"))return response(f.job({status:"succeeded",progress_completed:3,result_preparation_id:f.preparation.id,result_source_revision:1,outcomes:f.job().outcomes.map(item=>({...item,outcome:"abstract_only",source_type:"abstract",source_status:"abstract_only"}))}));if(path.endsWith("/source-preparations/"+f.preparation.id))return response(f.preparation);if(path.endsWith("/"+f.state.id))return response(f.state);throw new Error("Unexpected software-test GET "+path);};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<CollectionPreparationJobs workspace={f.state} collectionRef={f.collectionRef} papers={f.papers} selectedPaperIds={f.preparation.selected_paper_ids} selectionReady maxSources={30} flushSelection={async()=>{}} refresh={async()=>{}} onPublished={value=>{published.push(value.id);}}/>);});
  try{assert.deepEqual(published,[]);await act(async()=>context.mock.timers.tick(1500));assert.deepEqual(published,[f.preparation.id]);assert.match(text(renderer.root),/0 full text · 3 abstract only/);const reads=calls.length;await act(async()=>context.mock.timers.tick(20000));assert.equal(calls.length,reads);assert.equal(calls.some(path=>path.includes("/searches/")),false);}
  finally{await act(async()=>renderer.unmount());}
});

test("wrong collection snapshot receipts are rejected without applying sources or starting replacement work",async()=>{
  const f=research("wrong-collection"),published:string[]=[];let mutations=0;
  globalThis.fetch=async(input,options)=>{const path=String(input);if((options?.method??"GET")!=="GET")mutations++;if(path.endsWith("/session"))return response({csrf_token:"software"});return response({jobs:[f.job({collection_ref:{...f.collectionRef,collection_snapshot_sha256:"0".repeat(64)}})]});};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<CollectionPreparationJobs workspace={f.state} collectionRef={f.collectionRef} papers={f.papers} selectedPaperIds={f.preparation.selected_paper_ids} selectionReady maxSources={30} flushSelection={async()=>{}} refresh={async()=>{}} onPublished={value=>{published.push(value.id);}}/>);});
  try{assert.match(text(renderer.root),/do not belong to this retained paper snapshot/);assert.deepEqual(published,[]);assert.equal(mutations,0);assert.equal(button(renderer,"Prepare selected sources").props.disabled,true);}
  finally{await act(async()=>renderer.unmount());}
});
