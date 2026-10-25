import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestRenderer} from "react-test-renderer";
import {useEffect} from "react";
import AdmissionGate from "../components/admission-gate.tsx";
import {registerDraftFlusher} from "../lib/drafts.tsx";
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});

test("hosted admission requests no research session before explicit successful admission",async()=>{
  const original=globalThis.fetch,calls:string[]=[];let renderer!:ReactTestRenderer;
  globalThis.fetch=async(input,init)=>{calls.push(String(input));assert.equal(String(input),init?.method==="POST"?"/api/v1/admission/login":"/api/v1/admission/status");return Response.json(init?.method==="POST"?{admitted:false}:{mode:"hosted",admitted:false},{status:init?.method==="POST"?403:200});};
  try{
    await act(async()=>{renderer=create(<AdmissionGate><p>Research view</p></AdmissionGate>);});assert.deepEqual(calls,["/api/v1/admission/status"]);
    await act(async()=>renderer.root.findByType("input").props.onChange({target:{value:"software-test-code"}}));
    await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));
    assert.equal(renderer.root.findByType("input").props.value,"");assert.match(renderer.root.findByProps({role:"status"}).children.join(""),/not granted/);
    assert.equal(calls.includes("/api/v1/session"),false);
  }finally{await act(async()=>renderer?.unmount());globalThis.fetch=original;}
});
test("renewal retains the mounted research view and ending admission waits for draft acknowledgement",async()=>{
  const original=globalThis.fetch;let renderer!:ReactTestRenderer,mounts=0,unmounts=0,logouts=0,dirtyFailure=true;
  function ResearchView(){useEffect(()=>{mounts++;return()=>{unmounts++;};},[]);return <p>Retained research editor</p>;}
  const unregister=registerDraftFlusher(async()=>{if(dirtyFailure)throw new Error("Save blocked; retained edits remain.");});
  globalThis.fetch=async(input)=>{
    if(String(input).endsWith("/logout")){logouts++;return Response.json({mode:"hosted",admitted:false});}
    return Response.json({mode:"hosted",admitted:true});
  };
  const click=async(text:string)=>act(async()=>renderer.root.findAllByType("button").find(button=>button.children.join("")===text)!.props.onClick());
  try{
    await act(async()=>{renderer=create(<AdmissionGate><ResearchView/></AdmissionGate>);});assert.equal(mounts,1);
    await click("Renew beta access");
    await act(async()=>renderer.root.findByType("input").props.onChange({target:{value:"software-test-code"}}));
    await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));
    assert.equal(mounts,1);assert.equal(unmounts,0,"renewing expired admission does not discard local editor state");
    await click("End beta admission");assert.equal(logouts,0);assert.equal(unmounts,0);assert.match(renderer.root.findByProps({role:"status"}).children.join(""),/Save blocked/);
    dirtyFailure=false;await click("End beta admission");assert.equal(logouts,1);assert.equal(unmounts,1);
  }finally{unregister();await act(async()=>renderer?.unmount());globalThis.fetch=original;}
});
