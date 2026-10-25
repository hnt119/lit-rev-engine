import assert from "node:assert/strict";
import test from "node:test";
import {useState} from "react";
import {act,create,type ReactTestRenderer} from "react-test-renderer";
import {applyRawQueryEdit,pasteRawQuery,RawStrategyEditor} from "../components/search-planner";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const original='  ("women’s gut microbiota"[tiab] OR "微生物"[tiab])\r\n AND ("diet"[tiab] NOT "animals"[MeSH Terms])  \r';

test("native normalized textarea updates preserve untouched CRLF, Unicode, whitespace, quotes and Boolean strategy",()=>{
  const displayed=original.replace(/\r\n?/g,"\n");assert.equal(applyRawQueryEdit(original,displayed),original);
  assert.equal(applyRawQueryEdit(original,displayed.replace('"diet"','"dietary pattern"')),original.replace('"diet"','"dietary pattern"'));
  assert.equal(applyRawQueryEdit(original,displayed.slice(2)),original.slice(2));
  assert.equal(applyRawQueryEdit(original,displayed+"\n"),original+"\n");
  const offset=displayed.indexOf("AND");assert.equal(pasteRawQuery(original,"NOT\r\n",offset,offset+3),original.replace("AND","NOT\r\n"));
});

test("pasted specialist strategies retain exact clipboard content without requests or hidden compilation",async()=>{
  let requests=0,retained="";globalThis.fetch=async()=>{requests++;throw new Error("No requests are authorized while editing");};
  function Harness(){const [value,setValue]=useState("");retained=value;return <RawStrategyEditor value={value} onChange={setValue}/>;}
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<Harness/>);});
  try{
    let prevented=false;await act(async()=>renderer.root.findByType("textarea").props.onPaste({clipboardData:{getData:()=>original},currentTarget:{selectionStart:0,selectionEnd:0},preventDefault(){prevented=true;}}));assert.equal(prevented,true);assert.equal(retained,original);assert.equal(requests,0);
    await act(async()=>renderer.root.findByType("textarea").props.onChange({target:{value:original.replace(/\r\n?/g,"\n").replace("微生物","腸道微生物")}}));assert.equal(retained,original.replace("微生物","腸道微生物"));assert.equal(requests,0);
  }finally{await act(async()=>renderer.unmount());}
});
