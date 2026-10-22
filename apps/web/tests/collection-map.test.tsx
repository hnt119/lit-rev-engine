import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import {CollectionMapExplorer} from "../components/map-explorer";
import {CollectionPicker} from "../components/collection-explorer";
import {collection,response,storage} from "./import-collection-fixtures";
import {research} from "./collection-research-fixtures";
import type {Schema} from "../lib/api";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
const button=(renderer:ReactTestRenderer,label:string)=>renderer.root.findAllByType("button").find(item=>text(item)===label)!;
const deferred=<T,>()=>{let resolve!:(value:T)=>void;const promise=new Promise<T>(done=>resolve=done);return{promise,resolve};};

test("saved collection maps preserve pan/zoom and exact coordinates through filters/selection without model or mutation calls",async()=>{
  const f=research("saved-collection-map"),calls:string[]=[];globalThis.fetch=async(input,options)=>{const path=String(input);calls.push(path);assert.equal(options?.method??"GET","GET");if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.includes("/collection-maps?"))return response({maps:[f.mapSummary],jobs:[]});if(path.endsWith("/collection-maps/"+f.artifact.map_id))return response(f.mapView);throw new Error("Unexpected software-test GET "+path);};
  const props={workspaceId:f.state.id,collectionRef:f.collectionRef,papers:f.papers,capability:{ready:false,reason:"No model execution in software tests"},visibleIds:new Set(f.papers.map(item=>item.id)),selectedIds:new Set<string>(),inspectedId:null,hoveredId:null,onInspect:()=>{},onHover:()=>{},onChooseMap:()=>{}};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<CollectionMapExplorer {...props}/>);});
  try{
    assert.equal(renderer.root.findAllByType("circle").length,3);assert.doesNotMatch(text(renderer.root),/provider matches| fetched/);
    await act(async()=>renderer.root.findByProps({"aria-label":"Zoom map in"}).props.onClick());await act(async()=>renderer.root.findByProps({"aria-label":"Pan map left"}).props.onClick());const transform=renderer.root.findByType("g").props.transform,before=JSON.stringify(f.artifact.coordinates_by_paper_id);
    await act(async()=>renderer.update(<CollectionMapExplorer {...props} visibleIds={new Set([f.papers[1].id])} selectedIds={new Set([f.papers[1].id])}/>));assert.equal(renderer.root.findAllByType("circle").length,1);assert.match(renderer.root.findByType("circle").props.className,/selected/);assert.equal(renderer.root.findByType("g").props.transform,transform);assert.equal(JSON.stringify(f.artifact.coordinates_by_paper_id),before);assert.equal(calls.filter(path=>path.endsWith("/collection-maps/"+f.artifact.map_id)).length,1);assert.equal(calls.some(path=>path.includes("/searches/")),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("collection map build and cancellation use explicit origin-bound actions and never create a search",async()=>{
  const f=research("build-collection-map"),calls:{path:string;method:string;body:any}[]=[];let savedJob:Schema<"CollectionMapJobView">|null=null;Object.assign(globalThis,{sessionStorage:storage()});
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;calls.push({path,method,body});if(path.endsWith("/session"))return response({csrf_token:"software"});if(method==="GET"&&path.includes("/collection-maps?"))return response({maps:[],jobs:savedJob?[savedJob]:[]});if(method==="POST"&&path.endsWith("/collection-maps")){assert.deepEqual(body.collection_ref,f.collectionRef);assert.equal("search_id" in body,false);savedJob=f.mapJob();return response({job:savedJob,reused:false,map_id:null});}if(method==="POST"&&path.endsWith("/cancel")){savedJob=f.mapJob({status:"cancel_requested"});return response(savedJob);}throw new Error("Unexpected software-test request "+path);};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<CollectionMapExplorer workspaceId={f.state.id} collectionRef={f.collectionRef} papers={f.papers} capability={{ready:true,reason:"Mock only"}} visibleIds={new Set(f.papers.map(item=>item.id))} selectedIds={new Set()} inspectedId={null} hoveredId={null} onInspect={()=>{}} onHover={()=>{}} onChooseMap={()=>{}}/>);});
  try{assert.equal(calls.every(call=>call.method==="GET"),true);assert.match(text(renderer.root),/No persisted semantic map for this saved collection yet/);await act(async()=>button(renderer,"Build map of this saved collection").props.onClick());await act(async()=>button(renderer,"Cancel map build").props.onClick());const posts=calls.filter(call=>call.method==="POST");assert.equal(posts.length,2);assert.match(posts[1].path,/\/collection-map-jobs\/map-job-build-collection-map\/cancel$/);assert.deepEqual(posts[1].body,{});}
  finally{await act(async()=>renderer.unmount());}
});

test("selected subsets preview and commit only explicit paper membership with the immutable origin digest",async()=>{
  const f=research("selected-subset",4),selected=[f.papers[0].id,f.papers[2].id],calls:{path:string;method:string;body:any}[]=[],chosen:string[]=[];Object.assign(globalThis,{sessionStorage:storage()});
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;calls.push({path,method,body});if(path.endsWith("/session"))return response({csrf_token:"software"});assert.equal(method,"POST","subset review must not load all collections or call metadata providers");assert.deepEqual(body.sources,[{origin:f.collectionRef,paper_ids:selected}]);if(path.endsWith("/combine-preview"))return response({input_sha256:"7".repeat(64),member_count:2,duplicate_groups:[],members:[],sources:[f.collectionRef]});assert.match(path,/\/combine$/);assert.equal(body.preview_sha256,"7".repeat(64));return response({...collection("saved-selected-subset",2),kind:"subset",coverage:"explicit_subset"});};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<CollectionPicker workspaceId={f.state.id} subset={{collection:f.summary,paperIds:selected}} onChoose={async value=>{chosen.push(value.id);}}/>);});
  try{assert.equal(calls.length,0);await act(async()=>button(renderer,"Preview selected subset").props.onClick());await act(async()=>button(renderer,"Commit reviewed subset").props.onClick());assert.deepEqual(chosen,["saved-selected-subset"]);assert.equal(calls.filter(call=>call.method==="POST").length,2);}
  finally{await act(async()=>renderer.unmount());}
});

test("a late collection-map poll cannot undo explicit cancellation",async context=>{
  context.mock.timers.enable({apis:["setTimeout"]});const f=research("cancel-collection-map"),delayed=deferred<Response>();let phase:Schema<"CollectionMapJobView">["status"]="running",reads=0;
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET";if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.includes("/collection-maps?"))return response({maps:[],jobs:[f.mapJob({status:phase})]});if(method==="POST"&&path.endsWith("/cancel")){phase="cancel_requested";return response(f.mapJob({status:phase}));}if(path.includes("/collection-map-jobs/")){if(reads++===0)return delayed.promise;phase="cancelled";return response(f.mapJob({status:phase}));}throw new Error("Unexpected software-test request "+path);};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<CollectionMapExplorer workspaceId={f.state.id} collectionRef={f.collectionRef} papers={f.papers} capability={{ready:false,reason:"Mock only"}} visibleIds={new Set(f.papers.map(item=>item.id))} selectedIds={new Set()} inspectedId={null} hoveredId={null} onInspect={()=>{}} onHover={()=>{}} onChooseMap={()=>{}}/>);});
  try{await act(async()=>context.mock.timers.tick(1000));await act(async()=>button(renderer,"Cancel map build").props.onClick());await act(async()=>delayed.resolve(response(f.mapJob({status:"running"}))));assert.match(text(renderer.root),/cancel requested/);await act(async()=>context.mock.timers.tick(1000));assert.match(text(renderer.root),/cancelled/);}
  finally{await act(async()=>renderer.unmount());}
});
