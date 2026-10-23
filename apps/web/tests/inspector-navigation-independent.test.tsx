import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestRenderer,type ReactTestInstance} from "react-test-renderer";
import Discover from "../components/discover.tsx";
import type {Schema} from "../lib/api.ts";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const content=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:content(child)).join(" ");
const inspector=(renderer:ReactTestRenderer)=>renderer.root.findByProps({"aria-label":"Paper inspector"});
const previous=(renderer:ReactTestRenderer)=>renderer.root.findByProps({"aria-label":"Previous paper"});
const next=(renderer:ReactTestRenderer)=>renderer.root.findByProps({"aria-label":"Next paper"});
const paperRows=(renderer:ReactTestRenderer)=>renderer.root.findAllByType("article").filter(row=>row.props["data-paper-id"]);
const selections=(renderer:ReactTestRenderer)=>paperRows(renderer).map(row=>row.findByType("input").props.checked);
const localFilter=(renderer:ReactTestRenderer)=>renderer.root.findAllByType("input").find(input=>input.props.type==="search")!;

async function fixture(mobile=false,count=4) {
  const papers:Schema<"Paper">[]=Array.from({length:count},(_,index)=>({id:`independent-inspector:${index}`,
    title:`SOFTWARE PAPER ${index} ${index===1?"other":"visible"}`,authors:["Synthetic author"],year:2020+index,
    abstract:index===2?"Long abstract. ".repeat(400):"Short abstract.",pmid:null,doi:null,pmcid:null,url:""}));
  const search:Schema<"SearchPreview">={schema_version:"mvp.exploratory-preview.v1",id:"independent-inspector-search",query:"software",
    research_question:"Software navigation check",query_translation:null,searched_at:"2026-10-21T00:00:00Z",sort:"relevance",
    date_from:null,date_to:null,total_reported:count,fetched_count:count,ordered_identifiers:papers.map(paper=>paper.id),papers,
    warnings:[],truncated:false,provider:"synthetic-test",mode:"test",errors:[]};
  const workspace={id:`independent-inspector-${mobile}-${count}`,question:search.research_question,mode:"saved_example",
    created_at:search.searched_at,source_revision:0,current_preparation_id:null,selected_paper_ids:[],current_run_id:null,
    current_assessment_ids:{},searches:[{...search,distinct_count:count}],preparations:[],runs:[],assessments:[]} as Schema<"WorkspaceSummary">;
  const capabilities={default_mode:"saved_example",live_available:false,saved_example:{question:search.research_question,query:search.query},
    limits:{max_sources:30,max_prepared_sources:30,max_synchronous_prepared_sources:10,max_results:50,default_results:30,default_passages:5,max_passages:30},
    preparation_jobs_ready:false,search_plans_ready:false,board_span_profiles:null,boards:{max_papers:30,max_fields:6,max_cells:180,max_boards:10,max_definition_revisions:20,max_cell_revisions:50,
      max_references:5,max_workspace_bytes:33554432,max_candidate_characters:1200,max_inspector_characters:4000},
    map:{ready:false,reason:"No model calls in this fixture"}} as Schema<"Capabilities">;
  const artifact={map_id:"independent-inspector-map",search_id:search.id,coordinates_by_paper_id:Object.fromEntries(papers.map((paper,index)=>[paper.id,[index,index%2]])),
    projection_method:"pca_small_corpus_v1",created_at:search.searched_at,status:"ready",representation_by_paper_id:Object.fromEntries(papers.map(paper=>[paper.id,"title_abstract"])),
    excluded_papers_with_reasons:[],coordinate_sha256:"software-coordinates"};
  const requests:{method:string;path:string}[]=[],events:string[]=[];
  const oldFetch=globalThis.fetch,oldWindow=Object.getOwnPropertyDescriptor(globalThis,"window");
  Object.defineProperty(globalThis,"window",{configurable:true,value:{matchMedia:()=>({matches:mobile}),
    scrollTo:()=>events.push("window-scroll"),scrollBy:()=>events.push("window-adjust")}});
  globalThis.fetch=async(url,options)=>{
    const path=String(url),method=options?.method??"GET";requests.push({method,path});assert.equal(method,"GET","Inspector navigation cannot mutate research state");
    let value:unknown;
    if(path.endsWith("/session"))value={csrf_token:"independent-test"};
    else if(path.endsWith("/papers"))value=search;
    else if(path.includes("/maps?"))value={maps:count?[{map_id:artifact.map_id,search_id:search.id,created_at:search.searched_at,status:"ready",projection_method:artifact.projection_method,embedded_count:count,excluded_count:0,paper_count:count}]:[],jobs:[]};
    else if(path.endsWith("/maps/"+artifact.map_id))value={artifact,counts:{provider_reported:count,fetched_records:count,distinct_records:count,embedded_papers:count,excluded_papers:0,map_points:count}};
    else if(path.includes("/neighbors/"))value={map_id:artifact.map_id,paper_id:decodeURIComponent(path.split("/").at(-1)!),neighbors:[]};
    else if(path.includes("/drafts/")){const scope=decodeURIComponent(path.split("/").at(-1)!);value={scope,version:scope.startsWith("selection:")?1:0,data:scope.startsWith("selection:")?{selected_paper_ids:papers[1]?[papers[1].id]:[]}:{},expected_assessment_head:null,updated_at:null};}
    else assert.fail(`Unexpected request ${method} ${path}`);
    return new Response(JSON.stringify(value),{headers:{"Content-Type":"application/json"}});
  };
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<Discover workspace={workspace} capabilities={capabilities} refresh={async()=>assert.fail("Navigation cannot refresh the workspace")} navigate={async()=>assert.fail("Navigation cannot leave the inspector")}/>,{
    createNodeMock:element=>{
      const props=element.props as Record<string,unknown>;
      if(props.id==="paper-inspector")return {scrollIntoView:()=>events.push("explicit-inspect-scroll")};
      if(props["aria-label"]==="Paper inspector navigation")return {getBoundingClientRect:()=>({top:400})};
      return null;
    },
  });});
  return {renderer,papers,requests,events,async inspect(index:number){await act(async()=>paperRows(renderer)[index].findByType("button").props.onClick());},async cleanup(){await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;if(oldWindow)Object.defineProperty(globalThis,"window",oldWindow);else Reflect.deleteProperty(globalThis,"window");}};
}

for(const mobile of [false,true])test(`inspector sequence follows filtered order with stable selection/map/viewport (${mobile?"mobile":"desktop"})`,async()=>{
  const f=await fixture(mobile),r=f.renderer;
  try {
    await f.inspect(0);
    const node=inspector(r),nav=r.root.findByProps({"aria-label":"Paper inspector navigation"});
    const checkedBefore=selections(r);
    await act(async()=>r.root.findByProps({"aria-label":"Zoom map in"}).props.onClick());
    await act(async()=>r.root.findByProps({"aria-label":"Pan map left"}).props.onClick());
    const transform=r.root.findByType("g").props.transform,mapFetches=f.requests.filter(request=>request.path.endsWith("/maps/independent-inspector-map")).length;
    f.events.length=0;
    assert.equal(previous(r).props.disabled,true);assert.equal(next(r).props.disabled,false);
    assert.match(content(nav),/1 of 4/);
    assert.equal(previous(r).props.type,"button");assert.equal(next(r).props.type,"button");
    await act(async()=>localFilter(r).props.onChange({target:{value:"visible"}}));
    assert.match(content(nav),/1 of 3/);
    await act(async()=>next(r).props.onClick());
    assert.match(content(inspector(r)),/SOFTWARE PAPER 2 visible/);assert.match(content(nav),/2 of 3/);
    await act(async()=>previous(r).props.onClick());
    // Capture one render's handler: batched navigation must use current state.
    const goNext=next(r).props.onClick;
    await act(async()=>{goNext();goNext();goNext();});
    assert.match(content(inspector(r)),/SOFTWARE PAPER 3 visible/);assert.match(content(nav),/3 of 3/);
    assert.equal(next(r).props.disabled,true);
    assert.equal(inspector(r),node,"Stable inspector DOM retains focus across title/abstract changes");
    assert.equal(r.root.findByProps({"aria-label":"Paper inspector navigation"}),nav);
    assert.equal(r.root.findByType("g").props.transform,transform);
    assert.equal(f.requests.filter(request=>request.path.endsWith("/maps/independent-inspector-map")).length,mapFetches);
    assert.deepEqual(f.events,[],"Sequence navigation does not invoke reveal/scroll/focus actions when controls remain in place");
    await act(async()=>localFilter(r).props.onChange({target:{value:"other"}}));
    assert.match(content(inspector(r)),/Outside the current filter/i);
    assert.equal(previous(r).props.disabled,true);assert.equal(next(r).props.disabled,true);
    assert.match(content(inspector(r)),/SOFTWARE PAPER 3 visible/);
    await act(async()=>localFilter(r).props.onChange({target:{value:""}}));
    assert.match(content(nav),/4 of 4/);assert.deepEqual(selections(r),checkedBefore);
    assert.equal(f.requests.every(request=>request.method==="GET"),true);
  } finally {await f.cleanup();}
});

test("empty and singleton previews have no invented or wrapping inspector neighbors",async()=>{
  const empty=await fixture(false,0);
  try{assert.equal(empty.renderer.root.findAllByProps({"aria-label":"Paper inspector navigation"}).length,0);assert.match(content(empty.renderer.root),/No records/);}finally{await empty.cleanup();}
  const singleton=await fixture(false,1);
  try{await singleton.inspect(0);const r=singleton.renderer;assert.equal(previous(r).props.disabled,true);assert.equal(next(r).props.disabled,true);assert.match(content(r.root.findByProps({"aria-label":"Paper inspector navigation"})),/1 of 1/);await act(async()=>{previous(r).props.onClick();next(r).props.onClick();});assert.match(content(inspector(r)),/SOFTWARE PAPER 0 visible/);}finally{await singleton.cleanup();}
});
