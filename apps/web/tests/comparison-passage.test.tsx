import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Evidence from "../components/evidence";
import Compare from "../components/compare";
import {emptyCell} from "../lib/board-drafts";
import {flushDrafts} from "../lib/drafts";
import {comparisonPassageScope,comparisonTablePosition,matchesComparisonPassageRun,matchesComparisonPassageSummary,type ComparisonPassageContext} from "../lib/comparison-passage";
import type {LocationState} from "../components/workspace-app";
import type {Schema} from "../lib/api";
import {research} from "./collection-research-fixtures";
import {response,storage} from "./import-collection-fixtures";
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(n:ReactTestInstance):string=>n.children.map(c=>typeof c==="string"?c:text(c)).join("");
const button=(r:ReactTestRenderer,label:string)=>r.root.findAllByType("button").find(n=>text(n)===label)!;
const control=(r:ReactTestRenderer,label:string)=>r.root.findAllByType("label").find(n=>n.children[0]===label)!.findAll(n=>n.type==="textarea"||n.type==="input"||n.type==="select")[0];
async function observed(check:()=>boolean){const deadline=Date.now()+5000;while(!check()){assert.ok(Date.now()<deadline,"expected acknowledged navigation was not observed");await act(async()=>{await new Promise<void>(resolve=>setImmediate(resolve));});}}
function fixture(name:string){
 const f=research("passage-flow-"+name),paper=f.papers[0];
 const sources=f.sources.map(s=>({source_id:s.id,paper_id:s.paper_id,version:s.version,source_sha256:s.source_sha256,blocks_sha256:s.blocks_sha256,parser_id:s.parser_id,source_type:"abstract" as const,status:s.status,block_count:s.block_count}));
 const identity={board_id:"board",board_revision_id:"revision",paper_id:paper.id,field_id:"diet"};
 const context={...identity,preparation_id:f.preparation.id,source_revision:1,source_manifest_sha256:"f".repeat(64),board_paper_ids:f.papers.map(p=>p.id),paper_ids:[paper.id],sources:[sources[0]],papers:[paper],question:"What dietary exposure was measured?",board_question:"SOFTWARE TEST comparison question",field_revision_id:"diet-revision",field_label:"Diet"} as ComparisonPassageContext;
 const definition={board_id:"board",revision_id:"revision",question:context.board_question,preparation_id:context.preparation_id,source_revision:1,source_manifest_sha256:context.source_manifest_sha256,collection_ref:f.collectionRef,paper_ids:context.board_paper_ids,papers:f.papers,sources,fields:[{id:"diet",revision_id:"diet-revision",label:"Diet",subquestion:context.question}],retrieval_profile:{method:"lexical"},created_at:f.preparation.prepared_at};
 const summary={board_id:"board",revision_id:"revision",question:definition.question,paper_count:3,field_count:1,created_at:definition.created_at};
 const board={definition,current_revision_id:"revision",freshness:"current",freshness_reasons:[],cells:f.papers.map(p=>({paper_id:p.id,field_id:"diet",head:null,draft_version:0})),definitions:[summary],limits:{max_fields:6}};
 const run={...f.run,id:"matched",question:context.question,passages:[f.run.passages[0]],parameters:{top_k:5,board_passage_context:context}};
 const workspace={...f.state,current_run_id:"unrelated",runs:[{id:"unrelated",preparation_id:context.preparation_id,source_revision:1,question:"Unrelated",created_at:run.created_at,passage_count:3,current:true,collection_ref:f.collectionRef,search_id:null,board_context:null}]} as Schema<"WorkspaceSummary">;
 const reference={...sources[0],source_version:sources[0].version,block_id:run.passages[0].anchor.block_id,start:0,end:f.quote.length,quote:f.quote,id:"reference",locator:{section:"Abstract"},integrity:"checked"};
 const returned={reference,paper,source:sources[0],freshness:"current",block:{source_id:sources[0].source_id,paper_id:paper.id,block_id:reference.block_id,ordinal:0,locator:reference.locator,start:0,end:f.quote.length,total_characters:f.quote.length,text:f.quote,omitted_before:0,omitted_after:0,reference},run_id:run.id,passage_id:run.passages[0].id,passage_start:0,passage_end:f.quote.length,passage_omitted_after:0};
 let cell={version:0,expected_cell_head_id:null,data:emptyCell()},conflict=false,deny=false;
 const calls:{path:string;method:string;body:any}[]=[],locations:LocationState[]=[],drafts=new Map<string,any>();
 Object.assign(globalThis,{sessionStorage:storage()});
 globalThis.fetch=async(input,options)=>{
  const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):null;calls.push({path,method,body});
  if(path.endsWith("/session"))return response({csrf_token:"software"});
  if(path.includes("/passage-search-context?"))return response(context);
  if(path.includes("/passage-source-context?"))return deny?response({detail:{code:"wrong_paper",message:"Passage does not belong to this board cell."}},409):response(returned);
  if(path.endsWith("/boards"))return response({boards:[summary],limits:{max_fields:6}});
  if(/\/boards\/board(?:\?|$)/.test(path))return response(board);
  if(path.includes("/boards/board/drafts/")){if(method==="PUT"){assert.equal(body.version,cell.version);cell={...cell,version:cell.version+1,data:body.data};}return response(cell);}
  if(path.includes("/drafts/")){
   const key=path.slice(path.indexOf("/drafts/")+8);let saved=drafts.get(key)??{version:0,data:{},expected_assessment_head:null};
   if(method==="PUT"){if(conflict)return response({detail:{code:"draft_conflict",message:"Newer search draft in another tab."}},409);assert.equal(body.version,saved.version);saved={...body,version:saved.version+1};drafts.set(key,saved);}return response(saved);
  }
  if(path.endsWith("/evidence-runs")){assert.deepEqual(body.board_context,identity);assert.equal(body.expected_preparation_id,context.preparation_id);return response(run);}
  const match=path.match(/\/runs\/([^/?]+)(\/papers)?/);
  if(match){const selected=match[1].startsWith("matched")?{...run,id:match[1]}:{...f.run,id:"unrelated",parameters:{}};return response(match[2]?{...f.runPapers,run_id:selected.id}:{...f.view,run:selected,current:true});}
  throw new Error("Unexpected action "+method+" "+path);
 };
 const navigate=async(next:LocationState)=>{try{await flushDrafts();locations.push(next);return {status:"success" as const};}catch(e){return {status:"blocked" as const,message:(e as Error).message};}};
 return {f,paper,context,identity,calls,locations,drafts,workspace,run,returned,navigate,getCell:()=>cell,setConflict:()=>{conflict=true;},deny:()=>{deny=true;}};
}

test("board and field passage entry points carry IDs and save the cell draft without executing retrieval",async()=>{
 const f=fixture("entry");let r!:ReactTestRenderer;await act(async()=>{r=create(<Compare workspace={f.workspace} requestedBoard="board" navigate={f.navigate}/>);});
 try{
  await act(async()=>button(r,"Search passages for this comparison").props.onClick());assert.equal(f.locations.at(-1)?.revision,"revision");assert.equal(f.locations.at(-1)?.paper,undefined);
  await act(async()=>r.root.findByProps({"aria-label":"Diet for "+f.paper.title}).props.onClick());
  await act(async()=>control(r,"Manual cell value").props.onChange({target:{value:"Retained cell draft"}}));
  await act(async()=>button(r,"Open passage search for this field").props.onClick());
  assert.equal(f.getCell().data.value,"Retained cell draft");assert.equal(f.locations.at(-1)?.paper,f.paper.id);assert.equal(f.locations.at(-1)?.field,"diet");assert.ok(button(r,"Find excerpts in this paper"));
  assert.equal(f.calls.some(c=>/evidence-runs|candidates|preparation-jobs|proposal-runs/.test(c.path)),false);assert.equal(JSON.stringify(f.locations).includes(f.context.question),false);
 }finally{await act(async()=>r.unmount());}
});

test("scoped query/count/run survive reopening; return opens exact cell source without attaching or changing judgments",async()=>{
 const f=fixture("roundtrip");let r!:ReactTestRenderer;const mount=async()=>act(async()=>{r=create(<Evidence workspace={f.workspace} comparison={f.identity} refresh={async()=>{}} navigate={f.navigate}/>);});await mount();
 try{
  assert.equal(control(r,"Evidence question").props.value,f.context.question);assert.equal(f.calls.some(c=>c.path.includes("/runs/unrelated")),false);assert.equal(f.calls.some(c=>c.method!=="GET"),false);
  await act(async()=>control(r,"Evidence question").props.onChange({target:{value:"Edited scoped query"}}));await act(async()=>control(r,"Maximum passages for next search").props.onChange({target:{value:"20"}}));
  await act(async()=>r.root.findByType("form").props.onSubmit({preventDefault(){}}));
  await observed(()=>f.locations.at(-1)?.run==="matched");
  assert.equal(f.calls.filter(c=>c.path.endsWith("/evidence-runs")).length,1);assert.equal(f.calls.find(c=>c.path.endsWith("/evidence-runs"))?.body.top_k,20);assert.equal(f.calls.some(c=>c.path.endsWith("/drafts/evidence")),false);
  await act(async()=>r.unmount());await mount();assert.equal(control(r,"Evidence question").props.value,"Edited scoped query");assert.equal(control(r,"Maximum passages for next search").props.value,20);
  assert.ok(button(r,"Open in comparison cell · passage 1"),text(r.root)+JSON.stringify(f.calls));
  await act(async()=>button(r,"Open in comparison cell · passage 1").props.onClick());const target=f.locations.at(-1)!;assert.equal(target.passage,f.run.passages[0].id);assert.equal(target.run,"matched");
  await act(async()=>r.unmount());await act(async()=>{r=create(<Compare workspace={f.workspace} requestedBoard="board" requestedRevision="revision" requestedPaper={target.paper} requestedField={target.field} requestedRun={target.run} requestedPassage={target.passage} requestedReturn="cell" navigate={f.navigate}/>);});
  assert.equal(r.root.findByType("mark").children.join(""),f.f.quote);assert.equal(f.getCell().version,0);assert.deepEqual(f.getCell().data.references,[]);assert.equal(f.getCell().data.semantic_assessment,"unassessed");assert.equal(f.calls.some(c=>c.path.endsWith("/cell-revisions")),false);
 }finally{await act(async()=>r.unmount());}
});

test("unrelated requested run is rejected instead of displayed or persisted",async()=>{
 const f=fixture("mismatch");let r!:ReactTestRenderer;await act(async()=>{r=create(<Evidence workspace={f.workspace} comparison={f.identity} requestedRun="unrelated" refresh={async()=>{}} navigate={f.navigate}/>);});
 try{assert.match(text(r.root),/does not match this comparison/);assert.equal(r.root.findAllByProps({className:"passage"}).length,0);assert.equal(f.calls.some(c=>c.method!=="GET"),false);}finally{await act(async()=>r.unmount());}
});

test("wrong-paper return has an explicit failure and never opens or attaches evidence",async()=>{
 const f=fixture("wrongpaper");f.deny();let r!:ReactTestRenderer;await act(async()=>{r=create(<Compare workspace={f.workspace} requestedBoard="board" requestedPaper={f.paper.id} requestedField="diet" requestedRun="matched" requestedPassage="wrong-paper" navigate={f.navigate}/>);});
 try{assert.match(text(r.root),/does not belong to this board cell/);assert.equal(r.root.findAllByType("mark").length,0);assert.equal(f.getCell().version,0);assert.equal(f.calls.some(c=>c.method!=="GET"),false);}finally{await act(async()=>r.unmount());}
});

test("a search draft save conflict blocks return and retains edits without retrieval",async()=>{
 const f=fixture("conflict");let r!:ReactTestRenderer;await act(async()=>{r=create(<Evidence workspace={f.workspace} comparison={f.identity} refresh={async()=>{}} navigate={f.navigate}/>);});
 try{await act(async()=>control(r,"Evidence question").props.onChange({target:{value:"Retained conflicting query"}}));f.setConflict();await act(async()=>button(r,"Back to cell").props.onClick());assert.equal(f.locations.length,0);assert.equal(control(r,"Evidence question").props.value,"Retained conflicting query");assert.match(text(r.root),/Newer search draft/);assert.equal(f.calls.some(c=>c.path.endsWith("/evidence-runs")),false);}finally{await act(async()=>r.unmount());}
});

test("draft scopes, source bindings and bounded identity-bound table positions remain separate",()=>{
 const f=fixture("identity");assert.notEqual(comparisonPassageScope(f.identity),comparisonPassageScope({...f.identity,paper_id:"other"}));assert.match(comparisonPassageScope({...f.identity,field_id:"diet:字段"}),/646965743a/);
 assert.equal(matchesComparisonPassageRun(f.run,f.context),true);assert.equal(matchesComparisonPassageRun({...f.run,passages:[f.f.run.passages[1]]},f.context),false);assert.equal(matchesComparisonPassageRun(f.run,{...f.context,source_manifest_sha256:"0".repeat(64)}),false);
 assert.equal(matchesComparisonPassageSummary({...f.workspace.runs[0],board_context:f.identity},f.context),true);assert.equal(matchesComparisonPassageSummary(f.workspace.runs[0],f.context),false);
 const p={workspace:"w",board:"b",revision:"r",left:123,top:456};assert.deepEqual(comparisonTablePosition(p,"w","b","r"),p);assert.equal(comparisonTablePosition(p,"other","b","r"),null);assert.equal(comparisonTablePosition({...p,left:Infinity},"w","b","r"),null);
});

test("Back to an older matching URL run persists that validated selection without replacing the edited query",async()=>{
 const f=fixture("backrun");let r!:ReactTestRenderer;
 const component=(requestedRun?:string)=><Evidence workspace={f.workspace} comparison={f.identity} requestedRun={requestedRun} refresh={async()=>{}} navigate={f.navigate}/>;
 await act(async()=>{r=create(component());});
 try{
  await act(async()=>control(r,"Evidence question").props.onChange({target:{value:"Edited next query survives Back"}}));
  await act(async()=>r.root.findByType("form").props.onSubmit({preventDefault(){}}));await observed(()=>f.locations.at(-1)?.run==="matched");
  await act(async()=>r.update(component("matched-older")));await act(async()=>flushDrafts());
  assert.equal(control(r,"Evidence question").props.value,"Edited next query survives Back");
  assert.ok([...f.drafts.values()].some(draft=>draft.data.selected_run_id==="matched-older"));
  await act(async()=>r.unmount());await act(async()=>{r=create(component());});
  assert.equal(control(r,"Matching saved passage run").props.value,"matched-older");assert.equal(control(r,"Evidence question").props.value,"Edited next query survives Back");
  assert.equal(f.calls.filter(c=>c.path.endsWith("/evidence-runs")).length,1,"Back/reopen does not repeat retrieval");
 }finally{await act(async()=>r.unmount());}
});

test("return restores the original table position and keyboard focus after the board definition loads",async()=>{
 const f=fixture("focus"),previous=(globalThis as any).window,focus:string[]=[],scroll:number[]=[];
 const selected={dataset:{boardCell:f.paper.id+":diet"},focus(){focus.push("original cell");},scrollIntoView(){}};
 const table={scrollLeft:0,querySelectorAll(){return [selected];},focus(){focus.push("table");},scrollIntoView(){}};
 let y=0;
 const history={state:{comparisonPosition:{workspace:f.workspace.id,board:"board",revision:"revision",left:125,top:333}},replaceState(state:any){this.state=state;}};
 Object.assign(globalThis,{window:{history,location:{href:"http://localhost/"},get scrollY(){return y;},scrollTo(value:{top:number}){y=value.top;scroll.push(y);},addEventListener(){},removeEventListener(){}}});
 let r!:ReactTestRenderer;
 try{
  await act(async()=>{r=create(<Compare workspace={f.workspace} requestedBoard="board" requestedPaper={f.paper.id} requestedField="diet" requestedReturn="cell" navigate={f.navigate}/>,{createNodeMock(element){return (element.props as {className?:string}).className==="board-table-scroll"?table:{focus(){focus.push("editor");},scrollIntoView(){}};}});});
  assert.equal(table.scrollLeft,125);assert.equal(scroll.at(-1),333);assert.equal(focus.at(-1),"editor","a returned cell opens the visible focused editor instead of focusing its hidden table button");
  await act(async()=>button(r,"Open passage search for this field").props.onClick());assert.deepEqual(history.state.comparisonPosition,{workspace:f.workspace.id,board:"board",revision:"revision",left:125,top:333});
 }finally{if(r)await act(async()=>r.unmount());if(previous===undefined)delete (globalThis as any).window;else Object.assign(globalThis,{window:previous});}
});
