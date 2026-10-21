import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Discover from "../components/discover.tsx";
import type {Schema} from "../lib/api.ts";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});

/** Synthetic metadata exercises UI coordination; it is not a retrieval/model evaluation. */
async function renderSavedMap(workspaceId:string) {
  const papers:Schema<"Paper">[]=Array.from({length:12},(_,index)=>({
    id:`software-map:${index}`,title:`SOFTWARE MAP PAPER ${index}`,authors:["Synthetic test author"],
    year:2020,abstract:`Synthetic selection software fixture ${index}.`,pmid:null,doi:null,pmcid:null,url:"",
  }));
  const search:Schema<"SearchPreview">={schema_version:"mvp.exploratory-preview.v1",id:"software-map-search",query:"software test",research_question:"Software test linked selection",query_translation:null,searched_at:"2026-10-21T00:00:00Z",sort:"relevance",date_from:null,date_to:null,total_reported:512,fetched_count:12,ordered_identifiers:papers.map(paper=>paper.id),papers,warnings:[],truncated:true,provider:"software-test",mode:"test",errors:[]};
  const workspace={id:workspaceId,question:search.research_question,mode:"saved_example",created_at:search.searched_at,source_revision:0,current_preparation_id:null,selected_paper_ids:[],current_run_id:null,current_assessment_ids:{},searches:[{...search,distinct_count:12}],preparations:[],runs:[],assessments:[]} as Schema<"WorkspaceSummary">;
  const capabilities={default_mode:"saved_example",live_available:false,saved_example:{question:search.research_question,query:"software test"},limits:{},boards:{max_fields:6,max_cells:60,max_boards:10,max_definition_revisions:20,max_cell_revisions:50,max_references:5,max_workspace_bytes:33554432,max_candidate_characters:1200,max_inspector_characters:4000},map:{ready:false,reason:"No model runs in this software fixture"}} as Schema<"Capabilities">;
  const coordinates=Object.freeze(Object.fromEntries(papers.map((paper,index)=>[paper.id,Object.freeze([index,index%3])])));
  const artifact={map_id:"software-persisted-map",search_id:search.id,coordinates_by_paper_id:coordinates,projection_method:"pca_small_corpus_v1",created_at:search.searched_at,status:"ready",representation_by_paper_id:Object.fromEntries(papers.map(paper=>[paper.id,"title_abstract"])),excluded_papers_with_reasons:[],coordinate_sha256:"software-persisted-checksum"};
  const listing={maps:[{map_id:artifact.map_id,search_id:search.id,created_at:artifact.created_at,status:artifact.status,projection_method:artifact.projection_method,embedded_count:12,excluded_count:0,paper_count:12}],jobs:[]};
  const requests:{method:string;url:string;body:unknown}[]=[];
  const savedDrafts=new Map<string,{version:number;data:Record<string,unknown>}>();
  globalThis.fetch=async(url,options)=>{
    const path=String(url),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;
    requests.push({method,url:path,body});
    let value:unknown;
    if(path.endsWith("/session"))value={csrf_token:"software-test"};
    else if(path.endsWith("/papers"))value=search;
    else if(path.includes("/maps?"))value=listing;
    else if(path.endsWith("/maps/"+artifact.map_id))value={artifact,counts:{provider_reported:512,fetched_records:12,distinct_records:12,embedded_papers:12,excluded_papers:0,map_points:12}};
    else if(path.includes("/drafts/")){
      const scope=decodeURIComponent(path.split("/").at(-1)!);
      if(method==="PUT")savedDrafts.set(scope,{version:body.version+1,data:body.data});
      const saved=savedDrafts.get(scope)??{version:0,data:{}};
      value={scope,...saved,expected_assessment_head:null,updated_at:null};
    }else assert.fail(`Unexpected ${method} request: ${path}`);
    return new Response(JSON.stringify(value),{headers:{"Content-Type":"application/json"}});
  };
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<Discover workspace={workspace} capabilities={capabilities} requestedMap={artifact.map_id} refresh={async()=>{assert.fail("Selection must not refresh the workspace");}} navigate={async()=>{assert.fail("Selection must not navigate or rebuild the map");}}/>);});
  return {renderer,papers,artifact,requests};
}

const checkboxes=(renderer:ReactTestRenderer)=>renderer.root.findAllByType("input").filter(input=>input.props.type==="checkbox");
const point=(renderer:ReactTestRenderer,id:string)=>renderer.root.findByProps({"data-map-point":id});
const transform=(renderer:ReactTestRenderer)=>renderer.root.findByType("g").props.transform;
const pointPositions=(renderer:ReactTestRenderer)=>renderer.root.findAllByType("circle").map(circle=>[circle.props["data-map-point"],circle.props.cx,circle.props.cy]);
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");

function assertSelected(renderer:ReactTestRenderer,id:string,selected:boolean) {
  const marker=point(renderer,id);
  assert.equal(marker.props.className.split(" ").includes("selected"),selected);
  assert.equal(marker.props["aria-label"].includes("; selected for exploration"),selected,"the accessible marker description follows the paper checkbox");
}

function assertNoMapComputation(requests:{method:string;url:string}[]) {
  assert.equal(requests.some(request=>request.method==="POST"),false,"selection and navigation never submit provider or map work");
  assert.equal(requests.filter(request=>request.url.endsWith("/maps/software-persisted-map")).length,1,"selection does not reload or refit the persisted coordinates");
  assert.equal(requests.filter(request=>request.url.includes("/maps")).every(request=>request.method==="GET"),true);
}

test("every paper checkbox selection and deselection immediately update the saved map without resetting its view",async()=>{
  const {renderer,papers,artifact,requests}=await renderSavedMap("software-linked-map-selection");
  try {
    const coordinatesBefore=JSON.stringify(artifact.coordinates_by_paper_id),positionsBefore=pointPositions(renderer);
    assertSelected(renderer,papers[0].id,false);
    await act(async()=>renderer.root.findByProps({"aria-label":"Zoom map in"}).props.onClick());
    await act(async()=>renderer.root.findByProps({"aria-label":"Pan map left"}).props.onClick());
    const transformed=transform(renderer);
    for(let index=0;index<papers.length;index++){
      await act(async()=>checkboxes(renderer)[index].props.onChange());
      assertSelected(renderer,papers[index].id,true);assert.equal(checkboxes(renderer)[index].props.checked,true);
      assert.match(text(renderer.root.findByProps({"aria-label":"Semantic exploration"})),/1 selected for exploration/);
      assert.match(text(renderer.root),/1 selected · 0 prepared/);
      await act(async()=>checkboxes(renderer)[index].props.onChange());
      assertSelected(renderer,papers[index].id,false);assert.equal(checkboxes(renderer)[index].props.checked,false);
      assert.match(text(renderer.root.findByProps({"aria-label":"Semantic exploration"})),/0 selected for exploration/);
      assert.match(text(renderer.root),/0 selected · 0 prepared/);
      assert.equal(transform(renderer),transformed,"every change preserves the map view");
    }
    assert.equal(transform(renderer),transformed,"selection changes styling, preserving zoom and pan");
    assert.deepEqual(pointPositions(renderer),positionsBefore);assert.equal(JSON.stringify(artifact.coordinates_by_paper_id),coordinatesBefore);
    assert.equal(artifact.coordinate_sha256,"software-persisted-checksum");assertNoMapComputation(requests);
  } finally {await act(async()=>renderer.unmount());}
});

test("rapid capped checkbox changes stay linked to the map across mobile panel switches",async()=>{
  const {renderer,papers,requests}=await renderSavedMap("software-rapid-linked-map-selection");
  try {
    const map=renderer.root.findByType("svg"),positionsBefore=pointPositions(renderer);
    await act(async()=>renderer.root.findByProps({"aria-label":"Zoom map in"}).props.onClick());
    const transformed=transform(renderer);
    const tabs=renderer.root.findByProps({"aria-label":"Mobile exploration view"}).findAllByType("button");
    await act(async()=>tabs[1].props.onClick());
    assert.equal(renderer.root.findByProps({"data-exploration-panel":"map"}).props["data-active"],false);
    const handlers=checkboxes(renderer).map(input=>input.props.onChange);
    await act(async()=>{for(const change of handlers)change();});
    assert.equal(checkboxes(renderer).filter(input=>input.props.checked).length,10);
    for(let index=0;index<12;index++)assertSelected(renderer,papers[index].id,index<10);
    assert.match(text(renderer.root.findByProps({"aria-label":"Semantic exploration"})),/10 selected for exploration/);
    await act(async()=>{handlers[0]();handlers[10]();handlers[11]();});
    assertSelected(renderer,papers[0].id,false);assertSelected(renderer,papers[10].id,true);assertSelected(renderer,papers[11].id,false);
    assert.equal(checkboxes(renderer).filter(input=>input.props.checked).length,10);
    await act(async()=>tabs[0].props.onClick());
    assert.equal(renderer.root.findByProps({"data-exploration-panel":"map"}).props["data-active"],true);
    assert.equal(renderer.root.findByType("svg"),map,"switching panels preserves the mounted map");
    assert.equal(transform(renderer),transformed);assert.deepEqual(pointPositions(renderer),positionsBefore);
    assertNoMapComputation(requests);
  } finally {await act(async()=>renderer.unmount());}
});
