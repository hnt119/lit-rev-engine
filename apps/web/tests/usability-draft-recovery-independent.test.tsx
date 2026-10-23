import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestRenderer} from "react-test-renderer";
import {flushDrafts,recoverDrafts,useDraft} from "../lib/drafts";
import {response} from "./import-collection-fixtures";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});

test("retry saves the retained incomplete editor draft without compiling or executing it",async()=>{
  const scope="search-plan-editor:new",calls:{path:string;method:string}[]=[];
  let record={scope,version:0,data:{} as Record<string,unknown>,expected_assessment_head:null,updated_at:null};
  let fail=true;
  globalThis.fetch=async(path,options)=>{
    const method=options?.method??"GET";calls.push({path:String(path),method});
    if(String(path).endsWith("/session"))return response({csrf_token:"software"});
    assert.match(String(path),/\/drafts\/search-plan-editor/);
    if(method==="GET")return response(record);
    if(fail)return response({error:{code:"temporary_storage_error",message:"SOFTWARE TEST save unavailable"}},503);
    const body=JSON.parse(String(options?.body));assert.equal(body.version,record.version);
    record={...record,version:record.version+1,data:body.data};return response(record);
  };
  let draft!:ReturnType<typeof useDraft<{label:string;terms:string[]}>>,renderer!:ReactTestRenderer;
  function Harness(){draft=useDraft<{label:string;terms:string[]}>("independent-editor-failed-save",scope,{label:"initial",terms:[]});return null;}
  await act(async()=>{renderer=create(<Harness/>);});
  try{
    await act(async()=>draft.setData({label:"",terms:[]}));
    await act(async()=>{await assert.rejects(draft.save(),/save unavailable/);});
    await assert.rejects(flushDrafts(),/save unavailable/);
    assert.equal(calls.filter(call=>call.method==="PUT").length,1);
    assert.equal(draft.data.label,"");assert.equal(draft.state,"error");
    fail=false;await act(async()=>recoverDrafts("retry"));
    assert.equal(draft.state,"saved");assert.deepEqual(record.data,{label:"",terms:[]});
    assert.equal(calls.filter(call=>call.method==="PUT").length,2);
    assert.equal(calls.some(call=>/compile|propose|execute|searches/.test(call.path)),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("retry never overwrites a newer tab draft and explicit restore recovers that saved version",async()=>{
  const scope="search-plan-editor:new";
  let record={scope,version:0,data:{} as Record<string,unknown>,expected_assessment_head:null,updated_at:null},puts=0;
  globalThis.fetch=async(path,options)=>{
    if(String(path).endsWith("/session"))return response({csrf_token:"software"});
    if((options?.method??"GET")==="GET")return response(record);
    puts++;record={...record,version:2,data:{label:"other tab",terms:["retained"]}};
    return response({error:{code:"stale_draft",message:"SOFTWARE TEST newer draft exists"}},409);
  };
  let draft!:ReturnType<typeof useDraft<{label:string;terms:string[]}>>,renderer!:ReactTestRenderer;
  function Harness(){draft=useDraft<{label:string;terms:string[]}>("independent-editor-conflict",scope,{label:"initial",terms:[]});return null;}
  await act(async()=>{renderer=create(<Harness/>);});
  try{
    await act(async()=>draft.setData({label:"my incomplete label",terms:[]}));
    await act(async()=>{await assert.rejects(draft.save(),/newer draft exists/);});
    await act(async()=>{await assert.rejects(recoverDrafts("retry"),/does not overwrite another tab/);});
    assert.equal(puts,1);assert.equal(draft.data.label,"my incomplete label");assert.equal(draft.state,"conflict");
    await act(async()=>recoverDrafts("restore"));
    assert.equal(puts,1);assert.equal(draft.version,2);assert.equal(draft.state,"saved");
    assert.deepEqual(draft.data,{label:"other tab",terms:["retained"]});
    await flushDrafts();assert.equal(puts,1);
  }finally{await act(async()=>renderer.unmount());}
});

test("retry refreshes a ready clean participant's data before its next edit",async()=>{
  const scope="discover";
  let record={scope,version:1,data:{question:"saved A",query:"query A"},expected_assessment_head:null,updated_at:null},puts=0;
  globalThis.fetch=async(path,options)=>{
    if(String(path).endsWith("/session"))return response({csrf_token:"software"});
    if((options?.method??"GET")==="GET")return response(record);
    puts++;const body=JSON.parse(String(options?.body));assert.equal(body.version,record.version);
    record={...record,version:record.version+1,data:body.data};return response(record);
  };
  let draft!:ReturnType<typeof useDraft<{question:string;query:string}>>,renderer!:ReactTestRenderer;
  function Harness(){draft=useDraft<{question:string;query:string}>("independent-clean-draft-retry",scope,{question:"",query:""});return null;}
  await act(async()=>{renderer=create(<Harness/>);});
  try{
    assert.equal(draft.ready,true);assert.equal(draft.state,"saved");assert.equal(draft.version,1);
    assert.deepEqual(draft.data,{question:"saved A",query:"query A"});
    record={...record,version:2,data:{question:"saved B",query:"query B"}};
    await act(async()=>draft.retry());
    assert.equal(puts,0);assert.equal(draft.version,2);assert.equal(draft.state,"saved");
    assert.deepEqual(draft.data,{question:"saved B",query:"query B"});
    await act(async()=>draft.setData(previous=>({...previous,question:"next edit"})));
    await act(async()=>draft.save());
    assert.equal(puts,1);assert.equal(record.version,3);
    assert.deepEqual(record.data,{question:"next edit",query:"query B"});
  }finally{await act(async()=>renderer.unmount());}
});
