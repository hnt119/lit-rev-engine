import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Compare from "../components/compare";
import {flushDrafts,recoverDrafts,registerDraftFlusher} from "../lib/drafts";
import {research} from "./collection-research-fixtures";
import {response,storage,stamp} from "./import-collection-fixtures";
import type {LocationState} from "../components/workspace-app";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,document:{getElementById:()=>null}});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
function button(renderer:ReactTestRenderer,label:string){const node=renderer.root.findAllByType("button").find(item=>text(item)===label);assert.ok(node,label);return node;}
function control(renderer:ReactTestRenderer,label:string){const node=renderer.root.findAllByType("label").find(item=>item.children.filter(child=>typeof child==="string").join("")===label);assert.ok(node,label);return node.findAll(item=>["input","select","textarea"].includes(String(item.type)))[0];}
function disabled(node:ReactTestInstance):boolean {for(let item:ReactTestInstance|null=node;item;item=item.parent)if(item.props.disabled)return true;return false;}
async function tick(){await act(async()=>{await new Promise<void>(resolve=>setImmediate(resolve));});}
async function observed(check:()=>boolean){const until=Date.now()+2000;while(!check()){assert.ok(Date.now()<until,"Expected fixture event did not arrive");await tick();}}
function gate(){let release!:()=>void;const promise=new Promise<void>(resolve=>{release=resolve;});return {promise,release};}

async function fixture(id:string,{loading=false,revision=false}={}){
  const f=research(id),requests:{path:string;method:string;body:any}[]=[],destinations:LocationState[]=[];
  const listeners=new Map<string,EventListener>();let allowDiscard=false,failedSave=false,saveGate:ReturnType<typeof gate>|null=null;
  const loadGate=loading?gate():null;
  Object.assign(globalThis,{sessionStorage:storage(),window:{addEventListener:(name:string,listener:EventListener)=>listeners.set(name,listener),removeEventListener:(name:string)=>listeners.delete(name),confirm:()=>allowDiscard}});
  const definition={board_id:"existing",revision_id:"original-revision",workspace_id:f.state.id,parent_revision_id:null,collection_ref:f.collectionRef,preparation_id:f.preparation.id,source_revision:1,paper_ids:f.preparation.selected_paper_ids,papers:f.papers,sources:f.sources.map(source=>({...source,source_id:source.id})),question:"Original board question",fields:[{id:"population",revision_id:"field-original",label:"Population",subquestion:"Original population question"}],retrieval_profile:{profile_id:"legacy_block_prefix_v1"},created_at:stamp};
  const view={definition,current_revision_id:definition.revision_id,freshness:"current",freshness_reasons:[],definitions:[{...definition,paper_count:3,field_count:1}],cells:f.papers.map(paper=>({paper_id:paper.id,field_id:"population",head:null,draft_version:0})),limits:{max_fields:6}};
  globalThis.fetch=async(input,options)=>{
    const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;requests.push({path,method,body});
    if(path.endsWith("/session"))return response({csrf_token:"software-only"});
    if(method==="POST"){
      assert.match(path,/\/boards(?:\/existing\/revisions)?$/);
      if(saveGate)await saveGate.promise;
      if(failedSave)return response({error:{code:"test_save_failed",message:"SOFTWARE TEST definition save failed"}},503);
      return response({definition:{board_id:revision?"existing":"created",revision_id:"saved-revision"}});
    }
    assert.equal(method,"GET","Definition guard must never invent a durable draft write");
    if(path.endsWith("/boards"))return response({boards:[],limits:f.capability.boards});
    if(path.endsWith("/boards/existing"))return response(view);
    if(path.includes("/drafts/"))return response({version:0,data:{},expected_assessment_head:null,updated_at:null});
    if(path.endsWith("/source-preparations/"+f.preparation.id+"/papers")){if(loadGate)await loadGate.promise;return response(f.preparationPapers);}
    if(path.endsWith("/source-preparations/"+f.preparation.id)){if(loadGate)await loadGate.promise;return response(f.preparation);}
    throw new Error("Unexpected request "+method+" "+path);
  };
  let renderer!:ReactTestRenderer;
  const navigate=async(next:LocationState)=>{await flushDrafts();destinations.push(next);return {status:"success" as const};};
  const render=(state=f.state)=><Compare workspace={state} requestedSetup={revision?undefined:"new"} requestedBoard={revision?"existing":undefined} navigate={navigate}/>;
  await act(async()=>{renderer=create(render());});
  if(revision)await act(async()=>button(renderer,"Revise board definition").props.onClick());
  return {f,renderer,requests,destinations,listeners,loadGate,render,navigate,allowDiscard(value:boolean){allowDiscard=value;},failSave(value:boolean){failedSave=value;},delaySave(){saveGate=gate();return saveGate;},async close(){loadGate?.release();saveGate?.release();await act(async()=>renderer.unmount());}};
}

test("definition edits block internal close, navigation and unload until explicit discard",async()=>{
  const f=await fixture("definition-guard-discard");
  try{
    await flushDrafts();assert.equal(button(f.renderer,"Create comparison board").props.disabled,false);
    await act(async()=>control(f.renderer,"Field 1 label").props.onChange({target:{value:"UNSAVED DEFINITION AUDIT"}}));
    await act(async()=>button(f.renderer,"Close new board form").props.onClick());
    assert.equal(control(f.renderer,"Field 1 label").props.value,"UNSAVED DEFINITION AUDIT");
    await assert.rejects(f.navigate({page:"settings",workspace:f.f.state.id}),/unsaved edits/);
    await assert.rejects(recoverDrafts("retry"),/unsaved edits/);assert.equal(f.destinations.length,0);
    const event=new Event("beforeunload",{cancelable:true});f.listeners.get("beforeunload")!(event);assert.equal(event.defaultPrevented,true);
    await act(async()=>button(f.renderer,"Discard definition edits…").props.onClick());
    assert.equal(control(f.renderer,"Field 1 label").props.value,"UNSAVED DEFINITION AUDIT","cancel keeps edits");
    f.allowDiscard(true);await act(async()=>button(f.renderer,"Discard definition edits…").props.onClick());
    assert.equal(control(f.renderer,"Field 1 label").props.value,"Population");await flushDrafts();
    await act(async()=>button(f.renderer,"Close new board form").props.onClick());
    assert.equal(f.renderer.root.findAllByType("form").length,0);assert.equal(f.requests.some(request=>request.method!=="GET"),false);
  }finally{await f.close();}
  assert.equal(f.listeners.has("beforeunload"),false,"unmounted guard must be removed");
});

test("definition save skips only its own guard, waits for acknowledgment, then navigates without a barrier deadlock",async()=>{
  const f=await fixture("definition-guard-save"),pending=f.delaySave();let otherFlushes=0;
  const remove=registerDraftFlusher(async()=>{otherFlushes++;});
  try{
    await act(async()=>control(f.renderer,"Field 1 label").props.onChange({target:{value:"Reviewed population"}}));
    let submitting!:Promise<void>;act(()=>{submitting=f.renderer.root.findByType("form").props.onSubmit({preventDefault(){}});});
    await observed(()=>f.requests.some(request=>request.method==="POST"));
    let navigationReady=false;const waiting=flushDrafts().then(()=>{navigationReady=true;});await tick();assert.equal(navigationReady,false);
    await act(async()=>{pending.release();await Promise.all([submitting,waiting]);});
    assert.ok(otherFlushes>0);assert.equal(f.requests.filter(request=>request.method==="POST").length,1);
    assert.equal(f.requests.find(request=>request.method==="POST")!.body.fields[0].label,"Reviewed population");
    assert.equal(f.destinations[0].board,"created");assert.equal(navigationReady,true);await flushDrafts();
  }finally{remove();await f.close();}
});

test("another participant's failed draft still prevents definition submission",async()=>{
  const f=await fixture("definition-guard-other-draft");const remove=registerDraftFlusher(async()=>{throw new Error("SOFTWARE TEST other draft could not be saved");});
  try{
    await act(async()=>control(f.renderer,"Field 1 retrieval subquestion").props.onChange({target:{value:"Exact revised question"}}));
    await act(async()=>f.renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));
    assert.equal(f.requests.some(request=>request.method==="POST"),false);assert.match(text(f.renderer.root),/other draft could not be saved/);
    assert.equal(control(f.renderer,"Field 1 retrieval subquestion").props.value,"Exact revised question");
  }finally{remove();await f.close();}
});

test("restore cannot discard definition edits during save preflight or before the save acknowledgment",async()=>{
  const f=await fixture("definition-guard-restore-race"),preflight=gate(),pending=f.delaySave();let otherFlushStarted=false;
  const remove=registerDraftFlusher(async()=>{otherFlushStarted=true;await preflight.promise;});
  try{
    await act(async()=>control(f.renderer,"Field 1 label").props.onChange({target:{value:"Keep through save"}}));
    let submitting!:Promise<void>;act(()=>{submitting=f.renderer.root.findByType("form").props.onSubmit({preventDefault(){}});});
    await observed(()=>otherFlushStarted);
    await assert.rejects(recoverDrafts("restore"),/definition is being saved/);
    assert.equal(control(f.renderer,"Field 1 label").props.value,"Keep through save");
    assert.equal(f.requests.some(request=>request.method==="POST"),false);
    await act(async()=>{preflight.release();});await observed(()=>f.requests.some(request=>request.method==="POST"));
    let restored=false;const restoring=recoverDrafts("restore").then(()=>{restored=true;});await tick();
    assert.equal(restored,false,"recovery waits for the acknowledged definition barrier");
    assert.equal(control(f.renderer,"Field 1 label").props.value,"Keep through save");
    await act(async()=>{pending.release();await Promise.all([submitting,restoring]);});
    assert.equal(f.requests.find(request=>request.method==="POST")!.body.fields[0].label,"Keep through save");
    assert.equal(f.destinations[0].board,"created");assert.equal(restored,true);
  }finally{preflight.release();pending.release();remove();await f.close();}
});

test("failed definition saves keep local edits guarded and retry the same request identity",async()=>{
  const f=await fixture("definition-guard-retry");f.failSave(true);
  try{
    await act(async()=>control(f.renderer,"Board research question").props.onChange({target:{value:"Revised board question"}}));
    await act(async()=>f.renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));
    await assert.rejects(flushDrafts(),/unsaved edits/);assert.equal(f.destinations.length,0);
    assert.equal(control(f.renderer,"Board research question").props.value,"Revised board question");
    f.failSave(false);await act(async()=>f.renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));
    const writes=f.requests.filter(request=>request.method==="POST");assert.equal(writes.length,2);assert.equal(writes[0].body.request_id,writes[1].body.request_id);
    assert.equal(f.destinations[0].board,"created");
  }finally{await f.close();}
});

test("preparation initialization is clean and background rereads cannot overwrite authored choices",async()=>{
  const f=await fixture("definition-guard-loading",{loading:true});
  try{
    assert.equal(disabled(control(f.renderer,"Field 1 label")),true);await flushDrafts();
    await act(async()=>{f.loadGate!.release();});await observed(()=>!disabled(control(f.renderer,"Field 1 label")));
    await flushDrafts();assert.equal(f.renderer.root.findAllByProps({className:"check board-paper-choice"}).length,3);
    await act(async()=>control(f.renderer,"Field 1 label").props.onChange({target:{value:"Kept field"}}));
    const chosen=f.renderer.root.findAllByProps({className:"check board-paper-choice"})[0].findByType("input");
    await act(async()=>chosen.props.onChange({target:{checked:false}}));
    await act(async()=>f.renderer.update(f.render({...f.f.state,source_revision:2})));
    assert.equal(control(f.renderer,"Field 1 label").props.value,"Kept field");
    assert.equal(f.renderer.root.findAllByProps({className:"check board-paper-choice"})[0].findByType("input").props.checked,false);
    await assert.rejects(flushDrafts(),/unsaved edits/);
    await act(async()=>recoverDrafts("restore"));await flushDrafts();
    assert.equal(control(f.renderer,"Field 1 label").props.value,"Population");
    assert.equal(f.requests.some(request=>request.method!=="GET"),false);
  }finally{await f.close();}
});

test("revised definitions use the same guard and retain the expected original revision on save",async()=>{
  const f=await fixture("definition-guard-revision",{revision:true});
  try{
    await flushDrafts();await act(async()=>control(f.renderer,"Field 1 label").props.onChange({target:{value:"Revised population"}}));
    await act(async()=>button(f.renderer,"Close definition form").props.onClick());
    assert.equal(control(f.renderer,"Field 1 label").props.value,"Revised population");
    await assert.rejects(flushDrafts(),/unsaved edits/);
    await act(async()=>f.renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));
    const write=f.requests.find(request=>request.method==="POST")!;assert.match(write.path,/\/existing\/revisions$/);
    assert.equal(write.body.expected_revision_id,"original-revision");assert.equal(write.body.fields[0].label,"Revised population");
    assert.equal(f.destinations[0].revision,"saved-revision");await flushDrafts();
  }finally{await f.close();}
});
