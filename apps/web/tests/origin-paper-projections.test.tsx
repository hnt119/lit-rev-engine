import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Compare from "../components/compare";
import Evidence from "../components/evidence";
import {response,stamp,storage} from "./import-collection-fixtures";
import {research} from "./collection-research-fixtures";
import type {Schema} from "../lib/api";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,document:{getElementById:()=>null}});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
const button=(renderer:ReactTestRenderer,label:string)=>renderer.root.findAllByType("button").find(item=>text(item)===label)!;

test("new comparison definitions use small preparation bibliography projections for collection sources without loading a search",async()=>{
  const f=research("board-origin"),calls:{path:string;method:string;body:any}[]=[];Object.assign(globalThis,{sessionStorage:storage()});
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;calls.push({path,method,body});assert.equal(method,"GET");if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.endsWith("/boards"))return response({boards:[],limits:f.capability.boards});if(path.endsWith("/source-preparations/"+f.preparation.id+"/papers"))return response(f.preparationPapers);if(path.endsWith("/source-preparations/"+f.preparation.id))return response(f.preparation);throw new Error("Unexpected software-test request "+path);};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<Compare workspace={f.state} navigate={async()=>{}}/>);});
  try{await act(async()=>button(renderer,"Create comparison board").props.onClick());const form=renderer.root.findByProps({"aria-label":"New comparison board"});assert.equal(form.findAllByProps({className:"check board-paper-choice"}).length,3);assert.match(text(form),/Abstract only/);assert.equal(button(renderer,"Create manual comparison board").props.disabled,false);assert.equal(calls.some(call=>call.path.includes("/searches/")),false);assert.equal(calls.filter(call=>call.path.endsWith("/papers")).length,1);}
  finally{await act(async()=>renderer.unmount());}
});

test("a mismatched preparation projection blocks definition creation and preserves the actual binding",async()=>{
  const f=research("wrong-board-origin");globalThis.fetch=async(input,options)=>{const path=String(input);assert.equal(options?.method??"GET","GET");if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.endsWith("/boards"))return response({boards:[],limits:f.capability.boards});if(path.endsWith("/papers"))return response({...f.preparationPapers,origin:{...f.collectionRef,collection_snapshot_sha256:"0".repeat(64)}});return response(f.preparation);};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<Compare workspace={f.state} navigate={async()=>{}}/>);});
  try{await act(async()=>button(renderer,"Create comparison board").props.onClick());assert.match(text(renderer.root),/bibliography does not match/);assert.equal(button(renderer,"Create manual comparison board").props.disabled,true);}
  finally{await act(async()=>renderer.unmount());}
});

for(const historical of [false,true])test(`collection evidence citations and exact source inspection use retained run bibliography (${historical?"historical":"current"})`,async()=>{
  const f=research("evidence-origin-"+historical),calls:{path:string;method:string}[]=[],state={...f.state,current_run_id:historical?null:f.run.id},view={...f.view,current:!historical};
  globalThis.fetch=async(input,options)=>{
    const path=String(input),method=options?.method??"GET";calls.push({path,method});assert.equal(method,"GET","opening and source inspection must not submit a human assessment or regenerate evidence");
    if(path.endsWith("/session"))return response({csrf_token:"software"});
    if(path.includes("/drafts/"))return response({scope:decodeURIComponent(path.split("/").at(-1)!),version:0,data:{},expected_assessment_head:null,updated_at:null});
    if(path.includes("/context?")){const passage=f.run.passages[0],block={id:passage.anchor.block_id,ordinal:1,text:f.quote,locator:passage.locator};const context:Schema<"ContextView">={run_id:f.run.id,passage,paper:f.papers[0],source:f.sources[0],block,blocks:[block],offset:0,total_blocks:1,next_offset:null,archived:historical,current:!historical,offset_convention:"half-open-unicode-codepoints"};return response(context);}
    if(path.endsWith("/runs/"+f.run.id+"/papers"))return response(f.runPapers);
    if(path.endsWith("/runs/"+f.run.id))return response(view);
    throw new Error("Unexpected software-test GET "+path);
  };
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<Evidence workspace={state} requestedRun={f.run.id} refresh={async()=>{}} navigate={async()=>{}}/>);});
  try{
    assert.match(text(renderer.root),/SOFTWARE TEST CITATION 1/);assert.equal(renderer.root.findAllByType("select").filter(item=>["unreviewed"].includes(item.props.value)).length,3);const bundle=renderer.root.findByProps({className:"bundle"});assert.equal(bundle.findAllByType("fieldset")[0].props.disabled,historical);
    await act(async()=>button(renderer,"Inspect source for passage 1 ↓").props.onClick());assert.equal(text(renderer.root.findByType("mark")),f.quote);assert.match(text(renderer.root),/imported_abstract/);assert.equal(calls.some(call=>call.path.includes("/searches/")),false);assert.match(calls.find(call=>call.path.includes("/context?"))!.path,new RegExp("archived="+historical));assert.equal(calls.every(call=>call.method==="GET"),true);
  }finally{await act(async()=>renderer.unmount());}
});
