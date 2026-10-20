import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestRenderer} from "react-test-renderer";
import {flushDrafts,navigationBarrier,useDraft} from "../lib/drafts.tsx";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}});

test("delayed draft flush drains the latest edit once before route unmount and restores on reopen",async()=>{
  let record={scope:"discover",version:0,data:{} as Record<string,unknown>,expected_assessment_head:null,updated_at:null};
  let release:()=>void=()=>{};const gate=new Promise<void>(resolve=>release=resolve);let puts=0;
  globalThis.fetch=async(url,options)=>{
    if(String(url).endsWith("/session"))return response({csrf_token:"test"});
    if(!options?.method||options.method==="GET")return response(record);
    const body=JSON.parse(String(options.body));puts++;if(puts===1)await gate;
    assert.equal(body.version,record.version);
    record={...record,version:record.version+1,data:body.data};return response(record);
  };
  let current!:ReturnType<typeof useDraft<{question:string;query:string}>>;let renderer!:ReactTestRenderer;
  function Harness(){current=useDraft("race-workspace","discover",{question:"initial",query:""});return null;}
  await act(async()=>{renderer=create(<Harness/>);});assert.equal(current.ready,true);
  await act(async()=>current.setData({question:"first",query:"first query"}));
  let saving!:Promise<void>;act(()=>{saving=current.save();});
  await act(async()=>current.setData({question:"latest",query:"latest query"}));
  let flushing!:Promise<void>;act(()=>{flushing=flushDrafts();});
  await act(async()=>{release();await Promise.all([saving,flushing]);});
  assert.equal(puts,2);assert.deepEqual(record.data,{question:"latest",query:"latest query"});assert.equal(current.state,"saved");
  await act(async()=>renderer.unmount());
  await act(async()=>{renderer=create(<Harness/>);});assert.equal(current.data.question,"latest");assert.equal(current.data.query,"latest query");await act(async()=>renderer.unmount());
});

test("409 conflict retains edits, blocks navigation flush and does not automatically retry",async()=>{
  let puts=0;let forceConflict=true;
  let record={scope:"discover",version:0,data:{} as Record<string,unknown>,expected_assessment_head:null,updated_at:null};
  globalThis.fetch=async(_url,options)=>{
    if(!options?.method||options.method==="GET")return response(record);
    puts++;const body=JSON.parse(String(options.body));
    if(forceConflict){record={...record,version:1,data:{question:"other tab"}};return response({detail:{code:"draft_conflict",message:"Newer draft exists"}},409);}
    assert.equal(body.version,record.version);record={...record,version:record.version+1,data:body.data};return response(record);
  };
  let current!:ReturnType<typeof useDraft<{question:string}>>;let renderer!:ReactTestRenderer;
  function Harness(){current=useDraft("conflict-workspace","discover",{question:""});return null;}
  await act(async()=>{renderer=create(<Harness/>);});
  await act(async()=>current.setData({question:"my notes"}));
  await act(async()=>{await assert.rejects(current.save(),/Newer draft/);});
  assert.equal(current.state,"conflict");assert.equal(current.data.question,"my notes");
  await act(async()=>current.setData({question:"my notes extended"}));
  await assert.rejects(flushDrafts(),/Newer draft/);assert.equal(puts,1);
  forceConflict=false;await act(async()=>current.retry());assert.equal(current.state,"saved");assert.equal(record.data.question,"my notes extended");
  await act(async()=>renderer.unmount());
});

test("a null original assessment head is never rebound to a newer saved assessment",async()=>{
  const record={scope:"assessment:r",version:2,data:{notes:"old uncommitted draft"},expected_assessment_head:null,updated_at:null};let puts=0;
  globalThis.fetch=async(_url,options)=>{if(options?.method==="PUT")puts++;return response(record);};
  let current!:ReturnType<typeof useDraft<{notes:string}>>;let renderer!:ReactTestRenderer;
  function Harness(){current=useDraft("stale-head-workspace","assessment:r",{notes:"latest assessment"},"assessment-new");return null;}
  await act(async()=>{renderer=create(<Harness/>);});
  assert.equal(current.data.notes,"old uncommitted draft");assert.equal(current.state,"conflict");await assert.rejects(current.save(),/older assessment head/);assert.equal(puts,0);
  await act(async()=>renderer.unmount());
});

test("acknowledged assessment revision persists its new baseline before immediate navigation and reopen",async()=>{
  let head="assessment-1";
  let record={scope:"assessment:r",version:1,data:{notes:"first judgment",editing:false},expected_assessment_head:head,updated_at:null};
  globalThis.fetch=async(_url,options)=>{
    if(!options?.method||options.method==="GET")return response(record);
    const body=JSON.parse(String(options.body));assert.equal(body.version,record.version);assert.equal(body.expected_assessment_head,head);
    record={...record,version:record.version+1,data:body.data,expected_assessment_head:body.expected_assessment_head};return response(record);
  };
  let current!:ReturnType<typeof useDraft<{notes:string;editing:boolean}>>;let renderer!:ReactTestRenderer;
  function Harness(){current=useDraft<{notes:string;editing:boolean}>("assessment-commit-workspace","assessment:r",{notes:"first judgment",editing:false},head);return null;}
  await act(async()=>{renderer=create(<Harness/>);});
  await act(async()=>current.setData({notes:"second judgment",editing:true}));
  let finishMutation:()=>void=()=>{};const mutationGate=new Promise<void>(resolve=>finishMutation=resolve);
  let completing!:Promise<void>;
  act(()=>{completing=navigationBarrier(async()=>{
    await current.save();await mutationGate;
    head="assessment-2";
    current.replace({notes:"second judgment",editing:false},head);
    await current.save();
  });});
  let navigationFinished=false;
  const navigating=flushDrafts().then(()=>{navigationFinished=true;});
  await act(async()=>{await Promise.resolve();});assert.equal(navigationFinished,false);
  await act(async()=>{finishMutation();await Promise.all([completing,navigating]);});
  assert.equal(record.expected_assessment_head,"assessment-2");assert.equal(record.data.editing,false);
  await act(async()=>renderer.unmount());
  await act(async()=>{renderer=create(<Harness/>);});
  assert.equal(current.state,"saved");assert.equal(current.data.notes,"second judgment");assert.equal(current.data.editing,false);
  await act(async()=>renderer.unmount());
});
