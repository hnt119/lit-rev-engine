import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Discover from "../components/discover.tsx";
import type {Schema} from "../lib/api.ts";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});

const question="SOFTWARE TEST: gut microbiota and ovarian ageing in women from Southeast Asia";
const existingQuery=Array.from({length:120},(_,index)=>`"SOFTWARE TEST TERM ${index}"[Title/Abstract]`).join(" OR ");
const candidate='("gut microbiome"[Title/Abstract] OR "gut microbiota"[Title/Abstract]) AND women[Title/Abstract]';
const explanation="SOFTWARE TEST EXPLANATION: editable concept groups require human review; this proposal makes no search call.";
type Request={path:string;method:string;body:Record<string,unknown>|null};

function labelTextarea(renderer:ReactTestRenderer,label:string):ReactTestInstance {
  const match=renderer.root.findAllByType("label").find(node=>node.children.some(child=>typeof child==="string"&&child===label));
  assert.ok(match,`Missing textarea label ${label}`);
  return match.findByType("textarea");
}
function button(renderer:ReactTestRenderer,label:string):ReactTestInstance {
  const match=renderer.root.findAllByType("button").find(node=>node.children.join("")===label);
  assert.ok(match,`Missing button ${label}`);return match;
}
function proposal(renderer:ReactTestRenderer) {
  return renderer.root.findAll(node=>node.props.role==="region"&&node.props["aria-label"]==="Proposed query");
}

async function fixture(workspaceId:string,{delayed=false,proposedQuery=candidate,proposedExplanation=explanation}={}) {
  const workspace={id:workspaceId,question,mode:"live",created_at:"2026-10-21T00:00:00Z",source_revision:0,current_preparation_id:null,selected_paper_ids:[],current_run_id:null,current_assessment_ids:{},searches:[],preparations:[],runs:[],assessments:[]} as Schema<"WorkspaceSummary">;
  const capabilities={default_mode:"saved_example",live_available:true,saved_example:{question:"SOFTWARE TEST SAVED QUESTION",query:"SOFTWARE TEST SAVED QUERY"},limits:{},boards:{max_fields:6,max_cells:60,max_boards:10,max_definition_revisions:20,max_cell_revisions:50,max_references:5,max_workspace_bytes:33554432,max_candidate_characters:1200,max_inspector_characters:4000},map:{ready:false,reason:"No map needed for query proposal tests"}} as Schema<"Capabilities">;
  const requests:Request[]=[];
  let draftVersion=1;
  let retained={question,query:existingQuery,sort:"relevance",max_results:30,use_dates:false,date_from:"",date_to:""};
  let resolveProposal:(()=>void)|undefined;
  const pending=new Promise<void>(resolve=>{resolveProposal=resolve;});
  globalThis.fetch=async(url,options)=>{
    const path=String(url),method=options?.method??"GET";
    const body=typeof options?.body==="string"?JSON.parse(options.body):null;
    requests.push({path,method,body});
    let value:unknown;
    if(path.endsWith("/session"))value={csrf_token:"software-test"};
    else if(path.endsWith("/query-suggestions")){
      assert.equal(method,"POST");assert.deepEqual(body,{question});
      if(delayed)await pending;
      value={query:proposedQuery,explanation:proposedExplanation,method:"transparent-template-v1"};
    }else if(path.endsWith("/drafts/discover")){
      if(method==="PUT"){assert.equal(body.version,draftVersion);draftVersion++;retained=body.data;}
      else assert.equal(method,"GET");
      value={scope:"discover",version:draftVersion,data:retained,expected_assessment_head:null,updated_at:null};
    }else assert.fail(`Unexpected request: ${method} ${path}`);
    return new Response(JSON.stringify(value),{headers:{"Content-Type":"application/json"}});
  };
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<Discover workspace={workspace} capabilities={capabilities} refresh={async()=>assert.fail("proposal must not refresh research state")} navigate={async()=>assert.fail("proposal must not navigate")}/>);});
  assert.equal(labelTextarea(renderer,"PubMed query").props.value,existingQuery,"real persisted draft restores before proposing");
  return {renderer,requests,resolveProposal:resolveProposal!};
}

test("proposed query previews its explanation without overwriting a long persisted strategy or searching",async()=>{
  const {renderer,requests}=await fixture("software-query-preview-apply");
  try{
    await act(async()=>button(renderer,"Propose editable query").props.onClick());
    assert.equal(labelTextarea(renderer,"PubMed query").props.value,existingQuery);
    assert.equal(proposal(renderer).length,1);
    assert.equal(labelTextarea(renderer,"Proposed PubMed query").props.value,candidate);
    assert.equal(labelTextarea(renderer,"Proposed PubMed query").props.readOnly,true);
    assert.ok(JSON.stringify(renderer.toJSON()).includes(explanation),"returned explanation is visible");
    assert.equal(requests.filter(request=>request.method==="POST").length,1,"only query proposal endpoint was called");
    assert.equal(requests.some(request=>request.path.endsWith("/searches")),false);
    await act(async()=>button(renderer,"Use proposed query").props.onClick());
    assert.equal(labelTextarea(renderer,"PubMed query").props.value,candidate,"explicit apply copies the exact proposed query");
    assert.equal(labelTextarea(renderer,"Research question").props.value,question);
    assert.equal(proposal(renderer).length,0);
    assert.equal(requests.some(request=>request.path.endsWith("/searches")),false,"applying a query does not run it");
  }finally{await act(async()=>renderer.unmount());}
});

test("dismissing or editing either input clears a proposal without altering the existing strategy",async()=>{
  const {renderer,requests}=await fixture("software-query-dismiss-edit");
  try{
    await act(async()=>button(renderer,"Propose editable query").props.onClick());
    await act(async()=>button(renderer,"Dismiss proposal").props.onClick());
    assert.equal(proposal(renderer).length,0);
    assert.equal(labelTextarea(renderer,"PubMed query").props.value,existingQuery);
    await act(async()=>button(renderer,"Propose editable query").props.onClick());
    await act(async()=>labelTextarea(renderer,"PubMed query").props.onChange({target:{value:existingQuery+" OR manual"}}));
    assert.equal(proposal(renderer).length,0);
    assert.equal(labelTextarea(renderer,"PubMed query").props.value,existingQuery+" OR manual");
    await act(async()=>button(renderer,"Propose editable query").props.onClick());
    await act(async()=>labelTextarea(renderer,"Research question").props.onChange({target:{value:question+" edited"}}));
    assert.equal(proposal(renderer).length,0);
    assert.equal(labelTextarea(renderer,"Research question").props.value,question+" edited");
    assert.equal(labelTextarea(renderer,"PubMed query").props.value,existingQuery+" OR manual");
    assert.equal(requests.some(request=>request.path.endsWith("/searches")),false);
  }finally{await act(async()=>renderer.unmount());}
});

for(const field of ["Research question","PubMed query"])test(`an in-flight proposal cannot resurrect after editing ${field}`,async()=>{
  const {renderer,requests,resolveProposal}=await fixture(`software-query-race-${field}`,{delayed:true});
  try{
    await act(async()=>{button(renderer,"Propose editable query").props.onClick();});
    const original=field==="Research question"?question:existingQuery;
    await act(async()=>labelTextarea(renderer,field).props.onChange({target:{value:original+" edited during request"}}));
    await act(async()=>{resolveProposal();});
    assert.equal(proposal(renderer).length,0,"late response is stale after a manual edit");
    assert.equal(labelTextarea(renderer,field).props.value,original+" edited during request");
    assert.equal(labelTextarea(renderer,field==="Research question"?"PubMed query":"Research question").props.value,field==="Research question"?existingQuery:question);
    assert.equal(requests.some(request=>request.path.endsWith("/searches")),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("editing and reverting the query still invalidates an in-flight proposal",async()=>{
  const {renderer,resolveProposal}=await fixture("software-query-edit-revert-race",{delayed:true});
  try{
    await act(async()=>{button(renderer,"Propose editable query").props.onClick();});
    await act(async()=>labelTextarea(renderer,"PubMed query").props.onChange({target:{value:existingQuery+" manual edit"}}));
    await act(async()=>labelTextarea(renderer,"PubMed query").props.onChange({target:{value:existingQuery}}));
    await act(async()=>{resolveProposal();});
    assert.equal(proposal(renderer).length,0,"an edit invalidates a pending response even if the original text is restored");
    assert.equal(labelTextarea(renderer,"PubMed query").props.value,existingQuery);
  }finally{await act(async()=>renderer.unmount());}
});

test("an insufficient-concepts proposal cannot replace the retained query or start a search",async()=>{
  const insufficient="No research concepts found. Add a topic, population, exposure or outcome.";
  const {renderer,requests}=await fixture("software-query-empty",{proposedQuery:"",proposedExplanation:insufficient});
  try{
    await act(async()=>button(renderer,"Propose editable query").props.onClick());
    assert.equal(proposal(renderer).length,1);
    assert.ok(JSON.stringify(renderer.toJSON()).includes(insufficient));
    assert.equal(button(renderer,"Use proposed query").props.disabled,true);
    await act(async()=>button(renderer,"Use proposed query").props.onClick());
    assert.equal(labelTextarea(renderer,"PubMed query").props.value,existingQuery);
    assert.equal(proposal(renderer).length,1);
    assert.equal(requests.some(request=>request.path.endsWith("/searches")),false);
  }finally{await act(async()=>renderer.unmount());}
});
