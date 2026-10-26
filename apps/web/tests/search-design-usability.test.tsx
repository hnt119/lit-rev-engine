import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import SearchConceptCards,{conceptGroup} from "../components/search-concept-cards";
import SearchDiagnosticSummary from "../components/search-diagnostic-summary";
import SearchDesignNotes from "../components/search-design-notes";
import {checkedDesignNotes,type DesignNotesView} from "../lib/search-design";
import {draft,diagnostic,saved,response,stamp} from "./search-planner-fixtures";
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,window:{confirm:()=>true}});
const text=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(text).join("");
const button=(r:ReactTestRenderer,name:string)=>r.root.findAllByType("button").find(n=>text(n)===name)!;
const field=(r:ReactTestRenderer,name:string)=>r.root.findAllByType("label").find(n=>text(n).startsWith(name))!.findAll(n=>["input","textarea","select"].includes(String(n.type)))[0];
const metadata=(plan="notes-plan",revision="notes-revision",version=2):DesignNotesView=>({schema_version:"mvp.search-plan-metadata.v1",plan_id:plan,revision_id:revision,version,latest_version:2,current:true,metadata:{extraction_questions:[],term_notes:[],external_searches:[]},term_bindings:[],history:[{version:2,saved_at:stamp},{version:1,saved_at:stamp}],saved_at:stamp,terminology_verification:"unavailable"});

test("manual cards separate roles and retain broad question, negation and provenance without AI calls",async()=>{
  let value=draft();value.original_question="Across mixed populations, how do unfamiliar symbionts affect ageing, excluding neither sex by assumption?";value.concepts[0].terms[0].origin="model_proposed";
  let r!:ReactTestRenderer;const render=()=> <SearchConceptCards draft={value} onEdit={update=>{value=update(value);r.update(render());}} disabled={false} maxConcepts={12} maxTerms={8}/>;
  await act(async()=>{r=create(render());});try{
    for(const group of ["Search concepts","Eligibility to check later","Preferences and notes","Needs clarification"])assert.ok(r.root.findByProps({"aria-label":group}));
    await act(async()=>field(r,"Search term 1").props.onChange({target:{value:"unfamiliar symbiont"}}));
    assert.equal(value.concepts[0].terms[0].state,"proposed");assert.equal(value.concepts[0].terms[0].origin,"manual");assert.match(value.concepts[0].terms[0].provenance_note,/model_proposed/);
    await act(async()=>field(r,"When to use this concept").props.onChange({target:{value:"screen_later"}}));assert.equal(conceptGroup(value.concepts[0]),"Eligibility to check later");
    await act(async()=>button(r,"Add search concept").props.onClick());
    assert.equal(value.original_question,"Across mixed populations, how do unfamiliar symbionts affect ageing, excluding neither sex by assumption?");assert.equal(value.concepts[1].role,"unresolved");assert.equal(value.concepts[1].terms[0].text,"");assert.equal(value.variants[0].expression.concept_id,"lichen");
    assert.doesNotMatch(JSON.stringify(value),/gut|exposome|diet/);
  }finally{await act(async()=>r.unmount());}
});

test("compact diagnostic distinguishes missing, zero, provider error and preview membership",async()=>{
  let r!:ReactTestRenderer;await act(async()=>{r=create(<SearchDiagnosticSummary ready={true}/>);});try{
    assert.match(text(r.root),/Not run/);assert.match(text(r.root),/Unavailable/);
    const receipt=diagnostic(saved()).receipt;receipt.reported_count=0;
    await act(async()=>r.update(<SearchDiagnosticSummary ready={true} receipt={receipt}/>));assert.match(text(r.root),/Provider error/);assert.match(text(r.root),/0 in an unsuccessful response/);
    receipt.status="succeeded";receipt.error=null;receipt.messages=[];receipt.seed_results=[{seed:{id:"known",pmid:"123",doi:null,purpose:"held_out",approved:true},query_membership:"matched",preview_recovery:"absent",reason:"Matching PMID is outside the capped preview"}];
    await act(async()=>r.update(<SearchDiagnosticSummary ready={true} receipt={receipt}/>));
    assert.match(text(r.root),/Succeeded/);assert.match(text(r.root),/PMID 123/);assert.match(text(r.root),/matched/);assert.match(text(r.root),/absent/);assert.doesNotMatch(text(r.root),/unsuccessful response/);
    assert.match(text(r.root),/do not measure relevance/);
  }finally{await act(async()=>r.unmount());}
});

test("metadata responses require the exact saved plan and revision",()=>{
  assert.equal(checkedDesignNotes(metadata(),"notes-plan","notes-revision").version,2);
  for(const value of [{},metadata("other"),metadata("notes-plan","wrong"),{...metadata(),latest_version:1}])assert.throws(()=>checkedDesignNotes(value,"notes-plan","notes-revision"));
});

test("history switching waits for incomplete-note draft save before replacing its editor",async()=>{
  const calls:string[]=[],workspace="software-history-notes",record=metadata();let draftVersion=0,stored:Record<string,unknown>={},release:()=>void=()=>{};
  const gate=new Promise<void>(resolve=>{release=resolve;});
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET";calls.push(method+" "+path);
    if(path.endsWith("/session"))return response({csrf_token:"test-only"});
    if(path.includes("/drafts/")){if(method==="PUT"){await gate;const body=JSON.parse(String(options!.body));stored=body.data;draftVersion++;return response({scope:"test",version:draftVersion,data:stored,expected_assessment_head:"2",updated_at:stamp});}return response({scope:"test",version:draftVersion,data:stored,expected_assessment_head:draftVersion?"2":null,updated_at:null});}
    if(path.endsWith("/collections"))return response({collections:[]});
    if(path.includes("/metadata"))return response(path.includes("version=1")?{...record,version:1}:record);
    throw Error("Unexpected fixture request");};
  let r!:ReactTestRenderer;await act(async()=>{r=create(<SearchDesignNotes workspace={workspace} plan={record.plan_id} revision={record.revision_id} disabled={false} terms={[]}/>);});try{
    await act(async()=>button(r,"Add later extraction question").props.onClick());
    let navigation!:Promise<void>;await act(async()=>{navigation=field(r,"Design-note history").props.onChange({target:{value:"1"}});await Promise.resolve();});
    assert.equal(calls.filter(v=>v.includes("version=1")).length,0);assert.ok(field(r,"Later extraction question 1"));
    await act(async()=>{release();await navigation;await new Promise(resolve=>setTimeout(resolve,0));});
    assert.ok(calls.some(v=>v.includes("version=1")));assert.match(text(r.root),/Historical design notes/);assert.equal((stored as any).metadata.extraction_questions[0].question,"");
  }finally{release();await act(async()=>r.unmount());}
});
