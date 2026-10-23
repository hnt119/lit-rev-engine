import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import SearchPlanner,{IntentPlanEditor} from "../components/search-planner";
import {flushDrafts} from "../lib/drafts";
import {approval,capability,diagnostic,draft,proposal,response,saved,stamp,workspace} from "./search-planner-fixtures";
import type {Schema} from "../lib/api";
import Discover from "../components/discover";
import {capabilities as globalCapability} from "./import-collection-fixtures";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,window:{confirm:()=>true}});
const text=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(text).join("");
const button=(renderer:ReactTestRenderer,name:string)=>renderer.root.findAllByType("button").find(node=>text(node)===name)!;
const field=(renderer:ReactTestRenderer,name:string)=>renderer.root.findAllByType("label").find(node=>node.children[0]===name)!.findAll(node=>["input","textarea","select"].includes(String(node.type)))[0];
const checkbox=(renderer:ReactTestRenderer,prefix:string)=>renderer.root.findAllByType("label").find(node=>text(node).startsWith(prefix))!.findByType("input");
type Call={path:string;method:string;body:any};
let workspaceSequence=0,currentWorkspace=workspace();
function storage(){const values=new Map<string,string>();Object.defineProperty(globalThis,"sessionStorage",{configurable:true,value:{getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>values.set(key,value),removeItem:(key:string)=>values.delete(key)}});}
function mock(view:Schema<"SearchPlanView">|null,handle:(call:Call)=>Response|Promise<Response>,enabled=false){
  const calls:Call[]=[],editorDrafts=new Map<string,Schema<"DraftRecord">>();storage();
  currentWorkspace={...workspace(),id:"software-planner-test-"+(++workspaceSequence)};
  globalThis.fetch=async(input,options)=>{const call={path:String(input),method:options?.method??"GET",body:typeof options?.body==="string"?JSON.parse(options.body):undefined};calls.push(call);
    if(call.path.endsWith("/session"))return response({csrf_token:"software-only"});
    if(call.path.includes("/drafts/")){
      const scope=decodeURIComponent(call.path.split("/").at(-1)!);
      if(scope.startsWith("search-plan-editor:")){
        const prior=editorDrafts.get(scope)??{scope,version:0,data:{},expected_assessment_head:null,updated_at:null};
        if(call.method==="GET")return response(prior);
        assert.equal(call.method,"PUT");assert.equal(call.body.version,prior.version);
        const next={...prior,version:prior.version+1,data:call.body.data,expected_assessment_head:call.body.expected_assessment_head};
        editorDrafts.set(scope,next);return response(next);
      }
    }
    if(call.path.endsWith("/search-plan-capabilities"))return response(capability(enabled));
    if(call.method==="GET"&&call.path.endsWith("/search-plans"))return response({plans:view?.revisions??[]});
    if(view&&call.method==="GET"&&call.path.endsWith("/search-plans/"+view.revision.plan_id))return response(view);
    const result=await handle(call);
    if(result.ok&&((call.method==="POST"&&call.path.endsWith("/search-plans"))||(call.method==="PUT"&&/\/search-plans\/[^/]+$/.test(call.path))))view=await result.clone().json();
    if(result.ok&&call.path.endsWith("/propose")&&view){const receipt=await result.clone().json();view={...view,proposals:[receipt,...view.proposals]};}
    return result;
  };return calls;
}
async function mount(view:Schema<"SearchPlanView">|null,onExecuted:(search:Schema<"SearchPreview">)=>Promise<void>=async()=>{},revision?:string){
  let renderer!:ReactTestRenderer,plan=view?.revision.plan_id,requestedRevision=revision;
  const render=()=> <SearchPlanner workspace={currentWorkspace} initialQuestion={currentWorkspace.question} requestedPlan={plan} requestedRevision={requestedRevision} onOpen={async(next,revision)=>{plan=next;requestedRevision=revision;renderer.update(render());}} onExecuted={onExecuted}/>;
  await act(async()=>{renderer=create(render());});return renderer;
}

test("manual strategy preserves raw bytes, compiles without a model, and requires separate explicit approval/execution",async()=>{
  const raw='  ("lichen’s pigments"[tiab] OR 日本[tiab])\r\nAND (rainfall OR moisture)\r  ';
  let current:Schema<"SearchPlanView">|null=null;const executed:string[]=[];
  const calls=mock(null,call=>{
    if(call.path.endsWith("/search-plans")&&call.method==="POST"){current=saved(call.body.draft);return response(current);}
    if(call.path.endsWith("/approve"))return response(approval(current!));
    if(call.path.endsWith("/execute")){const candidate=current!.revision.compiled.candidates[0],search={schema_version:"mvp.exploratory-preview.v1",id:"software-capture",query:raw,research_question:current!.revision.draft.original_question,query_translation:null,searched_at:stamp,sort:candidate.sort,date_from:null,date_to:null,total_reported:0,fetched_count:0,ordered_identifiers:[],papers:[],warnings:[],truncated:false,provider:"software-fixture",mode:"live",errors:[]} as Schema<"SearchPreview">;return response({execution:{schema_version:"mvp.planned-search-execution.v2",id:"software-execution",plan_id:current!.revision.plan_id,revision_id:current!.revision.revision_id,candidate_id:candidate.id,candidate_sha256:candidate.candidate_sha256,approval_id:"software-approval",search_id:search.id,search_snapshot_sha256:"e".repeat(64),created_at:stamp},search});}
    throw new Error("Unexpected request "+call.path);
  });
  const renderer=await mount(null,async value=>{executed.push(value.id);});
  try{
    await act(async()=>field(renderer,"Planning mode").props.onChange({target:{value:"manual_strategy"}}));
    await act(async()=>field(renderer,"Specialist PubMed strategy").props.onPaste({clipboardData:{getData:()=>raw},currentTarget:{selectionStart:0,selectionEnd:0},preventDefault(){}}));
    assert.equal(calls.filter(call=>call.method!=="GET").length,0);assert.equal(field(renderer,"Specialist PubMed strategy").props.value,raw);
    await act(async()=>flushDrafts());
    const editorSave=calls.find(call=>call.method==="PUT"&&call.path.includes("/drafts/"))!;
    assert.equal(editorSave.body.data.draft.manual_strategy,raw);assert.equal(calls.some(call=>call.method==="POST"),false);
    await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));
    assert.equal(calls.find(call=>call.method==="POST")!.body.draft.manual_strategy,raw);assert.equal(button(renderer,"Build search").props.disabled,true);
    assert.equal(button(renderer,"Approve this candidate").props.disabled,true);assert.equal(button(renderer,"Search papers").props.disabled,true);
    await act(async()=>checkbox(renderer,"Acknowledge that this exact specialist strategy").props.onChange({target:{checked:true}}));
    await act(async()=>button(renderer,"Approve this candidate").props.onClick());
    assert.equal(executed.length,0);assert.equal(button(renderer,"Search papers").props.disabled,false);
    await act(async()=>button(renderer,"Search papers").props.onClick());
    assert.deepEqual(executed,["software-capture"]);assert.deepEqual(calls.filter(call=>call.method==="POST").map(call=>call.path.split("/").at(-1)),["search-plans","approve","execute"]);
  }finally{await act(async()=>renderer.unmount());}
});

test("Build search saves the exact question and requests one proposal without hand-authored concepts or automatic approvals",async()=>{
  let current:Schema<"SearchPlanView">|null=null;
  const calls=mock(null,call=>{
    if(call.path.endsWith("/search-plans")&&call.method==="POST"){assert.deepEqual(call.body.draft.concepts,[]);assert.deepEqual(call.body.draft.variants,[]);current=saved(call.body.draft);current.revision.compiled.candidates=[];return response(current);}
    if(call.path.endsWith("/propose")){assert.equal(call.body.original_question,current!.revision.draft.original_question);assert.equal(call.body.expected_revision_id,current!.revision.revision_id);return response(proposal(current!));}
    if(call.method==="PUT"&&call.path.includes("/search-plans/")){current=saved(call.body.draft,2);return response(current);}
    throw new Error("Unexpected "+call.path);
  },true);
  const renderer=await mount(null);
  try{
    const exact="How does 日本 rainfall affect lichen’s pigments? Preserve alternatives and exclusions.";
    await act(async()=>field(renderer,"Original research question").props.onChange({target:{value:exact}}));
    assert.equal(button(renderer,"Build search").props.disabled,false);
    let ancestor=button(renderer,"Build search").parent;while(ancestor){assert.notEqual(ancestor.type,"details","Build search must be available in the primary flow");ancestor=ancestor.parent;}
    await act(async()=>button(renderer,"Build search").props.onClick());
    assert.deepEqual(calls.filter(call=>call.method==="POST").map(call=>call.path.split("/").at(-1)),["search-plans","propose"]);
    assert.equal(current!.revision.draft.original_question,exact);assert.match(text(renderer.root.findByProps({"aria-label":"Proposed search"})),/Lichen pigments/);
    assert.equal(calls.some(call=>/approve|diagnose|execute|query-suggestions/.test(call.path)),false);
    await act(async()=>button(renderer,"Use as editable draft").props.onClick());assert.equal(checkbox(renderer,"Approve this exact term").props.checked,false);
    await act(async()=>button(renderer,"Approve displayed terms for compilation").props.onClick());assert.equal(checkbox(renderer,"Approve this exact term").props.checked,true);
    assert.equal(calls.some(call=>call.path.endsWith("/approve")),false,"term review does not approve the final saved candidate");
    await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));assert.equal(current!.revision.draft.concepts[0].terms[0].state,"approved");assert.equal(button(renderer,"Search papers").props.disabled,true);assert.equal(calls.filter(call=>call.path.endsWith("/propose")).length,1);
  }finally{await act(async()=>renderer.unmount());}
});

test("disabled planning keeps an exact manual query first-class without fallback calls",async()=>{
  const calls=mock(null,call=>{throw new Error("No implicit fallback "+call.path);});const renderer=await mount(null);
  try{
    assert.equal(button(renderer,"Build search").props.disabled,true);assert.match(text(renderer.root),/Build search is unavailable: Disabled by default/);
    await act(async()=>button(renderer,"Paste my own query").props.onClick());const exact='  日本[tiab]\r\nAND (rainfall OR "lichen’s pigments")\r  ';
    await act(async()=>field(renderer,"Specialist PubMed strategy").props.onPaste({clipboardData:{getData:()=>exact},currentTarget:{selectionStart:0,selectionEnd:0},preventDefault(){}}));
    assert.equal(field(renderer,"Specialist PubMed strategy").props.value,exact);await act(async()=>button(renderer,"Plan from my question").props.onClick());assert.equal(button(renderer,"Build search").props.disabled,true);assert.match(text(renderer.root),/Your separate pasted query is retained/);await act(async()=>button(renderer,"Paste my own query").props.onClick());assert.equal(field(renderer,"Specialist PubMed strategy").props.value,exact);assert.equal(calls.filter(call=>call.method==="POST").length,0);
  }finally{await act(async()=>renderer.unmount());}
});

test("zero match diagnostics remain visible beside primary checks and only explicit edits change the query",async()=>{
  const view=saved(),zero=diagnostic(view);zero.receipt={...zero.receipt,status:"succeeded",reported_count:0,error:null,messages:[],query_translation:"SOFTWARE TEST translation"};view.diagnostics=[zero];
  const calls=mock(view,call=>{throw new Error("No automatic retry "+call.path);});const renderer=await mount(view);
  try{
    let ancestor=button(renderer,"Check matches").parent;while(ancestor){assert.notEqual(ancestor.type,"details");ancestor=ancestor.parent;}
    assert.match(text(renderer.root),/No papers matched this query/);assert.match(text(renderer.root),/SOFTWARE TEST translation/);assert.match(text(renderer.root),/tagged phrases, date filters, AND groups and provider warnings/);
    await act(async()=>button(renderer,"Review filters and broader options").props.onClick());const advanced=renderer.root.findAllByType("details").find(node=>text(node.findAllByType("summary")[0]).startsWith("Advanced concepts"))!;assert.equal(advanced.props.open,true);
    await act(async()=>button(renderer,"Edit query").props.onClick());assert.equal(field(renderer,"Specialist PubMed strategy").props.value,view.revision.compiled.candidates[0].query);assert.equal(button(renderer,"Search papers").props.disabled,true);assert.equal(calls.filter(call=>call.method==="POST").length,0);
  }finally{await act(async()=>renderer.unmount());}
});

test("required/excluded deferrals and a subquestion each need explicit acceptance; diagnostics keep missing counts distinct from zero",async()=>{
  const value=draft();value.concepts.push({...value.concepts[0],id:"geography",label:"Japanese study origin",role:"geography",terms:[],retrieval_use:"screen_later"},{...value.concepts[0],id:"excluded",label:"Animal-only studies",role:"study_design",requirement:"excluded",terms:[],retrieval_use:"screen_later"});
  value.variants[0]={...value.variants[0],kind:"subquestion",deferred_concept_ids:["geography","excluded"],deferral_reason:"Screen exact study origin and design later",split_explanation:"This is a separate exploratory pigment question"};
  const view=saved(value),candidate=view.revision.compiled.candidates[0];Object.assign(candidate,{kind:"subquestion",deferred_required_ids:["geography"],deferred_excluded_ids:["excluded"],deferred_constraints:["required geography retained for screening","explicit exclusion retained for screening"],requires_split_approval:true,differences:["A separate subquestion does not establish the original joint relationship"]});
  const calls=mock(view,call=>call.path.endsWith("/approve")?response(approval(view)):call.path.endsWith("/diagnose")?response(diagnostic(view)):Promise.reject(new Error("Unexpected "+call.path)));
  const renderer=await mount(view);
  try{
    assert.equal(button(renderer,"Approve this candidate").props.disabled,true);
    for(const prefix of ["Explicitly accept deferring Japanese study origin","Explicitly accept deferring Animal-only studies"]){await act(async()=>checkbox(renderer,prefix).props.onChange({target:{checked:true}}));assert.equal(button(renderer,"Approve this candidate").props.disabled,true);}
    await act(async()=>checkbox(renderer,"Accept this separately run subquestion").props.onChange({target:{checked:true}}));
    await act(async()=>button(renderer,"Approve this candidate").props.onClick());const approved=calls.find(call=>call.path.endsWith("/approve"))!;assert.deepEqual(approved.body.acknowledged_deferred_concept_ids,["geography","excluded"]);assert.equal(approved.body.accept_subquestion_split,true);
    assert.equal(calls.some(call=>call.path.endsWith("/diagnose")),false);await act(async()=>button(renderer,"Check matches").props.onClick());
    assert.match(text(renderer.root),/Unavailable provider-reported matches/);assert.match(text(renderer.root),/Synthetic provider failed/);assert.match(text(renderer.root),/not a complete capture or a relevance\/recall score/);assert.equal(calls.some(call=>call.path.endsWith("/execute")),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("CAS conflicts retain local edits, expose an explicit latest-head inspection, and only rebase on deliberate action",async()=>{
  const original=saved(),newer=saved({...draft(),original_question:"Another researcher’s retained question"},2);let inspection=false,saves=0;
  const calls=mock(original,call=>{
    if(call.method==="PUT"){saves++;if(saves===1)return response({detail:{code:"stale_plan_revision",message:"Synthetic newer head exists"}},409);assert.equal(call.body.expected_revision_id,newer.current_revision_id);return response(saved(call.body.draft,3));}
    throw new Error("Unexpected "+call.path);
  });
  const originalFetch=globalThis.fetch;globalThis.fetch=async(input,options)=>{if(inspection&&String(input).endsWith("/search-plans/software-plan")&&(options?.method??"GET")==="GET"){calls.push({path:String(input),method:"GET",body:undefined});return response(newer);}return originalFetch(input,options);};
  const renderer=await mount(original);
  try{
    await act(async()=>field(renderer,"Original research question").props.onChange({target:{value:"My unsaved 日本 AND rainfall question"}}));
    await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));assert.equal(field(renderer,"Original research question").props.value,"My unsaved 日本 AND rainfall question");assert.match(text(renderer.root),/Synthetic newer head exists/);
    inspection=true;await act(async()=>button(renderer,"Inspect latest saved revision").props.onClick());assert.equal(field(renderer,"Original research question").props.value,"My unsaved 日本 AND rainfall question");assert.match(text(renderer.root),/Another researcher’s retained question/);assert.equal(saves,1);
    await act(async()=>button(renderer,"Keep local edits against this inspected latest head").props.onClick());assert.equal(field(renderer,"Original research question").props.value,"My unsaved 日本 AND rainfall question");assert.equal(saves,1);
    await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));assert.equal(saves,2);assert.match(text(renderer.root),/SAVED PLAN REVISION 3/);assert.equal(button(renderer,"Search papers").props.disabled,true);
  }finally{await act(async()=>renderer.unmount());}
});

test("late local-model proposals cannot overwrite edits and require explicit adoption and term approval",async()=>{
  const view=saved();let finish!:(value:Response)=>void,pending!:Promise<void>;
  const calls=mock(view,call=>{if(call.path.endsWith("/propose"))return new Promise<Response>(resolve=>{finish=resolve;});throw new Error("Unexpected "+call.path);},true);
  const renderer=await mount(view);
  try{
    await act(async()=>{pending=button(renderer,"Build search").props.onClick();});
    await act(async()=>field(renderer,"Original research question").props.onChange({target:{value:"Newer local question survives the slow model"}}));
    await act(async()=>{finish(response(proposal(view)));await pending;});
    assert.equal(field(renderer,"Original research question").props.value,"Newer local question survives the slow model");assert.equal(button(renderer,"Use as editable draft").props.disabled,true);assert.equal(calls.filter(call=>call.method!=="GET").length,1);
    await act(async()=>button(renderer,"Restore saved revision / reset unsaved plan").props.onClick());
    await act(async()=>button(renderer,"Use as editable draft").props.onClick());assert.equal(checkbox(renderer,"Approve this exact term").props.checked,false);assert.equal(button(renderer,"Search papers").props.disabled,true);assert.match(text(renderer.root),/model proposed/);assert.equal(calls.some(call=>call.method==="PUT"&&call.path.includes("/search-plans/")),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("model provider failure preserves the manual plan without invoking a fallback",async()=>{
  const view=saved(),calls=mock(view,call=>call.path.endsWith("/propose")?response({detail:{code:"planner_provider_failure",message:"Synthetic local planner unavailable"}},502):Promise.reject(new Error("No fallback "+call.path)),true);
  const renderer=await mount(view);
  try{await act(async()=>button(renderer,"Build search").props.onClick());assert.match(text(renderer.root),/Synthetic local planner unavailable/);assert.equal(field(renderer,"Original research question").props.value,view.revision.draft.original_question);assert.deepEqual(calls.filter(call=>call.method!=="GET").map(call=>call.path.split("/").at(-1)),["propose"]);assert.equal(renderer.root.findAllByType("button").some(node=>text(node)==="Use as editable draft"),false);}finally{await act(async()=>renderer.unmount());}
});

test("editing approved terms resets approval, AND/OR switching preserves references, and manual raw strategy survives mode changes",async()=>{
  storage();let current=draft(),renderer!:ReactTestRenderer;
  current.concepts.push({...current.concepts[0],id:"rainfall",label:"Rainfall"});current.variants[0].expression={op:"all_of",concept_id:null,children:[{op:"concept_ref",concept_id:"lichen",children:[]},{op:"concept_ref",concept_id:"rainfall",children:[]}]};
  const render=()=> <IntentPlanEditor draft={current} limits={capability().limits} onEdit={update=>{current=update(current);renderer.update(render());}}/>;
  globalThis.fetch=async()=>{throw new Error("No editing request allowed");};await act(async()=>{renderer=create(render());});
  try{
    await act(async()=>renderer.root.findAllByType("label").find(node=>node.children[0]==="Term ")!.findByType("input").props.onChange({target:{value:"Edited pigment"}}));assert.equal(current.concepts[0].terms[0].state,"proposed");
    const relationship=renderer.root.findAllByType("label").find(node=>node.children[0]==="Relationship")!.findByType("select");await act(async()=>relationship.props.onChange({target:{value:"any_of"}}));assert.deepEqual(current.variants[0].expression.children.map(item=>item.concept_id),["lichen","rainfall"]);assert.equal(current.variants[0].expression.op,"any_of");
    await act(async()=>field(renderer,"Planning mode").props.onChange({target:{value:"manual_strategy"}}));const raw="  lichen\r\nAND rain\r  ";await act(async()=>field(renderer,"Specialist PubMed strategy").props.onPaste({clipboardData:{getData:()=>raw},currentTarget:{selectionStart:0,selectionEnd:0},preventDefault(){}}));await act(async()=>field(renderer,"Planning mode").props.onChange({target:{value:"natural_question"}}));assert.equal(current.manual_strategy,raw);assert.match(text(renderer.root),/Concept compilation remains blocked/);
  }finally{await act(async()=>renderer.unmount());}
});

test("known-paper seeds remain explicit, stay bounded during rapid additions, and changed identifiers require renewed consent",async()=>{
  const view=saved(),calls=mock(view,call=>{throw new Error("No diagnostic before explicit approval "+call.path);});const renderer=await mount(view);
  try{
    const add=button(renderer,"Add a known-paper diagnostic seed").props.onClick;await act(async()=>{for(let index=0;index<5;index++)add();});assert.equal(renderer.root.findAllByType("label").filter(node=>node.children[0]==="Known PMID ").length,3);assert.equal(button(renderer,"Add a known-paper diagnostic seed").props.disabled,true);
    const identifiers=renderer.root.findAllByType("label").filter(node=>node.children[0]==="Known PMID ").map(node=>node.findByType("input"));
    for(let index=0;index<identifiers.length;index++)await act(async()=>identifiers[index].props.onChange({target:{value:String(12345670+index)}}));
    const approvals=renderer.root.findAllByType("label").filter(node=>text(node).startsWith("Approve sending these explicit identifiers")).map(node=>node.findByType("input"));for(const control of approvals)await act(async()=>control.props.onChange({target:{checked:true}}));assert.equal(button(renderer,"Check matches").props.disabled,false);
    await act(async()=>renderer.root.findAllByType("label").find(node=>node.children[0]==="Known PMID ")!.findByType("input").props.onChange({target:{value:"87654321"}}));assert.equal(checkbox(renderer,"Approve sending these explicit identifiers").props.checked,false);assert.equal(button(renderer,"Check matches").props.disabled,true);assert.equal(calls.filter(call=>call.method!=="GET").length,0);
  }finally{await act(async()=>renderer.unmount());}
});

test("a historical plan reopens via its exact revision and stays read only until the latest head is explicitly opened",async()=>{
  const historical=saved(),latest=saved(draft(),2);historical.current_revision_id=latest.current_revision_id;historical.revisions.push(latest.revisions[0]);historical.approvals=[approval(historical)];
  const calls=mock(latest,call=>call.method==="GET"&&call.path.endsWith("?revision_id=software-revision-1")?response(historical):Promise.reject(new Error("Unexpected "+call.path)));
  const renderer=await mount(historical,async()=>{throw new Error("No historical execution");},historical.revision.revision_id);
  try{
    assert.equal(field(renderer,"Original research question").props.value,historical.revision.draft.original_question);assert.match(text(renderer.root),/HISTORICAL PLAN · READ ONLY/);assert.equal(button(renderer,"Approve this candidate").props.disabled,true);assert.equal(button(renderer,"Check matches").props.disabled,true);assert.equal(button(renderer,"Search papers").props.disabled,true);
    await act(async()=>button(renderer,"Open latest revision to edit").props.onClick());assert.match(text(renderer.root),/SAVED PLAN REVISION 2/);assert.equal(calls.filter(call=>call.method!=="GET").length,0);
  }finally{await act(async()=>renderer.unmount());}
});

test("a wrong candidate approval is rejected without enabling execution or invoking a fallback",async()=>{
  const view=saved(),wrong={...approval(view),candidate_sha256:"f".repeat(64)},calls=mock(view,call=>call.path.endsWith("/approve")?response(wrong):Promise.reject(new Error("No fallback "+call.path)));const renderer=await mount(view);
  try{await act(async()=>button(renderer,"Approve this candidate").props.onClick());assert.match(text(renderer.root),/approval belongs to a different candidate revision/);assert.equal(button(renderer,"Search papers").props.disabled,true);assert.equal(calls.filter(call=>call.method!=="GET").length,1);}finally{await act(async()=>renderer.unmount());}
});

test("Discover persists edited planning inputs before opening Import without compiling or executing",async()=>{
  const calls=mock(null,call=>{if(call.path.endsWith("/drafts/discover"))return response({scope:"discover",version:0,data:{},expected_assessment_head:null,updated_at:null});if(call.path.endsWith("/imports"))return response({imports:[]});throw new Error("No hidden request "+call.path);});let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<Discover workspace={currentWorkspace} capabilities={{...globalCapability,search_plans_ready:true,live_available:true}} refresh={async()=>{}} navigate={async()=>{await flushDrafts();return {status:"success"};}}/>);});
  try{
    assert.match(text(renderer.root),/Build your paper search/);assert.equal(renderer.root.findAllByType("button").some(node=>text(node)==="Search PubMed preview"),false);
    await act(async()=>field(renderer,"Original research question").props.onChange({target:{value:"A locally edited unfamiliar research question"}}));await act(async()=>button(renderer,"Import papers").props.onClick());
    const persisted=calls.find(call=>call.method==="PUT"&&call.path.includes("/drafts/search-plan-editor"));
    assert.equal(persisted?.body.data.draft.original_question,"A locally edited unfamiliar research question");
    assert.equal(calls.some(call=>call.method==="POST"||call.method==="PUT"&&call.path.includes("/search-plans/")),false);
    assert.equal(calls.some(call=>call.path.endsWith("/imports")),true);
  }finally{await act(async()=>renderer.unmount());}
});

test("compiled candidates display retained non-query preferences without claiming automatic ranking or screening",async()=>{
  const value=draft();value.concepts.push({...value.concepts[0],id:"preferred-region",label:"Southeast Asian origin",role:"geography",requirement:"preferred",retrieval_use:"screen_later",terms:[]},{...value.concepts[0],id:"ranking-context",label:"Dietary context",role:"exposure",requirement:"preferred",retrieval_use:"rank_only",terms:[]});
  const view=saved(value),original=JSON.stringify(view),calls=mock(view,call=>{throw new Error("No display-triggered mutation "+call.path);});const renderer=await mount(view);
  try{
    const retained=renderer.root.findByProps({"aria-label":"Intent retained outside this query"});assert.match(text(retained),/Southeast Asian origin · preferred · screen later/);assert.match(text(retained),/Dietary context · preferred · rank only/);assert.match(text(retained),/do not automatically rank results, filter records or make screening decisions/);
    assert.equal(field(renderer,"Exact compiled PubMed query").props.value,view.revision.compiled.candidates[0].query);assert.equal(JSON.stringify(view),original);assert.equal(calls.filter(call=>call.method!=="GET").length,0);
  }finally{await act(async()=>renderer.unmount());}
});

test("a latest-head editable draft cannot replace the displayed immutable historical plan",async()=>{
  const historical=saved(),latest=saved({...draft(),original_question:"LATEST COMMITTED QUESTION"},2);
  historical.current_revision_id=latest.current_revision_id;historical.revisions.push(latest.revisions[0]);
  const retained={...draft(),original_question:"UNCOMPILED LATEST-HEAD EDITOR BUFFER"};
  const calls=mock(latest,call=>call.method==="GET"&&call.path.endsWith("?revision_id="+historical.revision.revision_id)?response(historical):Promise.reject(new Error("Unexpected "+call.path)));
  const originalFetch=globalThis.fetch;
  globalThis.fetch=async(input,options)=>{
    if((options?.method??"GET")==="GET"&&decodeURIComponent(String(input)).endsWith("/drafts/search-plan-editor:software-plan")){
      calls.push({path:String(input),method:"GET",body:undefined});
      return response({scope:"search-plan-editor:software-plan",version:1,data:{draft:retained,plan_id:latest.revision.plan_id,base_revision_id:latest.revision.revision_id},expected_assessment_head:null,updated_at:stamp});
    }
    return originalFetch(input,options);
  };
  const renderer=await mount(historical,async()=>{throw new Error("No historical execution");},historical.revision.revision_id);
  try{
    assert.match(text(renderer.root),/HISTORICAL PLAN · READ ONLY/);
    assert.equal(field(renderer,"Original research question").props.value,historical.revision.draft.original_question);
    await act(async()=>button(renderer,"Open latest revision to edit").props.onClick());
    assert.equal(field(renderer,"Original research question").props.value,retained.original_question);
    assert.equal(button(renderer,"Search papers").props.disabled,true);
    assert.equal(calls.some(call=>call.method!=="GET"),false);
  }finally{await act(async()=>renderer.unmount());}
});
