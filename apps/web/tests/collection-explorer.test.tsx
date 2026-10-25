import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import CollectionExplorer,{CollectionPicker} from "../components/collection-explorer";
import {capabilities as capability,collection,detail,paper,response,storage,workspace} from "./import-collection-fixtures";
import type {Schema} from "../lib/api";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(text).join("");
const button=(renderer:ReactTestRenderer,name:string)=>renderer.root.findAllByType("button").find(item=>text(item)===name)!;
const inputs=(renderer:ReactTestRenderer)=>renderer.root.findAllByType("input").filter(item=>item.props.type==="checkbox");
type Call={path:string;method:string;body:any};

async function explorer(workspaceId:string,count=75,extra?:(call:Call)=>Promise<Response>|Response|undefined){
  const snapshot=collection("software-collection-"+workspaceId,count),calls:Call[]=[],papers=Array.from({length:count},(_,index)=>paper(index+1));
  globalThis.fetch=async(input,options)=>{
    const path=String(input),method=options?.method??"GET",body=typeof options?.body==="string"?JSON.parse(options.body):undefined;const call={path,method,body};calls.push(call);
    if(path.endsWith("/session"))return response({csrf_token:"software-test"});
    const value=extra?.(call);if(value)return value;
    assert.equal(method,"GET","opening, filtering or inspecting collections must not prepare, generate or resolve");
    if(path.includes("/drafts/"))return response({scope:"collection-selection:"+snapshot.id,version:0,data:{},expected_assessment_head:null,updated_at:null});
    if(path.endsWith("/collections/"+snapshot.id))return response(snapshot);
    if(path.includes("/collection-maps?"))return response({maps:[],jobs:[]});
    if(path.includes("/papers?")){const url=new URL(path,"http://software.test"),offset=Number(url.searchParams.get("offset")),limit=Number(url.searchParams.get("limit")),filter=url.searchParams.get("filter")??"",visible=papers.filter(item=>(item.title+" "+item.abstract).includes(filter));return response({collection_id:snapshot.id,origin:snapshot.origin,papers:visible.slice(offset,offset+limit),offset,total:visible.length,next_offset:offset+limit<visible.length?offset+limit:null});}
    if(path.includes("/paper?")){const id=new URL(path,"http://software.test").searchParams.get("paper_id")!,number=Number(id.split(":").at(-1));return response(detail(snapshot,number));}
    throw new Error("Unexpected software-test path "+path);
  };
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<CollectionExplorer workspace={workspace(workspaceId)} collectionId={snapshot.id} capabilities={capability} refresh={async()=>{}} navigate={async()=>{}}/>);});
  return {renderer,calls,snapshot,papers};
}

test("collection reopen preserves imported origins and unknown search metadata; filtering and inspection use authorized GETs only",async()=>{
  const {renderer,calls}=await explorer("software-collection-inspection",3);
  try{
    const json=JSON.stringify(renderer.toJSON());assert.match(json,/Not recorded for this citation collection/);assert.match(json,/Unknown/);assert.equal(calls.some(call=>call.path.includes("/searches")),false);
    const before=calls.length;await act(async()=>renderer.root.findByProps({type:"search"}).props.onChange({target:{value:"CITATION 2"}}));assert.equal(calls.length,before,"typing never submits a filter or provider request");
    await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));assert.equal(renderer.root.findAllByProps({"data-paper-id":"software-paper:2"}).length,1);assert.equal(renderer.root.findAllByProps({"data-paper-id":"software-paper:1"}).length,0);
    await act(async()=>button(renderer,"Inspect paper").props.onClick());assert.match(JSON.stringify(renderer.toJSON()),/imported_abstract/);assert.match(JSON.stringify(renderer.toJSON()),/SOFTWARE-KEY-2/);
    assert.equal(renderer.root.findByProps({"aria-label":"Previous paper"}).props.disabled,true);assert.equal(renderer.root.findByProps({"aria-label":"Next paper"}).props.disabled,true);
    assert.equal(calls.every(call=>call.method==="GET"),true);
  }finally{await act(async()=>renderer.unmount());}
});

test("paged collection selection retains thirty IDs across pages, rejects the thirty-first, and inspector navigation follows displayed order",async()=>{
  const {renderer,calls}=await explorer("software-collection-selection");
  try{
    const first=inputs(renderer).map(item=>item.props.onChange);assert.equal(first.length,50);
    await act(async()=>{for(const change of first.slice(0,25))change();});await act(async()=>button(renderer,"Next collection page").props.onClick());
    const second=inputs(renderer).map(item=>item.props.onChange);assert.equal(second.length,25);await act(async()=>{for(const change of second)change();});
    assert.equal(inputs(renderer).filter(item=>item.props.checked).length,5);assert.equal(inputs(renderer)[5].props.disabled,true);assert.match(text(renderer.root),/30 selected/);
    await act(async()=>button(renderer,"Inspect paper").props.onClick());
    const handlers=renderer.root.findByProps({"aria-label":"Next paper"}).props.onClick;
    await act(async()=>{handlers();handlers();});const inspector=renderer.root.findByProps({"aria-label":"Collection paper inspector"});assert.match(text(inspector),/SOFTWARE TEST CITATION 53/);
    assert.equal(inputs(renderer).filter(item=>item.props.checked).length,6,"five list choices plus the selected inspector value");
    await act(async()=>second[0]());assert.match(text(renderer.root),/29 selected/);assert.equal(inputs(renderer)[5].props.disabled,false);
    await act(async()=>button(renderer,"Previous collection page").props.onClick());assert.equal(inputs(renderer).filter(item=>item.props.checked).length,26,"twenty-five saved page-one choices plus the retained inspector value");assert.match(text(renderer.root.findByProps({"aria-label":"Collection paper inspector"})),/outside the displayed page/i);assert.equal(renderer.root.findByProps({"aria-label":"Next paper"}).props.disabled,true);
    assert.equal(calls.some(call=>/searches|maps|source-preparations|proposals|resolve/.test(call.path)),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("late filtered pages and late paper provenance cannot replace the current collection view",async()=>{
  let latePage:((value:Response)=>void)|undefined,lateDetail:((value:Response)=>void)|undefined;
  const {renderer,snapshot}=await explorer("software-collection-stale",3,call=>{
    if(call.path.includes("filter=late"))return new Promise<Response>(resolve=>{latePage=resolve;});
    if(call.path.includes("paper_id=software-paper%3A1"))return new Promise<Response>(resolve=>{lateDetail=resolve;});
  });
  try{
    await act(async()=>renderer.root.findAllByType("button").find(item=>text(item)==="Inspect paper")!.props.onClick());
    await act(async()=>renderer.root.findAllByType("button").filter(item=>text(item)==="Inspect paper")[1].props.onClick());
    assert.match(text(renderer.root.findByProps({"aria-label":"Collection paper inspector"})),/SOFTWARE-KEY-2/);
    await act(async()=>{lateDetail!(response(detail(snapshot,1)));});assert.match(text(renderer.root.findByProps({"aria-label":"Collection paper inspector"})),/SOFTWARE-KEY-2/);
    await act(async()=>renderer.root.findByProps({type:"search"}).props.onChange({target:{value:"late"}}));await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));
    await act(async()=>button(renderer,"Clear collection filter").props.onClick());assert.equal(renderer.root.findAllByProps({"data-paper-id":"software-paper:3"}).length,1);
    await act(async()=>{latePage!(response({collection_id:snapshot.id,origin:snapshot.origin,papers:[],offset:0,total:0,next_offset:null}));});assert.equal(renderer.root.findAllByProps({"data-paper-id":"software-paper:3"}).length,1);
  }finally{await act(async()=>renderer.unmount());}
});

test("combination is explicitly previewed and conflicts reviewed before committing exact immutable input bindings",async()=>{
  Object.assign(globalThis,{sessionStorage:storage()});const first=collection("software-first"),second={...collection("software-second"),name:"SOFTWARE TEST SECOND"},calls:Call[]=[],chosen:Schema<"CollectionSummary">[]=[];
  const preview:Schema<"CombineCollectionsPreview">={input_sha256:"d".repeat(64),member_count:2,sources:[first.origin,second.origin],duplicate_groups:[{id:"software-group",kind:"identifier_conflict",row_ids:["occurrence:first","occurrence:second"],message:"Synthetic conflicting identifiers require a decision."}],members:[{id:"occurrence:first",paper_id:paper(1).id,title:paper(1).title,doi:paper(1).doi,pmid:null,pmcid:null,collection_id:first.id},{id:"occurrence:second",paper_id:paper(2).id,title:paper(2).title,doi:paper(2).doi,pmid:null,pmcid:null,collection_id:second.id}]};
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=typeof options?.body==="string"?JSON.parse(options.body):undefined;calls.push({path,method,body});if(path.endsWith("/session"))return response({csrf_token:"software-test"});if(method==="GET"&&path.endsWith("/collections"))return response({collections:[first,second],max_map_papers:50,max_prepared_sources:30});if(path.endsWith("/combine-preview")){assert.deepEqual(body.sources.map((source:any)=>source.origin),[first.origin,second.origin]);return response(preview);}if(path.endsWith("/combine")){assert.equal(body.preview_sha256,preview.input_sha256);assert.deepEqual(body.conflict_decisions,{"software-group":"keep_separate"});return response({...collection("software-combined"),kind:"combined",coverage:"explicit_combination"});}throw new Error("Unexpected software-test path "+path);};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<CollectionPicker workspaceId="software-combine" onChoose={async value=>{chosen.push(value);}}/>);});
  try{
    await act(async()=>{for(const input of inputs(renderer))input.props.onChange();});assert.equal(calls.filter(call=>call.method!=="GET").length,0);assert.equal(renderer.root.findAllByType("button").some(item=>text(item)==="Commit reviewed combination"),false);
    await act(async()=>button(renderer,"Preview combination").props.onClick());assert.equal(button(renderer,"Commit reviewed combination").props.disabled,true);
    const conflict=renderer.root.findAllByType("label").find(item=>text(item).startsWith("Keep these conflicting"))!.findByType("input");await act(async()=>conflict.props.onChange({target:{checked:true}}));assert.equal(calls.filter(call=>call.method==="POST").length,1);
    await act(async()=>button(renderer,"Commit reviewed combination").props.onClick());assert.equal(chosen[0].id,"software-combined");
    assert.equal(calls.some(call=>/searches|resolve|source-preparations|proposals/.test(call.path)),false);
  }finally{await act(async()=>renderer.unmount());}
});
