import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Compare from "../components/compare";
import {BoardCandidates} from "../components/board-candidates";
import {BoardRetrievalProfile,retainedExplicitRequirements,type ComponentRequirements,type BoardProfile} from "../components/board-retrieval-profile";
import {research} from "./collection-research-fixtures";
import {response,storage,stamp} from "./import-collection-fixtures";
import type {Schema} from "../lib/api";
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(text).join("");
const button=(renderer:ReactTestRenderer,label:string)=>renderer.root.findAllByType("button").find(item=>text(item)===label)!;
const field=(renderer:ReactTestRenderer,name:string)=>renderer.root.findAllByType("label").find(item=>item.children[0]===name)!.findAll(item=>["select","input","textarea"].includes(String(item.type)))[0];
const capability:Schema<"BoardSpanCapability">={enabled:true,profile_ids:["legacy_block_prefix_v1","lexical_spans_v1"],default_profile_id:"legacy_block_prefix_v1",max_requirements_per_field:3,max_candidates_per_field:3,max_candidate_characters:1200,max_candidate_budget_tokens:400,max_delivered_characters:3600,max_delivered_budget_tokens:1200,max_indexed_blocks:2048,max_indexed_windows:8192,max_indexed_characters:4000000,max_search_seconds:8,budget_tokenizer_id:"unicode-word-or-nonspace-punctuation-v1",meaning:"Software fixture"};

test("new boards disclose a pinned default profile and retain explicit per-field component queries in the v2 request",async()=>{
  const f=research("span-create"),calls:{path:string;method:string;body:any}[]=[],destinations:any[]=[];Object.assign(globalThis,{sessionStorage:storage()});
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;calls.push({path,method,body});if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.endsWith("/boards"))return response(method==="GET"?{boards:[],limits:f.capability.boards}:{definition:{board_id:"software-new-board"}});if(path.endsWith("/papers"))return response(f.preparationPapers);if(path.endsWith("/source-preparations/"+f.preparation.id))return response(f.preparation);throw new Error("No hidden provider/map call "+path);};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<Compare workspace={f.state} retrievalCapability={capability} navigate={async value=>{destinations.push(value);}}/>);});
  try{
    await act(async()=>button(renderer,"Create comparison board").props.onClick());assert.equal(button(renderer,"Create comparison board").props.disabled,false);
    assert.equal(field(renderer,"Retrieval profile for this definition").props.value,"lexical_spans_v1");assert.equal(calls.filter(call=>call.method!=="GET").length,0);
    await act(async()=>field(renderer,"Retrieval profile for this definition").props.onChange({target:{value:"lexical_spans_v1"}}));
    await act(async()=>button(renderer,"Add component to Population").props.onClick());
    const labels=renderer.root.findAllByType("label");await act(async()=>labels.find(item=>item.children[0]==="Component ")!.findByType("input").props.onChange({target:{value:"Participant origin"}}));
    await act(async()=>renderer.root.findAllByType("label").find(item=>item.children[0]==="Component "&&item.findAllByType("textarea").length)!.findByType("textarea").props.onChange({target:{value:"Asian women participant population"}}));
    assert.equal(calls.filter(call=>call.method!=="GET").length,0);await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));
    const submitted=calls.find(call=>call.method==="POST")!.body;assert.equal(submitted.schema_version,"mvp.board-profile-request.v2");assert.equal(submitted.retrieval_profile_id,"lexical_spans_v1");assert.equal(submitted.field_requirements.length,1);assert.equal(submitted.field_requirements[0].field_id,"population");assert.equal(submitted.field_requirements[0].requirements[0].query,"Asian women participant population");assert.equal(submitted.preparation_id,f.preparation.id);assert.equal(submitted.paper_ids.length,3);assert.equal(destinations[0].board,"software-new-board");
  }finally{await act(async()=>renderer.unmount());}
});

test("advanced components are bounded, preserved on field edits, and removed only by an explicit legacy-profile action",async()=>{
  let profile:BoardProfile|""="lexical_spans_v1",requirements:ComponentRequirements={population:[{id:"origin",label:"Origin",query:"participant origin"}]},renderer!:ReactTestRenderer;
  const fields=[{id:"population",label:"Population",subquestion:"Changed field question"}],original={fields:[{...fields[0],revision_id:"old-field",subquestion:"Original field question"}],retrieval_profile:{profile_id:"lexical_spans_v1",explicit_requirement_field_ids:["population"],requirements_by_field:requirements}} as unknown as Schema<"BoardView">["definition"];
  assert.deepEqual(retainedExplicitRequirements(original.retrieval_profile),requirements);
  const render=()=> <BoardRetrievalProfile profile={profile} onProfile={value=>{profile=value;renderer.update(render());}} requirements={requirements} onRequirements={update=>{requirements=update(requirements);renderer.update(render());}} fields={fields} original={original} capability={capability}/>;
  globalThis.fetch=async()=>{throw new Error("Component editing must remain local");};await act(async()=>{renderer=create(render());});
  try{
    assert.match(text(renderer.root),/field subquestion changed/);assert.equal(requirements.population[0].query,"participant origin");const add=button(renderer,"Add component to Population").props.onClick;await act(async()=>{for(let index=0;index<5;index++)add();});assert.equal(requirements.population.length,3);
    await act(async()=>field(renderer,"Retrieval profile for this definition").props.onChange({target:{value:"legacy_block_prefix_v1"}}));assert.equal(requirements.population.length,3);assert.match(text(renderer.root),/Legacy retrieval cannot execute explicit component queries/);
    await act(async()=>button(renderer,"Remove explicit component queries from this draft").props.onClick());assert.deepEqual(requirements,{});assert.equal((original.retrieval_profile.requirements_by_field as ComponentRequirements).population.length,1);
  }finally{await act(async()=>renderer.unmount());}
});

test("span candidate display distinguishes exact ranges, omitted context and lexical component matches from inspection/support",async()=>{
  const quote="女性😀 participants were not a validation cohort.",reference:Schema<"BoardReference">={id:"software-span-ref",paper_id:"p1",source_id:"s1",source_version:"v1",source_sha256:"a".repeat(64),blocks_sha256:"b".repeat(64),block_id:"late",start:2000,end:2000+Array.from(quote).length,quote,locator:{section:"Results"},integrity:"checked"};
  const result:Schema<"SpanBoardCandidates">={schema_version:"mvp.board-candidates.spans.v2",id:"software-run",board_id:"software-board",board_revision_id:"revision",paper_id:"p1",field_id:"population",field_revision_id:"field-revision",preparation_id:"prep",source_manifest_sha256:"c".repeat(64),retrieval_profile:{profile_id:"lexical_spans_v1"},retrieval_profile_sha256:"d".repeat(64),indexed_blocks:1,matched_blocks:1,returned_count:1,omitted_matched_blocks:0,candidates:[{rank:1,score:2,reference,total_block_characters:4000,omitted_characters:4000-Array.from(quote).length,omitted_before:2000,omitted_after:4000-reference.end,matched_requirement_ids:["population"],budget_tokens:10,hard_boundary_clipped:true}],requirements:[{id:"population",label:"Participant origin",query:"Asian women"},{id:"validation",label:"Validation population",query:"validation cohort"}],requirement_matches:[{requirement_id:"population",matched_windows:2,selected_windows:1,state:"candidates_selected",index_incomplete:false,meaning:"lexical_potential_not_inspected_or_supported"},{requirement_id:"validation",matched_windows:0,selected_windows:0,state:"no_lexical_match",index_incomplete:false,meaning:"lexical_potential_not_inspected_or_supported"}],indexed_windows:5,matched_windows:2,omitted_matched_windows:1,total_source_blocks:1,unindexed_source_blocks:0,partially_indexed_blocks:0,skipped_blank_blocks:0,total_source_characters:4000,indexed_source_characters:4000,unindexed_source_characters:0,delivered_characters:Array.from(quote).length,delivered_budget_tokens:10,budget_tokenizer_id:capability.budget_tokenizer_id,index_limits:[],warnings:[],elapsed_seconds:0.01,context_scope:"exact_retained_spans_only_not_whole_paper",meaning:"potential_relevance_not_inspected_support",created_at:stamp};
  const before=JSON.stringify(result),inspected:Schema<"BoardReference">[]=[];let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<BoardCandidates result={result} busy={false} onInspect={async value=>{inspected.push(value);}}/>);});
  try{
    assert.match(text(renderer.root),new RegExp("EXACT CODE POINTS 2000–"+reference.end));assert.match(text(renderer.root),/2000 omitted before/);assert.match(text(renderer.root),/Participant origin · candidates selected/);assert.match(text(renderer.root),/Validation population · no lexical match/);assert.match(text(renderer.root),/not measured model tokens/);assert.match(text(renderer.root),/NOT INSPECTED SUPPORT/);assert.equal(inspected.length,0);
    await act(async()=>button(renderer,"Read in source · passage 1").props.onClick());assert.deepEqual(inspected,[reference]);assert.equal(JSON.stringify(result),before);assert.deepEqual(reference.locator,{section:"Results"});
  }finally{await act(async()=>renderer.unmount());}
});
