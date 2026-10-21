import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestRenderer} from "react-test-renderer";
import Discover from "../components/discover.tsx";
import type {Schema} from "../lib/api.ts";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});

async function renderSelection(workspaceId:string) {
  const papers:Schema<"Paper">[]=Array.from({length:12},(_,index)=>({
    id:`software-test:${index}`,title:`SOFTWARE TEST PAPER ${index}`,authors:[],
    year:2020,abstract:"Synthetic metadata for selection software tests only.",pmid:null,doi:null,pmcid:null,url:"",
  }));
  const search:Schema<"SearchPreview">={schema_version:"mvp.exploratory-preview.v1",id:"software-search",query:"software test",research_question:"Software test selection",query_translation:null,searched_at:"2026-10-21T00:00:00Z",sort:"relevance",date_from:null,date_to:null,total_reported:12,fetched_count:12,ordered_identifiers:papers.map(paper=>paper.id),papers,warnings:[],truncated:false,provider:"software-test",mode:"test",errors:[]};
  const workspace={id:workspaceId,question:"Software test selection",mode:"saved_example",created_at:search.searched_at,source_revision:0,current_preparation_id:null,selected_paper_ids:[],current_run_id:null,current_assessment_ids:{},searches:[{...search,distinct_count:12}],preparations:[],runs:[],assessments:[]} as Schema<"WorkspaceSummary">;
  const capabilities={default_mode:"saved_example",live_available:false,saved_example:{question:"Software test selection",query:"software test"},limits:{},boards:{max_fields:6,max_cells:60,max_boards:10,max_definition_revisions:20,max_cell_revisions:50,max_references:5,max_workspace_bytes:33554432,max_candidate_characters:1200,max_inspector_characters:4000},map:{ready:false,reason:"No model needed for selection tests"}} as Schema<"Capabilities">;
  globalThis.fetch=async(url,options)=>{
    assert.equal(options?.method??"GET","GET","selection must not prepare sources or call a provider");
    const path=String(url);
    const value=path.endsWith("/session")?{csrf_token:"software-test"}:
      path.endsWith("/papers")?search:
      path.includes("/maps?")?{maps:[],jobs:[]}:
      {scope:decodeURIComponent(path.split("/").at(-1)!),version:0,data:{},expected_assessment_head:null,updated_at:null};
    return new Response(JSON.stringify(value),{headers:{"Content-Type":"application/json"}});
  };
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<Discover workspace={workspace} capabilities={capabilities} refresh={async()=>{}} navigate={async()=>{}}/>);});
  return renderer;
}

const checkboxes=(renderer:ReactTestRenderer)=>renderer.root.findAllByType("input").filter(input=>input.props.type==="checkbox");
const checked=(renderer:ReactTestRenderer)=>checkboxes(renderer).filter(input=>input.props.checked);

test("rapid paper selections from one rendered handler batch retain every choice",async()=>{
  const renderer=await renderSelection("software-rapid-selection");
  try {
    const inputs=checkboxes(renderer);assert.equal(inputs.length,12);
    assert.equal(inputs.every(input=>!input.props.disabled),true);
    // Capture handlers from one render, then batch changes before React rerenders.
    const handlers=inputs.map(input=>input.props.onChange);
    await act(async()=>{for(const change of handlers.slice(0,7))change();});
    assert.equal(checked(renderer).length,7);
    assert.deepEqual(checkboxes(renderer).map(input=>input.props.checked),Array.from({length:12},(_,index)=>index<7));
  } finally {await act(async()=>renderer.unmount());}
});

test("rapid selection preserves the ten-paper cap and deselection frees one slot within the same batch",async()=>{
  const renderer=await renderSelection("software-selection-cap");
  try {
    const handlers=checkboxes(renderer).map(input=>input.props.onChange);
    await act(async()=>{for(const change of handlers)change();});
    assert.equal(checked(renderer).length,10);
    assert.equal(checkboxes(renderer)[10].props.disabled,true);
    assert.equal(checkboxes(renderer)[11].props.disabled,true);
    // A still-mounted handler must read the latest draft, including the removal.
    await act(async()=>{handlers[0]();handlers[10]();handlers[11]();});
    assert.equal(checked(renderer).length,10);
    assert.equal(checkboxes(renderer)[0].props.checked,false);
    assert.equal(checkboxes(renderer)[10].props.checked,true);
    assert.equal(checkboxes(renderer)[11].props.checked,false);
    assert.equal(checkboxes(renderer)[10].props.disabled,false,"a selected paper remains deselectable at the cap");
  } finally {await act(async()=>renderer.unmount());}
});
