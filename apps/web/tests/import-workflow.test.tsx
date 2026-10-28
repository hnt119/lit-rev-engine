import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import ImportPapers from "../components/import-papers";
import {collection,metadata,response,row,storage,summary} from "./import-collection-fixtures";
import type {Schema} from "../lib/api";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,sessionStorage:storage()});
const text=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(text).join("");
const button=(renderer:ReactTestRenderer,label:string)=>renderer.root.findAllByType("button").find(item=>text(item)===label)!;
const label=(renderer:ReactTestRenderer,start:string)=>renderer.root.findAllByType("label").find(item=>text(item).startsWith(start))!;
type Call={path:string;method:string;body:any;options:RequestInit|undefined};
async function render(s:Schema<"ImportSummary">,rows:Schema<"ReviewedImportRow">[],mutation?:(call:Call)=>Promise<Response>|Response){
  const calls:Call[]=[],chosen:Schema<"CollectionSummary">[]=[];let current=s,currentRows=rows;
  Object.assign(globalThis,{sessionStorage:storage()});
  globalThis.fetch=async(input,options)=>{
    const path=String(input),method=options?.method??"GET",body=typeof options?.body==="string"?JSON.parse(options.body):options?.body;
    const call={path,method,body,options};calls.push(call);
    if(path.endsWith("/session"))return response({csrf_token:"software-test"});
    if(path.includes("/drafts/"))return response({scope:decodeURIComponent(path.split("/").at(-1)!),version:0,data:{},expected_assessment_head:null,updated_at:null});
    if(method!=="GET"){if(mutation)return mutation(call);throw new Error("Unexpected software-test mutation "+path);}
    if(path.endsWith("/imports"))return response({imports:[current]});
    if(path.includes("/rows?")){const url=new URL(path,"http://software.test"),offset=Number(url.searchParams.get("offset")),limit=Number(url.searchParams.get("limit"));return response({import_id:current.id,revision:current.revision,rows:currentRows.slice(offset,offset+limit),offset,total:currentRows.length,next_offset:offset+limit<currentRows.length?offset+limit:null});}
    if(path.endsWith("/"+current.id))return response(current);
    throw new Error("Unexpected software-test GET "+path);
  };
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<ImportPapers workspaceId={s.workspace_id} maxBytes={1024} maxRows={500} maxResolutionRows={3} onCommitted={async value=>{chosen.push(value);}}/>);});
  async function open(){await act(async()=>label(renderer,"Saved import preview").findByType("select").props.onChange({target:{value:s.id}}));}
  return {renderer,calls,chosen,open,update:(next:Schema<"ImportSummary">,values=currentRows)=>{current=next;currentRows=values;}};
}

test("saved CSV preview reopens through GET; column changes stay local until a revision-checked mapping action",async()=>{
  const s=summary(),rows=[row(1),row(2)];let harness!:Awaited<ReturnType<typeof render>>;
  harness=await render(s,rows,call=>{assert.match(call.path,/\/mapping$/);assert.equal(call.body.expected_revision,1);assert.equal(call.body.mapping.title,"");assert.equal(call.body.mapping.source_key,"Key");const next={...s,revision:2,mapping:call.body.mapping,pending_count:2,ready_count:0};harness.update(next,rows.map(item=>({...item,status:"pending",metadata:{...item.metadata,title:""}})));return response(next);});
  const {renderer,calls}=harness;
  try{
    await harness.open();assert.equal(renderer.root.findAllByProps({"aria-label":"Import row 1"}).length,1);
    const mapping=label(renderer,"title").findByType("select");assert.equal(mapping.findAllByType("option").some(option=>option.props.value==="Notes"),false);
    await act(async()=>mapping.props.onChange({target:{value:""}}));assert.equal(calls.filter(call=>call.method!=="GET").length,0);
    await act(async()=>button(renderer,"Apply column mapping").props.onClick());
    assert.match(JSON.stringify(renderer.toJSON()),/new revision/);assert.match(JSON.stringify(renderer.toJSON()),/Title not supplied/);
    assert.equal(calls.filter(call=>call.method==="POST").length,1);
    assert.equal(button(renderer,"Commit 0 accepted records").props.disabled,true);
  }finally{await act(async()=>renderer.unmount());}
});

test("exact duplicates require a deliberate policy; commit uses reviewed row IDs and opens the immutable snapshot",async()=>{
  const s={...summary(),duplicate_groups:[{id:"software-exact",kind:"exact_identifier_duplicate" as const,row_ids:["software-row:1","software-row:2"],message:"Software-test exact identifiers overlap."}]};
  const harness=await render(s,[row(1),{...row(2),duplicate_of:"software-row:1"}],call=>{assert.match(call.path,/\/commit$/);assert.deepEqual(call.body.accepted_row_ids,["software-row:1","software-row:2"]);assert.equal(call.body.duplicate_policy,"keep_separate");assert.equal(call.body.expected_revision,1);return response(collection());});
  const {renderer,calls,chosen}=harness;
  try{
    await harness.open();await act(async()=>button(renderer,"Accept all import-ready records").props.onClick());
    assert.equal(button(renderer,"Commit 2 accepted records").props.disabled,true);
    await act(async()=>label(renderer,"Exact-identifier duplicate policy").findByType("select").props.onChange({target:{value:"keep_separate"}}));
    assert.equal(calls.filter(call=>call.method!=="GET").length,0);
    await act(async()=>button(renderer,"Commit 2 accepted records").props.onClick());assert.equal(chosen[0].id,"software-snapshot");assert.equal(chosen[0].collection_id,"software-family");
    assert.equal(calls.some(call=>/resolve|searches|source-preparations/.test(call.path)),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("cross-row conflicts permit explicit keep-separate review while within-row identifier conflicts remain blocked",async()=>{
  const conflict={...row(2),status:"conflict" as const,diagnostics:[{code:"cross_row_identity_conflict",message:"Synthetic cross-row contradiction",severity:"error" as const,row_number:2,field:null}]};
  const invalid={...row(3),status:"conflict" as const,diagnostics:[{code:"identifier_conflict",message:"Synthetic within-row contradiction",severity:"error" as const,row_number:3,field:"doi"}]};
  const s={...summary(3),duplicate_groups:[{id:"software-conflict",kind:"identifier_conflict" as const,row_ids:[row(1).id,row(2).id],message:"Software-test conflicting IDs."}]};
  const {renderer,open}=await render(s,[row(1),conflict,invalid]);
  try{
    await open();assert.equal(label(renderer,"Accept row 2").findByType("input").props.disabled,false);assert.equal(label(renderer,"Accept row 3").findByType("input").props.disabled,true);
    await act(async()=>{label(renderer,"Accept row 1").findByType("input").props.onChange();label(renderer,"Accept row 2").findByType("input").props.onChange();});assert.equal(button(renderer,"Commit 2 accepted records").props.disabled,true);
    await act(async()=>label(renderer,"Keep these conflicting").findByType("input").props.onChange({target:{checked:true}}));assert.equal(button(renderer,"Commit 2 accepted records").props.disabled,false);
  }finally{await act(async()=>renderer.unmount());}
});

test("identifier resolution is explicit, bounded to three rows and invalidates acceptance after a new preview revision",async()=>{
  const rows=Array.from({length:5},(_,index)=>({...row(index+1),status:"pending" as const,metadata:{...metadata(index+1),title:"",abstract:""}}));const s={...summary(5),ready_count:0,pending_count:5};let harness!:Awaited<ReturnType<typeof render>>;
  harness=await render(s,rows,call=>{assert.match(call.path,/\/resolve$/);assert.deepEqual(call.body.row_ids,rows.slice(0,3).map(item=>item.id));const next={...s,revision:2};harness.update(next);return response(next);});
  const {renderer,calls}=harness;
  try{
    await harness.open();assert.equal(calls.filter(call=>call.method!=="GET").length,0);
    const checks=renderer.root.findAllByType("label").filter(item=>text(item).startsWith("Select row ")).map(item=>item.findByType("input").props.onChange);
    await act(async()=>{for(const change of checks)change();});
    assert.equal(renderer.root.findAllByType("label").filter(item=>text(item).startsWith("Select row ")&&item.findByType("input").props.checked).length,3);assert.equal(calls.filter(call=>call.method!=="GET").length,0);
    await act(async()=>button(renderer,"Resolve selected identifiers (3/3)").props.onClick());assert.equal(calls.filter(call=>call.method==="POST").length,1);assert.equal(button(renderer,"Commit 0 accepted records").props.disabled,true);
  }finally{await act(async()=>renderer.unmount());}
});

test("manual metadata edits survive a revision conflict and identical retry reuses its request ID",async()=>{
  const s=summary(1),rows=[row(1)];let posts=0,harness!:Awaited<ReturnType<typeof render>>;const ids:string[]=[];
  harness=await render(s,rows,call=>{assert.match(call.path,/\/edit-row$/);ids.push(call.body.request_id);assert.equal(call.body.metadata.title,"SOFTWARE TEST MANUAL CORRECTION");assert.equal(call.body.expected_revision,1);if(posts++===0)return response({detail:{code:"import_conflict",message:"Synthetic revision conflict; edits retained."}},409);const next={...s,revision:2};harness.update(next,[{...rows[0],metadata:call.body.metadata}]);return response(next);});
  const {renderer,calls}=harness;
  try{
    await harness.open();await act(async()=>button(renderer,"Edit metadata for row 1").props.onClick());
    const editor=()=>renderer.root.findByProps({"aria-label":"Edit metadata row 1"});await act(async()=>editor().findAllByType("input")[0].props.onChange({target:{value:"SOFTWARE TEST MANUAL CORRECTION"}}));
    assert.equal(calls.filter(call=>call.method!=="GET").length,0);
    await act(async()=>editor().props.onSubmit({preventDefault(){}}));assert.equal(editor().findAllByType("input")[0].props.value,"SOFTWARE TEST MANUAL CORRECTION");assert.match(JSON.stringify(renderer.toJSON()),/Synthetic revision conflict/);
    await act(async()=>editor().props.onSubmit({preventDefault(){}}));assert.equal(ids.length,2);assert.equal(ids[0],ids[1]);assert.equal(renderer.root.findAllByProps({"aria-label":"Edit metadata row 1"}).length,0);
    assert.equal(calls.some(call=>call.path.endsWith("/resolve")),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("an ambiguous raw parse upload retains exact bytes, filename and request identity on explicit retry",async()=>{
  const s=summary(),bytes=new TextEncoder().encode("\ufeffTitle,DOI\nSOFTWARE TEST,10.1234/software\n"),keys:string[]=[];let uploads=0;
  const {renderer,calls}=await render(s,[row(1),row(2)],call=>{
    assert.match(call.path,/\/imports\/csv$/);assert.deepEqual(new Uint8Array(call.options?.body as ArrayBuffer),bytes);
    const headers=call.options?.headers as Record<string,string>;keys.push(headers["X-Request-ID"]);assert.equal(headers["X-Import-Filename"],encodeURIComponent("software 微生物.csv"));
    if(uploads++===0)throw new Error("Synthetic ambiguous upload response");return response(s);
  });
  try{
    const input=renderer.root.findByProps({type:"file"});await act(async()=>input.props.onChange({target:{files:[{name:"software 微生物.csv",size:bytes.byteLength,arrayBuffer:async()=>bytes.buffer}]}}));
    const form=()=>renderer.root.findByProps({"aria-label":"Citation import input"});assert.equal(calls.filter(call=>call.method!=="GET").length,0);
    await act(async()=>form().props.onSubmit({preventDefault(){}}));assert.match(text(renderer.root),/Synthetic ambiguous upload response/);
    await act(async()=>form().props.onSubmit({preventDefault(){}}));assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);assert.equal(renderer.root.findAllByProps({"aria-label":"Import row 1"}).length,1);
    assert.equal(calls.some(call=>/resolve|searches|source-preparations|proposals/.test(call.path)),false);
  }finally{await act(async()=>renderer.unmount());}
});
