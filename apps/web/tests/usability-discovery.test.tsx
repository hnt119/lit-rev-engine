import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Discover from "../components/discover";
import {CollectionPreparationJobs} from "../components/preparation-jobs";
import {flushDrafts} from "../lib/drafts";
import type {LocationState,Navigate} from "../components/workspace-app";
import type {Schema} from "../lib/api";
import {capabilities,paper,response,stamp,storage,workspace} from "./import-collection-fixtures";
import {research} from "./collection-research-fixtures";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
const button=(r:ReactTestRenderer,name:string)=>r.root.findAllByType("button").find(node=>text(node)===name)!;
const deferred=<T,>()=>{let resolve!:(value:T)=>void;const promise=new Promise<T>(done=>resolve=done);return {promise,resolve};};
async function observed(check:()=>boolean){const deadline=Date.now()+5000;while(!check()){assert.ok(Date.now()<deadline,"expected acknowledged UI state was not observed");await act(async()=>{await new Promise<void>(resolve=>setImmediate(resolve));});}}
function savedSearch(id:string):Schema<"SearchPreview">{const papers=[paper(1),paper(2),paper(3)];return {schema_version:"mvp.exploratory-preview.v1",id,query:"software test",research_question:"SOFTWARE TEST",query_translation:null,searched_at:stamp,sort:"relevance",date_from:null,date_to:null,total_reported:3,fetched_count:3,ordered_identifiers:papers.map(item=>item.id),papers,warnings:[],truncated:false,provider:"software-fixture",mode:"test",errors:[]};}
function draftStore(){const records=new Map<string,any>();return (path:string,method:string,body:any)=>{const scope=decodeURIComponent(path.split("/").at(-1)!);if(method==="PUT"){const record={scope,version:body.version+1,data:body.data,expected_assessment_head:null,updated_at:stamp};records.set(scope,record);return record;}return records.get(scope)??{scope,version:0,data:{},expected_assessment_head:null,updated_at:null};};}

test("persistent intake preserves filtered results and all shared selection counts without rerunning discovery",async()=>{
  const search=savedSearch("intake-retention"),state={...workspace("intake-retention"),searches:[{...search,distinct_count:3}]},draft=draftStore(),calls:{path:string;method:string}[]=[];
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;calls.push({path,method});if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.includes("/drafts/"))return response(draft(path,method,body));if(path.endsWith("/papers"))return response(search);if(path.includes("/maps?"))return response({maps:[],jobs:[]});if(path.endsWith("/imports"))return response({imports:[]});if(path.endsWith("/collections"))return response({collections:[],max_map_papers:50,max_prepared_sources:30});throw new Error("Unexpected software request "+path);};
  let renderer!:ReactTestRenderer,intake:LocationState["intake"];
  const navigate:Navigate=async next=>{await flushDrafts();intake=next.intake;renderer.update(view());return {status:"success"};};
  const view=()=> <Discover workspace={state} capabilities={capabilities} requestedIntake={intake} refresh={async()=>{}} navigate={navigate}/>;
  await act(async()=>{renderer=create(view());});
  try{
    const checks=renderer.root.findAllByType("input").filter(node=>node.props.type==="checkbox");await act(async()=>{checks[0].props.onChange();checks[1].props.onChange();});
    await act(async()=>renderer.root.findAllByType("button").find(node=>text(node)==="Inspect paper")!.props.onClick());
    const filter=()=>renderer.root.findAllByType("input").find(node=>node.props.type==="search")!;
    await act(async()=>filter().props.onChange({target:{value:"CITATION 3"}}));
    for(const title of ["Papers & source selection","Paper inspector","Semantic map"]){const count=renderer.root.findByProps({"aria-label":title+" selection count"});assert.match(text(count),/2 \/ 30 selected/);assert.match(text(count),/2 outside the visible subset/);}
    const rowBefore=renderer.root.findByProps({"data-paper-id":paper(3).id});
    await act(async()=>button(renderer,"Import papers").props.onClick());assert.equal(filter().props.value,"CITATION 3");assert.equal(renderer.root.findByProps({"data-paper-id":paper(3).id}),rowBefore);
    await act(async()=>button(renderer,"Browse collections").props.onClick());assert.equal(filter().props.value,"CITATION 3");
    const switcher=renderer.root.findByProps({"aria-label":"Add papers"});assert.equal(switcher.findAllByType("button").length,3);assert.equal(calls.filter(call=>call.path.endsWith("/papers")).length,1);assert.equal(calls.some(call=>call.method==="POST"),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("a blocked intake switch reports next to the switcher and Retry saves retained edits before leaving",async()=>{
  const state=workspace("intake-retry"),draft=draftStore(),calls:string[]=[];let fail=true;
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;calls.push(method+" "+path);if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.includes("/drafts/")){if(method==="PUT"&&fail)return response({error:{code:"save_failed",message:"SOFTWARE TEST draft save failed"}},500);return response(draft(path,method,body));}if(path.endsWith("/imports"))return response({imports:[]});throw new Error("Unexpected software request "+path);};
  let renderer!:ReactTestRenderer;
  const navigate:Navigate=async()=>{try{await flushDrafts();return {status:"success"};}catch(error){return {status:"blocked",message:(error as Error).message};}};
  await act(async()=>{renderer=create(<Discover workspace={state} capabilities={capabilities} refresh={async()=>{}} navigate={navigate}/>);});
  try{
    await act(async()=>renderer.root.findAllByType("textarea")[0].props.onChange({target:{value:"RECOVERABLE INCOMPLETE QUESTION"}}));
    await act(async()=>button(renderer,"Import papers").props.onClick());
    const switcher=renderer.root.findByProps({"aria-label":"Add papers"});assert.match(text(switcher),/draft save failed/);assert.equal(calls.some(path=>path.endsWith("/imports")),false);assert.equal(renderer.root.findAllByType("textarea")[0].props.value,"RECOVERABLE INCOMPLETE QUESTION");
    fail=false;await act(async()=>button(renderer,"Retry").props.onClick());assert.ok(calls.some(path=>path.endsWith("/imports")));assert.equal(renderer.root.findByProps({"aria-label":"Add papers"}).findAllByProps({role:"alert"}).length,0);
  }finally{await act(async()=>renderer.unmount());}
});

test("result focus is exact and one-shot across edits and reopen, and zero results offer query repair without prepare",async()=>{
  const search=savedSearch("focus-once"),state={...workspace("focus-once"),searches:[{...search,distinct_count:3}]},draft=draftStore();let focuses=0,scrolls=0;
  globalThis.fetch=async(input,options)=>{const path=String(input);if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.includes("/drafts/"))return response(draft(path,options?.method??"GET",undefined));if(path.endsWith("/papers"))return response(search);if(path.includes("/maps?"))return response({maps:[],jobs:[]});throw new Error(path);};
  const props={workspace:state,capabilities,refresh:async()=>{},navigate:async()=>{},requestedFocusResult:search.id};
  const options={createNodeMock:(element:any)=>element.props["data-result-id"]?{focus:()=>focuses++,scrollIntoView:()=>scrolls++}:null};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<Discover {...props}/>,options);});
  try{assert.equal(focuses,1);assert.equal(scrolls,1);await act(async()=>renderer.update(<Discover {...props} requestedFocusResult="stale-result"/>));assert.equal(focuses,1);await act(async()=>renderer.unmount());await act(async()=>{renderer=create(<Discover {...props}/>,options);});assert.equal(focuses,1);}
  finally{await act(async()=>renderer.unmount());}
  const zero={...search,id:"zero-results",papers:[],fetched_count:0,total_reported:0,ordered_identifiers:[]};
  globalThis.fetch=async input=>{const path=String(input);if(path.includes("/drafts/"))return response({scope:"discover",version:0,data:{},expected_assessment_head:null,updated_at:null});if(path.endsWith("/papers"))return response(zero);if(path.includes("/maps?"))return response({maps:[],jobs:[]});throw new Error(path);};
  await act(async()=>{renderer=create(<Discover {...props} workspace={{...state,id:"zero-results",searches:[{...zero,distinct_count:0}]}} requestedFocusResult={undefined}/>);});
  try{assert.match(text(renderer.root),/No papers matched this query/);assert.ok(renderer.root.findAllByType("a").some(node=>text(node)==="Edit query"));assert.equal(renderer.root.findAllByType("button").some(node=>text(node).startsWith("Prepare & compare")),false);}
  finally{await act(async()=>renderer.unmount());}
});

test("executing a search keeps its focused heading mounted through the matching route and result read",async()=>{
  Object.assign(globalThis,{sessionStorage:storage()});const result=savedSearch("focus-after-execution"),loaded=deferred<Schema<"SearchPreview">>(),draft=draftStore();let state=workspace("focus-after-execution"),location:LocationState={page:"discover",workspace:state.id},headingMounts=0,focuses=0,scrolls=0,posts=0;
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.includes("/drafts/"))return response(draft(path,method,body));if(method==="POST"&&path.endsWith("/searches")){posts++;return response(result);}if(path.endsWith("/papers"))return response(await loaded.promise);if(path.includes("/maps?"))return response({maps:[],jobs:[]});throw new Error(path);};
  let renderer!:ReactTestRenderer;
  const refresh=async()=>{state={...state,searches:[{...result,distinct_count:3}]};renderer.update(view());};
  const navigate:Navigate=async next=>{await flushDrafts();location=next;renderer.update(view());return {status:"success"};};
  const view=()=> <Discover workspace={state} capabilities={capabilities} refresh={refresh} navigate={navigate} requestedSearch={location.search} requestedFocusResult={location.focusResult}/>;
  await act(async()=>{renderer=create(view(),{createNodeMock:(element:any)=>{if(!element.props["data-result-id"])return null;headingMounts++;return {focus:()=>focuses++,scrollIntoView:()=>scrolls++};}});});
  try{await act(async()=>renderer.root.findByType("form").props.onSubmit({preventDefault(){}}));await observed(()=>posts===1&&focuses===1);assert.equal(posts,1);assert.equal(focuses,1);assert.equal(headingMounts,1);await act(async()=>loaded.resolve(result));assert.equal(focuses,1);assert.equal(scrolls,1);assert.equal(headingMounts,1,"a route-bound result read cannot replace the heading after consuming focus");}
  finally{await act(async()=>renderer.unmount());}
});

test("foreground preparation saves the pre-click capture and opens only its exact acknowledged thirty-paper preparation",async context=>{
  context.mock.timers.enable({apis:["setTimeout"]});Object.assign(globalThis,{sessionStorage:storage()});const f=research("foreground-exact",30),gate=deferred<void>(),draft=draftStore(),writes:any[]=[],destinations:LocationState[]=[],published:string[]=[];
  const initial={...f.state,source_revision:0,current_preparation_id:null,preparations:[]};
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.includes("/drafts/")){if(method==="PUT")writes.push(structuredClone(body.data));return response(draft(path,method,body));}if(path.includes("/collection-preparation-jobs?"))return response({jobs:[]});if(method==="POST")return response({job:f.job(),reused:false});if(path.includes("/collection-preparation-jobs/"))return response(f.job({status:"succeeded",result_preparation_id:f.preparation.id,result_source_revision:1,progress_completed:30}));if(path.includes("/source-preparations/"))return response({...f.preparation,sources:f.sources.slice(0,1)});if(path.endsWith("/"+f.state.id))return response(f.state);throw new Error(path);};
  const props={workspace:initial,collectionRef:f.collectionRef,papers:f.papers,selectedPaperIds:[...f.preparation.selected_paper_ids],selectionReady:true,maxSources:30,flushSelection:()=>gate.promise,refresh:async()=>{},onPublished:(value:Schema<"CollectionPreparationView">)=>published.push(value.id),question:"CLICKED QUESTION",navigate:async(next:LocationState)=>{destinations.push(next);return {status:"success" as const};}};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<CollectionPreparationJobs {...props}/>);});
  try{
    let submission!:Promise<void>;act(()=>{submission=button(renderer,"Prepare & compare (30)").props.onClick();});assert.equal(writes.length,0);
    await act(async()=>renderer.update(<CollectionPreparationJobs {...props} selectedPaperIds={[f.papers[29].id]} question="LATER QUESTION"/>));await act(async()=>{gate.resolve();await submission;});assert.equal(writes.length,2);assert.equal(writes[0].question,"CLICKED QUESTION");assert.deepEqual(writes[0].selected_paper_ids,f.preparation.selected_paper_ids);assert.equal(writes[0].job_id,null);assert.equal(writes[1].job_id,f.job().id);
    await act(async()=>context.mock.timers.tick(1500));assert.deepEqual(published,[f.preparation.id]);assert.equal(destinations.length,1);assert.equal(destinations[0].preparation,f.preparation.id);assert.equal(destinations[0].setup,"new");assert.match(destinations[0].handoff!,/^comparison-handoff:/);assert.equal(writes[2].preparation_id,f.preparation.id);assert.equal(writes[2].selected_paper_ids.length,30);assert.equal(writes[2].question,"CLICKED QUESTION");
  }finally{await act(async()=>renderer.unmount());}
});

test("reopened completed jobs stay ready and exact current reuse adds no source/job request on continue",async()=>{
  const f=research("reopened-ready"),draft=draftStore(),calls:{path:string;method:string}[]=[],destinations:LocationState[]=[];
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;calls.push({path,method});if(path.endsWith("/session"))return response({csrf_token:"software"});if(path.includes("/drafts/"))return response(draft(path,method,body));if(path.includes("/collection-preparation-jobs?"))return response({jobs:[f.job({status:"succeeded",result_preparation_id:f.preparation.id,result_source_revision:1})]});if(path.includes("/source-preparations/"))return response(f.preparation);if(path.endsWith("/"+f.state.id))return response(f.state);throw new Error(path);};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<CollectionPreparationJobs workspace={f.state} collectionRef={f.collectionRef} papers={f.papers} selectedPaperIds={f.preparation.selected_paper_ids} selectionReady maxSources={30} flushSelection={async()=>{}} refresh={async()=>{}} onPublished={()=>{}} navigate={async next=>{destinations.push(next);}}/>);});
  try{assert.equal(destinations.length,0);assert.ok(calls.every(call=>call.method==="GET"));const readCount=calls.filter(call=>call.path.includes("/source-preparations/")).length;await act(async()=>button(renderer,"Continue to comparison (3)").props.onClick());assert.equal(destinations.length,1);assert.equal(calls.some(call=>call.method==="POST"),false);assert.equal(calls.filter(call=>call.path.includes("/source-preparations/")).length,readCount);}
  finally{await act(async()=>renderer.unmount());}
});
