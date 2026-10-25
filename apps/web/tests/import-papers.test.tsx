import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestRenderer} from "react-test-renderer";
import {ImportInputForm,type CitationInput} from "../components/import-papers.tsx";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const form=(renderer:ReactTestRenderer)=>renderer.root.findByType("form");
const submit=(renderer:ReactTestRenderer)=>form(renderer).props.onSubmit({preventDefault(){}});

test("typing identifiers and selecting a citation file remain local until an explicit parse action",async()=>{
  const parsed:CitationInput[]=[],source="\ufeffTitle,DOI\nSOFTWARE TEST,10.1234/software\n";let reads=0;
  const file={name:"software.csv",size:new TextEncoder().encode(source).length,arrayBuffer:async()=>{reads++;return new TextEncoder().encode(source).buffer;}};
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<ImportInputForm maxBytes={1024} busy={false} onParse={async input=>{parsed.push(input);}}/>);});
  try{
    await act(async()=>renderer.root.findByType("input").props.onChange({target:{files:[file]}}));
    assert.equal(reads,0);assert.equal(parsed.length,0);
    await act(async()=>submit(renderer));
    assert.equal(reads,1);assert.equal(parsed.length,1);assert.equal(new TextDecoder().decode(parsed[0].bytes),source.replace(/^\ufeff/,""));
    assert.equal(parsed[0].bytes[0],0xef,"original UTF-8 BOM bytes are preserved for server parsing");assert.equal(parsed[0].filename,"software.csv");
    await act(async()=>renderer.root.findByType("select").props.onChange({target:{value:"identifiers"}}));
    await act(async()=>renderer.root.findByType("textarea").props.onChange({target:{value:"doi:10.1234/example\nPMID: 12345678"}}));
    assert.equal(parsed.length,1);
    await act(async()=>submit(renderer));
    assert.equal(parsed.length,2);assert.equal(parsed[1].filename,null);assert.equal(new TextDecoder().decode(parsed[1].bytes),"doi:10.1234/example\nPMID: 12345678");
  }finally{await act(async()=>renderer.unmount());}
});

test("empty or oversized citation files are rejected before reading their bytes",async()=>{
  let reads=0,parses=0;let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<ImportInputForm maxBytes={16} busy={false} onParse={async()=>{parses++;}}/>);});
  try{
    for(const size of [0,17]){
      await act(async()=>renderer.root.findByType("input").props.onChange({target:{files:[{name:"software.csv",size,arrayBuffer:async()=>{reads++;return new ArrayBuffer(size);}}]}}));
      await act(async()=>submit(renderer));
      assert.equal(renderer.root.findAllByProps({role:"alert"}).length,1);
    }
    assert.equal(reads,0);assert.equal(parses,0);
    await act(async()=>renderer.root.findByType("select").props.onChange({target:{value:"identifiers"}}));
    await act(async()=>renderer.root.findByType("textarea").props.onChange({target:{value:"界界界界界界"}}));
    await act(async()=>submit(renderer));assert.equal(parses,0,"byte limits account for multibyte input");
  }finally{await act(async()=>renderer.unmount());}
});
