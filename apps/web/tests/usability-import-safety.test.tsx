import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Discover from "../components/discover";
import ImportPapers,{ImportInputForm} from "../components/import-papers";
import {CollectionPicker} from "../components/collection-explorer";
import {flushDrafts} from "../lib/drafts";
import type {LocationState,Navigate} from "../components/workspace-app";
import {capabilities,collection,response,row,stamp,storage,summary,workspace} from "./import-collection-fixtures";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,window:{confirm:()=>true}});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
const button=(renderer:ReactTestRenderer,label:string)=>renderer.root.findAllByType("button").find(node=>text(node)===label)!;
const field=(renderer:ReactTestRenderer,label:string)=>renderer.root.findAllByType("label").find(node=>text(node).startsWith(label))!.findAll(node=>["input","select","textarea"].includes(String(node.type)))[0];
type Call={path:string;method:string;body:any};
function server(id:string){
  const state=workspace(id),saved={...summary(1),workspace_id:id},snapshot=collection("collection-"+id),drafts=new Map<string,any>(),calls:Call[]=[];let failDraft=false;
  Object.assign(globalThis,{sessionStorage:storage()});
  globalThis.fetch=async(input,options)=>{
    const path=String(input),method=options?.method??"GET",body=typeof options?.body==="string"?JSON.parse(options.body):options?.body;calls.push({path,method,body});
    if(path.endsWith("/session"))return response({csrf_token:"software"});
    if(path.includes("/drafts/")){const scope=decodeURIComponent(path.split("/").at(-1)!),prior=drafts.get(scope)??{scope,version:0,data:{},expected_assessment_head:null,updated_at:null};if(method==="GET")return response(prior);if(failDraft)return response({error:{code:"save_failed",message:"SOFTWARE TEST intake draft save failed"}},500);assert.equal(body.version,prior.version);const next={...prior,version:prior.version+1,data:body.data,updated_at:stamp};drafts.set(scope,next);return response(next);}
    if(path.endsWith("/imports"))return response({imports:[saved]});
    if(path.includes("/rows?"))return response({import_id:saved.id,revision:1,rows:[row(1)],offset:0,total:1,next_offset:null});
    if(path.endsWith("/imports/"+saved.id))return response(saved);
    if(method==="POST"&&path.endsWith("/imports/csv"))return response(saved);
    if(path.endsWith("/collections"))return response({collections:[snapshot],max_map_papers:50,max_prepared_sources:30});
    throw new Error("Unexpected software request "+path);
  };
  return {state,saved,snapshot,drafts,calls,setFailDraft:(value:boolean)=>{failDraft=value;}};
}
async function discover(id:string){
  const fixture=server(id);let intake:LocationState["intake"]="import",renderer!:ReactTestRenderer;
  const navigate:Navigate=async next=>{try{await flushDrafts();}catch(error){return {status:"blocked",message:(error as Error).message};}intake=next.intake;renderer.update(view());return {status:"success"};};
  const view=()=> <Discover workspace={fixture.state} capabilities={capabilities} requestedIntake={intake} refresh={async()=>{}} navigate={navigate}/>;
  await act(async()=>{renderer=create(view());});
  return {...fixture,renderer,view};
}

test("typed identifier intake survives pane switches and reopen without uploading or parsing",async()=>{
  const h=await discover("safe-typed-input");let renderer=h.renderer;
  try{
    await act(async()=>field(renderer,"Import format").props.onChange({target:{value:"identifiers"}}));const exact="PMID: 12345678\n10.1234/日本";
    await act(async()=>field(renderer,"Identifiers · one per line").props.onChange({target:{value:exact}}));await act(async()=>button(renderer,"Browse collections").props.onClick());
    assert.deepEqual(h.drafts.get("import-intake").data,{format:"identifiers",identifiers:exact});assert.equal(h.calls.some(call=>call.method==="POST"),false);
    await act(async()=>button(renderer,"Import papers").props.onClick());assert.equal(field(renderer,"Identifiers · one per line").props.value,exact);
    await act(async()=>renderer.unmount());await act(async()=>{renderer=create(h.view());});assert.equal(field(renderer,"Identifiers · one per line").props.value,exact);assert.equal(h.calls.some(call=>/resolve|query-suggestions|source-preparations/.test(call.path)),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("failed identifier draft save blocks the initiating switch and retains text until Retry",async()=>{
  const h=await discover("safe-input-save-failure"),renderer=h.renderer;
  try{
    await act(async()=>field(renderer,"Import format").props.onChange({target:{value:"identifiers"}}));await act(async()=>field(renderer,"Identifiers · one per line").props.onChange({target:{value:"UNFINISHED IDENTIFIER"}}));h.setFailDraft(true);
    await act(async()=>button(renderer,"Browse collections").props.onClick());assert.match(text(renderer.root.findByProps({"aria-label":"Add papers"})),/intake draft save failed/);assert.equal(field(renderer,"Identifiers · one per line").props.value,"UNFINISHED IDENTIFIER");assert.equal(h.calls.some(call=>call.path.endsWith("/collections")),false);
    h.setFailDraft(false);await act(async()=>button(renderer,"Retry").props.onClick());assert.equal(h.drafts.get("import-intake").data.identifiers,"UNFINISHED IDENTIFIER");assert.ok(h.calls.some(call=>call.path.endsWith("/collections")));assert.equal(h.calls.some(call=>call.method==="POST"),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("an unparsed file blocks leaving without reading bytes and only a confirmed reset clears it",async()=>{
  const h=await discover("safe-file-choice"),renderer=h.renderer;let reads=0,confirmed=false;
  Object.assign(globalThis,{window:{confirm:()=>confirmed}});
  try{
    await act(async()=>renderer.root.findByProps({type:"file"}).props.onChange({target:{files:[{name:"LOCAL.csv",size:10,arrayBuffer:async()=>{reads++;return new ArrayBuffer(10);}}]}}));await act(async()=>button(renderer,"Browse collections").props.onClick());
    assert.equal(reads,0);assert.equal(h.calls.some(call=>call.method==="POST"),false);assert.match(text(renderer.root),/File bytes are never stored in an editable draft/);
    await act(async()=>button(renderer,"Discard unfinished intake changes…").props.onClick());await act(async()=>assert.rejects(flushDrafts(),/selected citation file/));
    confirmed=true;await act(async()=>button(renderer,"Discard changes & restore saved drafts…").props.onClick());assert.ok(h.calls.some(call=>call.path.endsWith("/collections")));assert.equal(reads,0);
    for(const call of h.calls.filter(call=>call.method==="PUT"))assert.deepEqual(Object.keys(call.body.data).sort(),["format","identifiers"]);
  }finally{await act(async()=>renderer.unmount());Object.assign(globalThis,{window:{confirm:()=>true}});}
});

test("a successful explicit file parse retains its saved preview and permits navigation",async()=>{
  const h=await discover("safe-parsed-file"),renderer=h.renderer;const bytes=new TextEncoder().encode("Title\nSOFTWARE TEST\n");
  try{await act(async()=>renderer.root.findByProps({type:"file"}).props.onChange({target:{files:[{name:"LOCAL.csv",size:bytes.length,arrayBuffer:async()=>bytes.buffer}]}}));await act(async()=>renderer.root.findByProps({"aria-label":"Citation import input"}).props.onSubmit({preventDefault(){}}));assert.equal(renderer.root.findAllByProps({"aria-label":"Import row 1"}).length,1);await act(async()=>button(renderer,"Browse collections").props.onClick());assert.ok(h.calls.some(call=>call.path.endsWith("/collections")));assert.equal(h.calls.filter(call=>call.method==="POST").length,1);}
  finally{await act(async()=>renderer.unmount());}
});

test("manual row and review edits block unmount until saved or explicitly reset",async()=>{
  const h=server("safe-row-review");let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<ImportPapers workspaceId={h.state.id} maxBytes={1024} maxRows={500} maxResolutionRows={3} onCommitted={async()=>{}}/>);});
  try{
    await act(async()=>field(renderer,"Saved import preview").props.onChange({target:{value:h.saved.id}}));await act(async()=>button(renderer,"Edit metadata for row 1").props.onClick());const editor=()=>renderer.root.findByProps({"aria-label":"Edit metadata row 1"});await act(async()=>editor().findAllByType("input")[0].props.onChange({target:{value:"UNSAVED ROW TITLE"}}));await act(async()=>assert.rejects(flushDrafts(),/manual metadata row/));assert.equal(editor().findAllByType("input")[0].props.value,"UNSAVED ROW TITLE");
    await act(async()=>button(renderer,"Discard unfinished intake changes…").props.onClick());await act(async()=>flushDrafts());await act(async()=>button(renderer,"Close metadata editor").props.onClick());
    await act(async()=>field(renderer,"Accept row 1").props.onChange());await act(async()=>field(renderer,"Collection name").props.onChange({target:{value:"UNCOMMITTED NAME"}}));await act(async()=>assert.rejects(flushDrafts(),/unfinished row acceptance/));assert.equal(field(renderer,"Accept row 1").props.checked,true);assert.equal(field(renderer,"Collection name").props.value,"UNCOMMITTED NAME");
    await act(async()=>button(renderer,"Discard unfinished intake changes…").props.onClick());await act(async()=>flushDrafts());assert.equal(field(renderer,"Accept row 1").props.checked,false);assert.equal(field(renderer,"Collection name").props.value,"software");assert.equal(h.calls.some(call=>call.method==="POST"),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("uncommitted collection combinations retain their chosen inputs until confirmed reset",async()=>{
  const h=server("safe-combination");let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<CollectionPicker workspaceId={h.state.id} onChoose={async()=>{}}/>);});
  try{await act(async()=>field(renderer,"Include this snapshot").props.onChange());await act(async()=>field(renderer,"Combined collection name").props.onChange({target:{value:"UNCOMMITTED COMBINATION"}}));await act(async()=>assert.rejects(flushDrafts(),/unfinished local review/));assert.equal(field(renderer,"Include this snapshot").props.checked,true);assert.equal(field(renderer,"Combined collection name").props.value,"UNCOMMITTED COMBINATION");await act(async()=>button(renderer,"Discard unfinished intake changes…").props.onClick());await act(async()=>flushDrafts());assert.equal(field(renderer,"Include this snapshot").props.checked,false);assert.equal(field(renderer,"Combined collection name").props.value,"Combined papers");assert.equal(h.calls.some(call=>call.method==="POST"),false);}
  finally{await act(async()=>renderer.unmount());}
});

test("acknowledged import and combination commits can flush navigation without blocking on their own saved review",async()=>{
  const h=server("safe-acknowledged-commit"),originalFetch=globalThis.fetch;let choices=0;
  globalThis.fetch=async(input,options)=>{const path=String(input);if(path.endsWith("/commit")||path.endsWith("/combine"))return response(h.snapshot);if(path.endsWith("/combine-preview"))return response({input_sha256:"a".repeat(64),member_count:1,members:[],duplicate_groups:[]});return originalFetch(input,options);};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<ImportPapers workspaceId={h.state.id} maxBytes={1024} maxRows={500} maxResolutionRows={3} onCommitted={async()=>{await flushDrafts();choices++;}}/>);});
  try{await act(async()=>field(renderer,"Saved import preview").props.onChange({target:{value:h.saved.id}}));await act(async()=>field(renderer,"Accept row 1").props.onChange());await act(async()=>button(renderer,"Commit 1 accepted records").props.onClick());assert.equal(choices,1);}
  finally{await act(async()=>renderer.unmount());}
  await act(async()=>{renderer=create(<CollectionPicker workspaceId={h.state.id} onChoose={async()=>{await flushDrafts();choices++;}}/>);});
  try{await act(async()=>field(renderer,"Include this snapshot").props.onChange());await act(async()=>button(renderer,"Preview combination").props.onClick());await act(async()=>button(renderer,"Commit reviewed combination").props.onClick());assert.equal(choices,2);}
  finally{await act(async()=>renderer.unmount());}
});

test("native leave confirmation protects an unparsed file without reading bytes or starting an async save",async()=>{
  const listeners=new Map<string,(event:any)=>void>();let reads=0,requests=0,confirmations=0;
  Object.assign(globalThis,{window:{confirm:()=>{confirmations++;return true;},addEventListener:(name:string,handler:(event:any)=>void)=>listeners.set(name,handler),removeEventListener:(name:string)=>listeners.delete(name)}});
  globalThis.fetch=async()=>{requests++;throw new Error("An unload guard must never save or upload");};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<ImportInputForm maxBytes={1024} busy={false} onParse={async()=>{throw new Error("No implicit parse");}}/>);});
  try{
    assert.equal(listeners.has("beforeunload"),false);await act(async()=>renderer.root.findByProps({type:"file"}).props.onChange({target:{files:[{name:"LOCAL.csv",size:10,arrayBuffer:async()=>{reads++;return new ArrayBuffer(10);}}]}}));
    const event={prevented:false,returnValue:undefined as unknown,preventDefault(){this.prevented=true;}};listeners.get("beforeunload")!(event);assert.equal(event.prevented,true);assert.equal(event.returnValue,"");assert.equal(reads,0);assert.equal(requests,0);assert.equal(confirmations,0,"native beforeunload requests browser confirmation without custom synchronous prompts");
    // Declining the native leave keeps the mounted input and its navigation guard.
    await act(async()=>assert.rejects(flushDrafts(),/selected citation file/));await act(async()=>button(renderer,"Discard unfinished intake changes…").props.onClick());assert.equal(listeners.has("beforeunload"),false);assert.equal(reads,0);assert.equal(requests,0);
  }finally{await act(async()=>renderer.unmount());Object.assign(globalThis,{window:{confirm:()=>true}});}
});
