import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestRenderer} from "react-test-renderer";
import Discover from "../components/discover.tsx";
import type {Schema} from "../lib/api.ts";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});

test("opening the current offline bundle ignores stale one-paper draft controls and displays its saved map without inference",{timeout:5000},async context=>{
  const oldQuery="SOFTWARE HISTORICAL QUERY",query="SOFTWARE CURRENT BUNDLED QUERY";
  const papers=Array.from({length:30},(_,index)=>({id:`software-offline:${index}`,title:`SOFTWARE OFFLINE PAPER ${index}`,authors:[],year:2020,abstract:"Synthetic metadata only; no scientific evidence.",pmid:null,pmcid:null,doi:null,url:""}));
  const preview={schema_version:"mvp.exploratory-preview.v1",id:"new-offline-search",query,research_question:"Retained reviewer question",query_translation:null,searched_at:"2026-10-21T00:00:00Z",sort:"Recorded relevance",date_from:null,date_to:null,total_reported:100,fetched_count:30,ordered_identifiers:papers.map(paper=>paper.id),papers,warnings:[],truncated:true,provider:"software-offline-test",mode:"saved_example",errors:[]} as Schema<"SearchPreview">;
  const historical={...preview,id:"old-offline-search",query:oldQuery,fetched_count:1,papers:papers.slice(0,1),ordered_identifiers:papers.slice(0,1).map(paper=>paper.id)};
  const workspace={id:"software-offline-upgrade",question:"Retained reviewer question",mode:"saved_example",created_at:preview.searched_at,source_revision:0,current_preparation_id:null,selected_paper_ids:[],current_run_id:null,current_assessment_ids:{},searches:[{...historical,distinct_count:1}],preparations:[],runs:[],assessments:[]} as Schema<"WorkspaceSummary">;
  const capabilities={default_mode:"saved_example",live_available:false,saved_example:{question:"Example question",query,paper_count:30,bundle_id:"software-public-bundle-v2"},limits:{},boards:{max_fields:6,max_cells:60,max_boards:10,max_definition_revisions:20,max_cell_revisions:50,max_references:5,max_workspace_bytes:33554432,max_candidate_characters:1200,max_inspector_characters:4000},map:{ready:false,reason:"No optional model installed"}} as Schema<"Capabilities">;
  const artifact={map_id:"software-bundled-map",search_id:preview.id,coordinates_by_paper_id:Object.fromEntries(papers.map((paper,index)=>[paper.id,[index,index%3]])),projection_method:"umap_cosine_v1",projection_parameters:{saved_example_bundle:{bundle_id:"software-public-bundle-v2"}},created_at:preview.searched_at,status:"ready",representation_by_paper_id:{},excluded_papers_with_reasons:[],coordinate_sha256:"software-coordinate-digest"};
  const requests:{url:string;method:string;body:Record<string,unknown>|null}[]=[];
  const originalFetch=globalThis.fetch,originalStorage=Object.getOwnPropertyDescriptor(globalThis,"sessionStorage");
  const storage=new Map<string,string>();
  Object.defineProperty(globalThis,"sessionStorage",{configurable:true,value:{getItem:(key:string)=>storage.get(key)??null,setItem:(key:string,value:string)=>storage.set(key,value)}});
  let finishPost!:()=>void;
  const posted=new Promise<void>((resolve,reject)=>{finishPost=resolve;context.signal.addEventListener("abort",()=>reject(context.signal.reason),{once:true});});
  globalThis.fetch=async(url,options)=>{
    const path=String(url),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):null;
    requests.push({url:path,method,body});let value:unknown;
    if(path.endsWith("/session"))value={csrf_token:"software-offline"};
    else if(path.endsWith("/drafts/discover"))value={scope:"discover",version:1,data:{question:workspace.question,query:oldQuery,max_results:1,use_dates:true,date_from:"2000-01-01",date_to:"2001-01-01",sort:"pub_date"},expected_assessment_head:null,updated_at:null};
    else if(path.endsWith("/searches")&&method==="POST"){value=preview;finishPost();}
    else if(path.endsWith("/papers"))value=path.includes(historical.id)?historical:preview;
    else if(path.includes("/maps?"))value={maps:path.includes(preview.id)?[{map_id:artifact.map_id,search_id:preview.id,created_at:preview.searched_at,status:"ready",projection_method:artifact.projection_method,embedded_count:30,excluded_count:0,paper_count:30}]:[],jobs:[]};
    else if(path.endsWith("/maps/"+artifact.map_id))value={artifact,counts:{provider_reported:100,fetched_records:30,distinct_records:30,embedded_papers:30,excluded_papers:0,map_points:30}};
    else if(path.includes("/drafts/selection"))value={scope:decodeURIComponent(path.split("/").at(-1)!),version:0,data:{},expected_assessment_head:null,updated_at:null};
    else assert.fail(`Unexpected request ${method} ${path}`);
    return new Response(JSON.stringify(value),{headers:{"Content-Type":"application/json"}});
  };
  let renderer!:ReactTestRenderer;
  try{
    await act(async()=>{renderer=create(<Discover workspace={workspace} capabilities={capabilities} refresh={async()=>{}} navigate={async next=>assert.equal(next.search,preview.id)}/>);});
    const recorded=renderer.root.findAllByType("textarea").find(input=>input.props.readOnly)!;
    assert.equal(recorded.props.value,query,"the current bundle query is displayed even when an older draft retained a different capture");
    assert.equal(renderer.root.findAllByType("article").length,1,"historical saved preview stays intact before explicit opening");
    await act(async()=>{renderer.root.findByType("form").props.onSubmit({preventDefault(){}});await posted;});
    const submitted=requests.find(request=>request.method==="POST")!;
    assert.equal(submitted.body!.query,query);assert.equal(submitted.body!.max_results,30);
    assert.equal(submitted.body!.date_from,null);assert.equal(submitted.body!.date_to,null);assert.equal(submitted.body!.sort,"relevance");
    assert.equal(submitted.body!.research_question,workspace.question);
    assert.equal("saved_example_bundle" in submitted.body!,false,"bundle identity is only an idempotency fingerprint, not an undeclared API field");
    assert.equal(renderer.root.findAllByType("article").length,30);
    assert.equal(renderer.root.findAllByType("circle").length,30,"unavailable local inference does not hide a precomputed map");
    assert.equal(requests.filter(request=>request.method!=="GET").length,1,"opening only posts the local saved search; no build, source or live-provider request");
    assert.equal(requests.some(request=>request.url.endsWith("/maps")&&request.method==="POST"),false);
  }finally{
    if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;
    if(originalStorage)Object.defineProperty(globalThis,"sessionStorage",originalStorage);else Reflect.deleteProperty(globalThis,"sessionStorage");
  }
});
