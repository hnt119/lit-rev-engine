import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import InvestigationNavigator,{type InvestigationContext} from "../components/investigation-navigator.tsx";
import {allowedRoute,allowedQuery} from "../lib/bridge.ts";
import {emptyCell} from "../lib/board-drafts.tsx";
import {unresolvedCell,unresolvedInvestigationDraft} from "../lib/investigations.ts";
import type {Schema} from "../lib/api.ts";
import {saved,draft,approval,capability,response,stamp} from "./search-planner-fixtures.ts";

const storage=new Map<string,string>();
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,sessionStorage:{getItem:(key:string)=>storage.get(key)??null,setItem:(key:string,value:string)=>storage.set(key,value),removeItem:(key:string)=>storage.delete(key)}});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
function button(renderer:ReactTestRenderer,label:string){const found=renderer.root.findAllByType("button").find(item=>text(item)===label);assert.ok(found,`Missing button ${label}`);return found;}
function control(renderer:ReactTestRenderer,label:string,type:"textarea"|"input"|"select"="textarea"){const found=renderer.root.findAllByType("label").find(item=>item.children.some(child=>child===label));assert.ok(found,`Missing control ${label}`);return found.findByType(type);}
function checkbox(renderer:ReactTestRenderer,label:string){const found=renderer.root.findAllByType("label").find(item=>text(item).includes(label));assert.ok(found,label);return found.findByType("input");}
const query="lichen[Title/Abstract] AND pigment[Title/Abstract]";
function fixture(id:string,live=true){
  const plan=saved({...draft(),input_mode:"manual_strategy",manual_strategy:query,concepts:[],variants:[]});plan.revision.workspace_id=id;plan.revision.plan_id="plan-"+id;
  const data={...emptyCell(),value:"Original draft note",reason:"Partial abstract context"};
  const board={board_id:"board",revision_id:"revision",workspace_id:id,fields:[{id:"field",label:"Population",subquestion:"What population was studied?"}],papers:[{id:"paper",title:"Original retained report"}],sources:[]} as unknown as Schema<"BoardView">["definition"];
  const origin={schema_version:"mvp.investigation-origin.v1",id:"investigation",workspace_id:id,board,paper_id:"paper",field_id:"field",cell:null,draft:{version:2,data},local_draft:data,reason:"Investigate reports describing the missing population",plan_id:plan.revision.plan_id,created_at:stamp,seed_plan_id:null,seed_revision_id:null,seed_approval_ids:[],meaning:"unresolved_cell_not_proof_of_research_gap"} as unknown as Schema<"InvestigationOrigin">;
  const caps=capability();caps.execution_enabled=live;caps.diagnostics_enabled=live;caps.execution_reason=live?"Explicit live search":"Saved examples cannot execute PubMed queries.";caps.diagnostics_reason=caps.execution_reason;
  const view:Schema<"InvestigationView">={schema_version:"mvp.investigation.v1",origin,plan,capabilities:caps,executions:[],decisions:[],failures:[]};
  const context:InvestigationContext={board_id:"board",expected_board_revision_id:"revision",paper_id:"paper",field_id:"field",expected_cell_head_id:null,expected_draft_version:2,local_draft:data};
  return {view,context};
}
type Call={path:string;method:string;body:any};
async function mount(id:string,{live=true,existing=true,handler}:{live?:boolean;existing?:boolean;handler?:(call:Call,state:{view:Schema<"InvestigationView">})=>Response|Promise<Response>}={}){
  const f=fixture(id,live),state={view:f.view},calls:Call[]=[],drafts=new Map<string,any>();let returned:Schema<"InvestigationOrigin">|undefined;
  globalThis.fetch=async(input,init)=>{
    const call={path:decodeURIComponent(String(input)),method:init?.method??"GET",body:init?.body?JSON.parse(String(init.body)):undefined};calls.push(call);
    if(call.path.endsWith("/session"))return response({csrf_token:"test"});
    if(call.path.includes("/drafts/")){
      assert.ok(call.path.includes("/drafts/search-plan-editor:"),"Only the existing validated draft scope is used");
      const old=drafts.get(call.path)??{version:0,data:{},expected_assessment_head:null};
      if(call.method==="GET")return response(old);
      assert.equal(call.body.version,old.version);assert.equal(call.body.data.plan_id,state.view.origin.plan_id);
      const next={...call.body,version:old.version+1};drafts.set(call.path,next);return response(next);
    }
    if(call.path.includes("/investigations?"))return response({investigations:existing?[state.view.origin]:[]});
    if(call.path.endsWith("/investigations/investigation")&&call.method==="GET")return response(state.view);
    if(call.path.endsWith("/investigations")&&call.method==="POST"){state.view.origin={...state.view.origin,reason:call.body.reason,local_draft:call.body.local_draft};return response(state.view);}
    if(handler)return handler(call,state);
    throw new Error("Unexpected request "+call.method+" "+call.path);
  };
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<InvestigationNavigator workspaceId={id} context={f.context} canCreate onReturn={async origin=>{returned=origin;}}/>);});
  return {renderer,calls,state,context:f.context,drafts,returned:()=>returned};
}
async function open(renderer:ReactTestRenderer){await act(async()=>button(renderer,"Reopen investigation").props.onClick());}
async function approve(renderer:ReactTestRenderer){
  await act(async()=>checkbox(renderer,"Acknowledge that this specialist strategy is unparsed").props.onChange({target:{checked:true}}));
  await act(async()=>checkbox(renderer,"I reviewed this exact query").props.onChange({target:{checked:true}}));
  await act(async()=>button(renderer,"Approve exact investigation query").props.onClick());
}

test("investigation bridge exposes only bounded owned methods and filters",()=>{
  const base="workspaces/w/investigations";
  for(const [method,path] of [["GET",base],["POST",base],["GET",base+"/i"],["PUT",base+"/i/plan"],["POST",base+"/i/approve"],["POST",base+"/i/execute"],["POST",base+"/i/diagnose"],["POST",base+"/i/decisions"],["GET",base+"/i/export"],["GET",base+"/i/research"],...["handoff-preview","handoffs","inspections","notes"].map(suffix=>["POST",base+"/i/"+suffix])])assert.equal(allowedRoute(method,path),true,path);
  for(const suffix of ["handoffs","inspections","notes"]){assert.equal(allowedRoute("DELETE",base+"/i/"+suffix),false);assert.equal(allowedQuery(base+"/i/"+suffix,new URLSearchParams("workspace_id=other"),"POST"),false);}
  assert.equal(allowedRoute("POST","workspaces/w/search-plan-suggestions"),true);
  assert.equal(allowedRoute("GET","workspaces/w/search-plan-suggestions"),false);
  for(const suffix of ["propose","prepare-generation","add-to-board","sources","delete"])assert.equal(allowedRoute("POST",base+"/i/"+suffix),false);
  assert.equal(allowedQuery(base,new URLSearchParams("board_id=b&paper_id=p&field_id=f")),true);
  for(const query of ["board_id=b&board_id=other","paper_id=","token=secret"])assert.equal(allowedQuery(base,new URLSearchParams(query)),false);
  assert.equal(allowedQuery(base+"/i/export",new URLSearchParams("workspace_id=other")),false);
  assert.equal(allowedQuery(base+"/i/execute",new URLSearchParams("approval_id=a"),"POST"),false);
});

test("local investigation drafts use the backend's meaningful unresolved condition",()=>{
  assert.equal(unresolvedInvestigationDraft(null),false);
  for(const data of [emptyCell(),{...emptyCell(),value:"  ",reason:"\n",missing_information:" "},{...emptyCell(),semantic_assessment:"partial" as const}])assert.equal(unresolvedInvestigationDraft(data),false,"Empty draft state alone is not a new unresolved assessment");
  const supported={...emptyCell(),value:"Supported answer",reason:"Inspected source",semantic_assessment:"human_supported" as const,scope_result:"value_found" as const};
  assert.equal(unresolvedInvestigationDraft(supported),false);
  assert.equal(unresolvedInvestigationDraft({...supported,missing_information:"  "}),false);
  for(const changes of [{semantic_assessment:"partial" as const},{semantic_assessment:"unsupported" as const},{scope_result:"not_found_in_inspected_material" as const},{value:null},{missing_information:"Unresolved subgroup"}])assert.equal(unresolvedInvestigationDraft({...supported,...changes}),true);
  assert.equal(unresolvedInvestigationDraft({...emptyCell(),reason:"Need more context"}),true);
  const reference={source_id:"source",source_version:"v1",source_sha256:"a".repeat(64),blocks_sha256:"b".repeat(64),block_id:"block",start:0,end:1};
  assert.equal(unresolvedInvestigationDraft({...emptyCell(),references:[reference]}),true);
  assert.equal(unresolvedInvestigationDraft({...emptyCell(),inspected_ranges:[reference]}),true);
});

test("create captures the original draft without any comparison, source or provider mutation",async()=>{
  const f=await mount("investigation-create",{existing:false}),before=JSON.stringify(f.context);
  try{
    assert.equal(f.calls.some(call=>call.method!=="GET"),false);
    await act(async()=>control(f.renderer,"Reason for investigating").props.onChange({target:{value:"Researcher-authored reason"}}));
    assert.equal(f.calls.some(call=>call.method!=="GET"),false);
    await act(async()=>button(f.renderer,"Create investigation draft").props.onClick());
    const request=f.calls.find(call=>call.method==="POST")!;
    assert.deepEqual({...request.body,request_id:undefined},{...f.context,reason:"Researcher-authored reason",request_id:undefined});
    assert.equal(JSON.stringify(f.context),before);
    assert.match(text(f.renderer.root),/SAVED PLAN REVISION 1/);
    assert.equal(f.calls.some(call=>/\/boards\/|\/source-preparations|\/execute|\/diagnose/.test(call.path)),false);
    await act(async()=>button(f.renderer,"Return to original cell").props.onClick());assert.equal(f.returned()?.board.revision_id,"revision");
  }finally{await act(async()=>f.renderer.unmount());}
});

test("query edits invalidate execution locally, a new saved revision needs approval, and stale saves preserve edits",async()=>{
  let stale=false;
  const f=await mount("investigation-approval",{handler:(call,state)=>{
    if(call.path.endsWith("/approve")){state.view={...state.view,plan:{...state.view.plan,approvals:[approval(state.view.plan)]}};return response(state.view);}
    if(call.path.endsWith("/plan")){
      if(stale)return response({detail:{code:"stale_search_plan",message:"A newer saved plan exists"}},409);
      const next=saved(call.body.draft,2);next.revision.workspace_id=state.view.origin.workspace_id;next.revision.plan_id=state.view.origin.plan_id;state.view={...state.view,plan:next};return response(state.view);
    }
    throw new Error("Unexpected "+call.path);
  }});
  try{
    await open(f.renderer);assert.equal(button(f.renderer,"Run approved PubMed search").props.disabled,true);await approve(f.renderer);assert.equal(button(f.renderer,"Run approved PubMed search").props.disabled,false);
    await act(async()=>control(f.renderer,"Specialist PubMed strategy").props.onChange({target:{value:query+" AND population"}}));assert.equal(button(f.renderer,"Run approved PubMed search").props.disabled,true);
    await act(async()=>button(f.renderer,"Save revised investigation plan").props.onClick());assert.match(text(f.renderer.root),/SAVED PLAN REVISION 2/);assert.equal(button(f.renderer,"Run approved PubMed search").props.disabled,true);
    const put=f.calls.find(call=>call.path.endsWith("/plan"))!;assert.equal(put.body.expected_revision_id,"software-revision-1");
    await act(async()=>control(f.renderer,"Specialist PubMed strategy").props.onChange({target:{value:"LOCAL EDIT SURVIVES CONFLICT"}}));stale=true;await act(async()=>button(f.renderer,"Save revised investigation plan").props.onClick());
    assert.equal(control(f.renderer,"Specialist PubMed strategy").props.value,"LOCAL EDIT SURVIVES CONFLICT");assert.match(text(f.renderer.root),/A newer saved plan exists/);assert.equal(f.calls.some(call=>call.path.endsWith("/execute")),false);
  }finally{await act(async()=>f.renderer.unmount());}
});

test("saved examples reopen, approve and export without making a provider call",async()=>{
  const f=await mount("investigation-saved-example",{live:false,handler:(call,state)=>{
    if(call.path.endsWith("/approve")){state.view.plan.approvals=[approval(state.view.plan)];return response(state.view);}
    if(call.path.endsWith("/export"))return response({schema_version:"mvp.investigation-export.v1",json_text:JSON.stringify(state.view),markdown_text:"# Investigation audit\n\nOriginal retained report"});
    throw new Error("No provider call permitted "+call.path);
  }});
  try{
    await open(f.renderer);await approve(f.renderer);assert.equal(button(f.renderer,"Run approved PubMed search").props.disabled,true);assert.equal(button(f.renderer,"Check PubMed matches").props.disabled,true);assert.match(text(f.renderer.root),/Saved examples cannot execute PubMed queries/);
    await act(async()=>button(f.renderer,"Prepare readable audit export").props.onClick());assert.equal(f.renderer.root.findAllByType("a").filter(link=>link.props.download).length,2);assert.match(text(f.renderer.root),/# Investigation audit/);
    assert.equal(f.calls.some(call=>/\/(execute|diagnose|propose)$/.test(call.path)),false);
  }finally{await act(async()=>f.renderer.unmount());}
});

test("failed provider requests replay safely and only an explicit new attempt gets a fresh request id",async()=>{
  const f=await mount("investigation-failure",{handler:(call,state)=>{
    if(call.path.endsWith("/approve")){state.view.plan.approvals=[approval(state.view.plan)];return response(state.view);}
    if(call.path.endsWith("/execute")){state.view.failures=[{request_id:call.body.request_id,operation:"execute",status:"failed",code:"provider_failed",message:"Offline provider failure",created_at:stamp}];return response({detail:{code:"provider_failed",message:"Offline provider failure"}},502);}
    throw new Error("Unexpected "+call.path);
  }});
  try{
    await open(f.renderer);await approve(f.renderer);
    await act(async()=>button(f.renderer,"Run approved PubMed search").props.onClick());assert.match(text(f.renderer.root),/Offline provider failure/);
    await act(async()=>button(f.renderer,"Run approved PubMed search").props.onClick());
    let calls=f.calls.filter(call=>call.path.endsWith("/execute"));assert.equal(calls[0].body.request_id,calls[1].body.request_id);
    await act(async()=>button(f.renderer,"Start a new PubMed search attempt").props.onClick());calls=f.calls.filter(call=>call.path.endsWith("/execute"));assert.notEqual(calls[2].body.request_id,calls[1].body.request_id);
    assert.equal(control(f.renderer,"Specialist PubMed strategy").props.value,query);assert.equal(f.calls.some(call=>call.path.endsWith("/propose")),false);
  }finally{await act(async()=>f.renderer.unmount());}
});

test("manual candidate decisions are versioned and remain separate when reopened",async()=>{
  const f=await mount("investigation-decisions",{handler:(call,state)=>{
    if(call.path.endsWith("/decisions")){const candidate=state.view.executions[0].candidates[0];assert.equal(call.body.expected_version,candidate.decision_version);state.view={...state.view,executions:[{...state.view.executions[0],candidates:[{...candidate,decision:call.body.decision,decision_version:candidate.decision_version+1}]}]};return response(state.view);}
    throw new Error("Unexpected "+call.path);
  }});
  f.state.view.executions=[{execution:{id:"execution"},search:{searched_at:stamp,query,total_reported:1,fetched_count:1,truncated:false,warnings:[],errors:[]},candidates:[{id:"candidate",paper:{id:"pmid:1",title:"Another report",authors:[],year:2026,pmid:"1",doi:null,pmcid:null,abstract:"Candidate abstract",url:""},decision:"unassessed",decision_version:0}]}] as unknown as Schema<"InvestigationView">["executions"];
  try{
    await open(f.renderer);await act(async()=>button(f.renderer,"Shortlist").props.onClick());assert.match(text(f.renderer.root),/Decision: shortlist · version 1/);
    await act(async()=>button(f.renderer,"Dismiss").props.onClick());assert.match(text(f.renderer.root),/Decision: dismiss · version 2/);
    await act(async()=>button(f.renderer,"Leave unassessed").props.onClick());assert.match(text(f.renderer.root),/Decision: unassessed · version 3/);
    await act(async()=>button(f.renderer,"All investigations for this cell").props.onClick());await open(f.renderer);assert.match(text(f.renderer.root),/Decision: unassessed · version 3/);
    assert.equal(f.calls.some(call=>/\/boards\/|\/source-preparations/.test(call.path)),false);
  }finally{await act(async()=>f.renderer.unmount());}
});

test("Needs review uses workflow state, not a scientific gap judgment",()=>{
  const cell={paper_id:"p",field_id:"f",head:{semantic_assessment:"human_supported",scope_result:"value_found",value:"Value",missing_information:""}};
  const view={freshness:"current",definition:{sources:[{paper_id:"p",source_type:"abstract"}]},cells:[cell]} as unknown as Schema<"BoardView">;
  assert.equal(unresolvedCell(view,"p","f"),false);
  for(const changes of [{semantic_assessment:"partial"},{scope_result:"not_found_in_inspected_material"},{missing_information:"Unresolved recruitment detail"},{value:null}])assert.equal(unresolvedCell({...view,cells:[{...cell,head:{...cell.head,...changes}}]} as unknown as Schema<"BoardView">,"p","f"),true);
  assert.equal(unresolvedCell({...view,freshness:"historical"},"p","f"),true);
  assert.equal(unresolvedCell({...view,cells:[]},"p","f"),true);
});

test("two-tab editor draft conflicts require inspecting its exact version before retaining local edits",async()=>{
  const f=await mount("investigation-draft-conflict",{handler:(call,state)=>{
    if(call.path.endsWith("/plan")){const next=saved(call.body.draft,2);next.revision.workspace_id=state.view.origin.workspace_id;next.revision.plan_id=state.view.origin.plan_id;state.view={...state.view,plan:next};return response(state.view);}
    throw new Error("Unexpected "+call.path);
  }});
  try{
    await open(f.renderer);
    const draftPath=f.calls.find(call=>call.path.includes("/drafts/search-plan-editor:"))!.path;
    const stored={version:2,data:{plan_id:f.state.view.origin.plan_id,base_revision_id:f.state.view.plan.revision.revision_id,draft:{...f.state.view.plan.revision.draft,manual_strategy:"OTHER TAB DRAFT"}},expected_assessment_head:null};
    f.drafts.set(draftPath,stored);
    const originalFetch=globalThis.fetch;
    globalThis.fetch=async(input,options)=>{
      if(decodeURIComponent(String(input))===draftPath&&options?.method==="PUT"&&JSON.parse(String(options.body)).version!==f.drafts.get(draftPath).version)return response({detail:{code:"draft_conflict",message:"Another tab saved this draft"}},409);
      return originalFetch(input,options);
    };
    await act(async()=>control(f.renderer,"Specialist PubMed strategy").props.onChange({target:{value:"MY RETAINED QUERY"}}));
    await act(async()=>button(f.renderer,"Save revised investigation plan").props.onClick());
    assert.match(text(f.renderer.root),/Another tab saved this draft/);assert.equal(button(f.renderer,"Save revised investigation plan").props.disabled,true);
    await act(async()=>button(f.renderer,"Inspect latest investigation").props.onClick());assert.match(text(f.renderer.root),/OTHER TAB DRAFT/);
    f.drafts.set(draftPath,{...stored,version:3});
    await act(async()=>button(f.renderer,"Keep my edits against this inspected revision").props.onClick());assert.match(text(f.renderer.root),/inspected draft changed again/);assert.equal(control(f.renderer,"Specialist PubMed strategy").props.value,"MY RETAINED QUERY");
    await act(async()=>button(f.renderer,"Inspect latest investigation").props.onClick());
    await act(async()=>button(f.renderer,"Keep my edits against this inspected revision").props.onClick());assert.equal(button(f.renderer,"Save revised investigation plan").props.disabled,false);
    await act(async()=>button(f.renderer,"Save revised investigation plan").props.onClick());assert.match(text(f.renderer.root),/SAVED PLAN REVISION 2/);assert.equal(f.state.view.plan.revision.draft.manual_strategy,"MY RETAINED QUERY");
    assert.equal(f.calls.some(call=>/\/(execute|diagnose)$/.test(call.path)),false);
  }finally{await act(async()=>f.renderer.unmount());}
});

test("citation-fetch failure stays distinct from a zero-match search and shows the provider cap",async()=>{
  const f=await mount("investigation-fetch-failure");
  f.state.view.executions=[{execution:{id:"execution",requested_max_results:10},search:{searched_at:stamp,query,total_reported:213,fetched_count:0,truncated:true,warnings:["Only the first ten identifiers were requested"],errors:[{code:"pubmed_fetch_failed",message:"Citation metadata fetch failed",retryable:true,paper_id:null}]},candidates:[]}] as unknown as Schema<"InvestigationView">["executions"];
  try{
    await open(f.renderer);const result=text(f.renderer.root.findByProps({"aria-label":"Saved investigation results"}));
    assert.match(result,/213 provider-reported matches · 0 records fetched · 0 candidate records/);
    assert.match(result,/capped preview/);assert.match(result,/Requested limit: 10/);assert.match(result,/Citation metadata fetch failed/);assert.match(result,/not a zero-match finding/);
    assert.equal(f.calls.some(call=>call.method!=="GET"),false);
  }finally{await act(async()=>f.renderer.unmount());}
});
