import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Evidence from "../components/evidence";
import {flushDrafts} from "../lib/drafts";
import {research} from "./collection-research-fixtures";
import {response,storage} from "./import-collection-fixtures";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
const field=(renderer:ReactTestRenderer,label:string)=>renderer.root.findAllByType("label").find(node=>node.children[0]===label)!.findAll(node=>node.type==="input"||node.type==="textarea")[0];
async function observed(check:()=>boolean){const deadline=Date.now()+5000;while(!check()){assert.ok(Date.now()<deadline,"expected acknowledged retrieval state was not observed");await act(async()=>{await new Promise<void>(resolve=>setImmediate(resolve));});}}

test("passage counts 5,7,10,20,30 are explicit requests, persist across question edits/reopen, and leave old runs immutable",async()=>{
  const f=research("passage-count"),old=JSON.stringify(f.run),calls:{path:string;method:string;body:any}[]=[];
  let saved={scope:"evidence",version:0,data:{} as Record<string,unknown>,expected_assessment_head:null,updated_at:null};
  Object.assign(globalThis,{sessionStorage:storage()});
  globalThis.fetch=async(input,options)=>{
    const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):null;calls.push({path,method,body});
    if(path.endsWith("/session"))return response({csrf_token:"software"});
    if(path.endsWith("/settings"))return response({preferences:{retrieval:{profile_id:"legacy_block_prefix_v1",device:"cpu"}}});
    if(path.endsWith("/drafts/evidence")){if(method==="PUT"){assert.equal(body.version,saved.version);saved={...saved,...body,version:saved.version+1};}return response(saved);}
    if(path.endsWith("/evidence-runs"))return response({...f.run,id:"new-"+body.top_k,parameters:{top_k:body.top_k,returned_count:3}});
    throw new Error("Unexpected provider or retrieval call "+path);
  };
  let renderer!:ReactTestRenderer;
  const mount=async()=>act(async()=>{renderer=create(<Evidence workspace={f.state} refresh={async()=>{}} navigate={async()=>({status:"success"})}/>);});
  await mount();
  try{
    assert.equal(field(renderer,"Maximum passages for next search").props.value,5);
    for(const count of [5,7,10,20,30]){
      await act(async()=>field(renderer,"Maximum passages for next search").props.onChange({target:{value:String(count)}}));
      await act(async()=>field(renderer,"Evidence question").props.onChange({target:{value:"Question for "+count}}));
      assert.equal(field(renderer,"Maximum passages for next search").props.value,count);
      await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));
      await observed(()=>calls.some(call=>call.path.endsWith("/evidence-runs")&&call.body.top_k===count)&&!renderer.root.findByType("form").findByProps({className:"primary"}).props.disabled);
    }
    assert.deepEqual(calls.filter(call=>call.path.endsWith("/evidence-runs")).map(call=>call.body.top_k),[5,7,10,20,30]);
    assert.equal(JSON.stringify(f.run),old);
    assert.equal(calls.some(call=>/proposal|candidates/.test(call.path)),false);
    await act(async()=>flushDrafts());await act(async()=>renderer.unmount());await mount();
    assert.equal(field(renderer,"Maximum passages for next search").props.value,30);
    assert.equal(field(renderer,"Evidence question").props.value,"Question for 30");
    const before=calls.filter(call=>call.method!=="GET").length;
    await act(async()=>field(renderer,"Maximum passages for next search").props.onChange({target:{value:"31"}}));
    await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));
    assert.equal(calls.filter(call=>call.method!=="GET").length,before,"invalid retrieval count fails before mutation");
    assert.match(text(renderer.root),/Choose a whole number from 5 to 30/);
  }finally{await act(async()=>renderer.unmount());}
});
