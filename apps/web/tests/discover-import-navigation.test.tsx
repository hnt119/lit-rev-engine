import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Discover from "../components/discover";
import {flushDrafts} from "../lib/drafts";
import {capabilities as capability,collection,paper,response,stamp} from "./import-collection-fixtures";
import type {Schema} from "../lib/api";
import type {LocationState} from "../components/workspace-app";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(text).join("");
const button=(renderer:ReactTestRenderer,name:string)=>renderer.root.findAllByType("button").find(item=>text(item)===name)!;
const workspace=(id:string)=>({id,question:"SOFTWARE TEST",mode:"saved_example",created_at:stamp,source_revision:0,current_preparation_id:null,selected_paper_ids:[],current_run_id:null,current_assessment_ids:{},searches:[],preparations:[],runs:[],assessments:[]}) as Schema<"WorkspaceSummary">;

test("legacy Discover makes no import or collection reads until explicitly opened, and saves drafts before changing panes",async()=>{
  const calls:{path:string;method:string;body:any}[]=[],destinations:LocationState[]=[],saved=collection("software-import-snapshot");
  globalThis.fetch=async(input,options)=>{
    const path=String(input),method=options?.method??"GET",body=typeof options?.body==="string"?JSON.parse(options.body):undefined;calls.push({path,method,body});
    if(path.endsWith("/session"))return response({csrf_token:"software-test"});
    if(path.includes("/drafts/"))return response({scope:"discover",version:method==="PUT"?1:0,data:body?.data??{},expected_assessment_head:null,updated_at:method==="PUT"?stamp:null});
    if(path.endsWith("/imports"))return response({imports:[]});
    if(path.endsWith("/collections"))return response({collections:[saved],max_map_papers:50,max_prepared_sources:30});
    throw new Error("Unexpected software-test request "+path);
  };
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<Discover workspace={workspace("software-import-discover")} capabilities={capability} refresh={async()=>{}} navigate={async value=>{await flushDrafts();destinations.push(value);return {status:"success"};}}/>);});
  try{
    assert.equal(calls.some(call=>/imports|collections/.test(call.path)),false);
    const research=renderer.root.findAllByType("textarea")[0];await act(async()=>research.props.onChange({target:{value:"SOFTWARE TEST CHANGED QUESTION"}}));
    await act(async()=>button(renderer,"Import papers").props.onClick());
    const draftSave=calls.findIndex(call=>call.method==="PUT"),importRead=calls.findIndex(call=>call.path.endsWith("/imports"));assert.ok(draftSave>=0&&importRead>draftSave);assert.equal(calls[draftSave].body.data.question,"SOFTWARE TEST CHANGED QUESTION");assert.equal(calls.filter(call=>call.method==="POST").length,0);
    await act(async()=>button(renderer,"Browse collections").props.onClick());await act(async()=>button(renderer,saved.name).props.onClick());
    assert.deepEqual(destinations,[{page:"discover",workspace:"software-import-discover",intake:"import"},{page:"discover",workspace:"software-import-discover",intake:"collections"},{page:"discover",workspace:"software-import-discover",collection:saved.id}]);
  }finally{await act(async()=>renderer.unmount());}
});

test("saved-search collections navigate to the genuine saved search, and a collection URL suppresses legacy search loading",async()=>{
  const destinations:LocationState[]=[],snapshot=collection("software-reopen-snapshot"),search={...collection("software-real-search"),kind:"saved_search" as const,name:"SOFTWARE TEST SEARCH",origin:{kind:"search" as const,search_id:"software-real-search",search_snapshot_sha256:"a".repeat(64)}};
  const calls:string[]=[];
  globalThis.fetch=async(input,options)=>{
    const path=String(input);calls.push(path);assert.equal(options?.method??"GET","GET");if(path.endsWith("/session"))return response({csrf_token:"software-test"});
    if(path.includes("/drafts/"))return response({scope:"software",version:0,data:{},expected_assessment_head:null,updated_at:null});
    if(path.endsWith("/collections"))return response({collections:[search],max_map_papers:50,max_prepared_sources:30});
    if(path.endsWith("/collections/"+snapshot.id))return response(snapshot);
    if(path.includes("/collection-maps?"))return response({maps:[],jobs:[]});
    if(path.includes("/papers?"))return response({collection_id:snapshot.id,origin:snapshot.origin,papers:[paper()],offset:0,total:1,next_offset:null});
    throw new Error("A collection URL must not request a legacy search: "+path);
  };
  let renderer!:ReactTestRenderer;const w=workspace("software-saved-search-adapter");
  await act(async()=>{renderer=create(<Discover workspace={w} capabilities={capability} refresh={async()=>{}} navigate={async value=>{await flushDrafts();destinations.push(value);return {status:"success"};}}/>);});
  try{
    await act(async()=>button(renderer,"Browse collections").props.onClick());await act(async()=>button(renderer,search.name).props.onClick());assert.deepEqual(destinations,[{page:"discover",workspace:w.id,intake:"collections"},{page:"discover",workspace:w.id,search:"software-real-search"}]);
    const withOldSearch={...w,searches:[{id:"software-old-search"}]} as Schema<"WorkspaceSummary">;
    await act(async()=>renderer.update(<Discover workspace={withOldSearch} requestedCollection={snapshot.id} capabilities={capability} refresh={async()=>{}} navigate={async value=>{await flushDrafts();destinations.push(value);return {status:"success"};}}/>));
    assert.equal(calls.some(path=>path.includes("/searches/")),false);assert.match(text(renderer.root),/retained citation records/);assert.equal(renderer.root.findAllByProps({"data-paper-id":"software-paper:1"}).length,1);
  }finally{await act(async()=>renderer.unmount());}
});
