import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Compare from "../components/compare.tsx";
import {emptyCell} from "../lib/board-drafts.tsx";
import {flushDrafts} from "../lib/drafts.tsx";
import type {Schema} from "../lib/api.ts";

const storage=new Map<string,string>();
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,sessionStorage:{getItem:(key:string)=>storage.get(key)??null,setItem:(key:string,value:string)=>storage.set(key,value),removeItem:(key:string)=>storage.delete(key)}});
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");
function button(renderer:ReactTestRenderer,label:string){const result=renderer.root.findAllByType("button").find(node=>text(node)===label);assert.ok(result,"Missing button: "+label);return result;}
function disabled(node:ReactTestInstance){for(let parent:ReactTestInstance|null=node;parent;parent=parent.parent)if(parent.props.disabled)return true;return false;}
function control(renderer:ReactTestRenderer,label:string){const result=renderer.root.findAllByType("label").find(node=>node.children.some(child=>child===label));assert.ok(result,"Missing field: "+label);return result.findByType("textarea");}
async function observed(check:()=>boolean,label:string){const deadline=Date.now()+5000;while(!check()){assert.ok(Date.now()<deadline,"Unobserved outcome: "+label);await act(async()=>{await new Promise<void>(resolve=>setImmediate(resolve));});}}
function ready(renderer:ReactTestRenderer){const navigation=renderer.root.findAllByProps({"aria-label":"Cell review steps"})[0];return !!navigation&&navigation.findAllByType("button").every(node=>!disabled(node));}
async function click(renderer:ReactTestRenderer,label:string){await observed(()=>ready(renderer)&&!disabled(button(renderer,label)),label+" ready");await act(async()=>{await button(renderer,label).props.onClick();});await observed(()=>ready(renderer),label+" settled");}
const position=(renderer:ReactTestRenderer)=>text(renderer.root.findByProps({"aria-label":"Current paper and field"}));
const destination=(renderer:ReactTestRenderer)=>text(renderer.root.findByProps({"aria-label":"Next unfinished cell destination"}));

async function fixture({papers=1,historical=false,paper="p1",field="f1",completed=[] as string[]}={}){
 const id="paper-context-"+crypto.randomUUID(),date="2026-10-26T00:00:00Z";
 const reports=Array.from({length:papers},(_,index)=>({id:"p"+(index+1),title:"SYNTHETIC report "+(index+1),authors:["Software fixture"],year:2026,pmid:null,doi:null,pmcid:null,url:null}));
 const fields=[1,2,3].map(n=>({id:"f"+n,revision_id:"field-"+n,label:"Field "+n,subquestion:"SYNTHETIC question "+n}));
 const sources=reports.map((report,index)=>({source_id:"s"+(index+1),paper_id:report.id,version:"v1",source_sha256:"a".repeat(64),blocks_sha256:"b".repeat(64),parser_id:"synthetic",source_type:"abstract",status:"abstract_only",block_count:1}));
 const definition={board_id:"board",revision_id:"revision",workspace_id:id,parent_revision_id:null,search_id:"search",search_sha256:"c".repeat(64),question:"SYNTHETIC paper and field context",question_sha256:"d".repeat(64),preparation_id:"prep",source_revision:1,source_manifest_sha256:"e".repeat(64),papers:reports,paper_ids:reports.map(report=>report.id),sources,fields,retrieval_profile:{method:"lexical"},retrieval_profile_sha256:"f".repeat(64),created_at:date};
 const saved=(paper_id:string,field_id:string)=>({...emptyCell(),id:"saved-"+paper_id+field_id,board_id:"board",board_revision_id:"revision",paper_id,field_id,field_revision_id:"field-"+field_id.slice(1),supersedes_id:null,reason:"SYNTHETIC earlier software entry",missing_information:"No scientific value assessed",reference_integrity:"not_applicable",review_state:"single_human_self_declared_not_independently_verified",created_at:date});
 const view={definition,current_revision_id:historical?"newer":"revision",freshness:historical?"historical":"current",freshness_reasons:historical?["Historical definition"]:[],cells:reports.flatMap(report=>fields.map(item=>({paper_id:report.id,field_id:item.id,head:completed.includes(report.id+"/"+item.id)?saved(report.id,item.id):null as ReturnType<typeof saved>|null,draft_version:0}))),definitions:[{board_id:"board",revision_id:"revision",question:definition.question,paper_count:papers,field_count:3,created_at:date}],limits:{max_fields:6}};
 const workspace={id,question:definition.question,mode:"saved_example",created_at:date,source_revision:1,current_preparation_id:"prep",selected_paper_ids:definition.paper_ids,current_run_id:null,current_assessment_ids:{},searches:[],preparations:[{id:"prep",search_id:"search",selected_paper_ids:definition.paper_ids,source_revision:1,prepared_at:date}],runs:[],assessments:[]} as unknown as Schema<"WorkspaceSummary">;
 const drafts=new Map<string,any>(),hints=new Map<string,any>(),requests:{route:string;method:string;body:any}[]=[],navigation:any[]=[],submissions:any[]=[];
 let conflict=false,renderer!:ReactTestRenderer,mounted=false;
 globalThis.fetch=async(url,options)=>{
  const raw=String(url),route=new URL(raw,"http://fixture").pathname,method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):null;requests.push({route,method,body});
  if(route.endsWith("/session"))return response({csrf_token:"synthetic-context"});
  if(route.endsWith("/boards"))return response({boards:view.definitions,limits:{max_fields:6}});
  if(route.endsWith("/boards/board"))return response(view);
  if(route.includes("/drafts/board-editor%3A")){
   const old=hints.get(route)??{version:0,data:{},expected_assessment_head:null};if(method==="GET")return response(old);
   assert.equal(body.version,old.version);const record={...body,version:old.version+1};hints.set(route,record);return response(record);
  }
  if(route.includes("/drafts/")){
   const match=route.match(/\/drafts\/([^/]+)\/([^/]+)$/)!;assert.ok(match);
   const key=decodeURIComponent(match[1])+"/"+decodeURIComponent(match[2]);
   const cell=view.cells.find(item=>key===item.paper_id+"/"+item.field_id)!;
   const old=drafts.get(key)??{board_id:"board",board_revision_id:"revision",paper_id:cell.paper_id,field_id:cell.field_id,version:0,expected_cell_head_id:cell.head?.id??null,data:emptyCell(),updated_at:null};
   if(method==="GET")return response(old);
   if(conflict)return response({detail:{code:"stale_draft",message:"SYNTHETIC draft conflict; values retained"}},409);
   assert.equal(body.version,old.version);const record={...old,version:old.version+1,expected_cell_head_id:body.expected_cell_head_id,data:body.data};drafts.set(key,record);return response(record);
  }
  if(route.endsWith("/cell-revisions")){
   const key=body.paper_id+"/"+body.field_id,record=drafts.get(key);assert.ok(record);assert.equal(body.draft_version,record.version);
   const row={...saved(body.paper_id,body.field_id),...record.data,id:"new-"+submissions.length};submissions.push(row);
   view.cells.find(cell=>key===cell.paper_id+"/"+cell.field_id)!.head=row;drafts.delete(key);return response(row);
  }
  assert.fail("Unexpected source/action request: "+method+" "+route);
 };
 const navigate=async(value:unknown)=>{try{await flushDrafts();navigation.push(value);return {status:"success" as const};}catch(error){return {status:"blocked" as const,message:(error as Error).message};}};
 async function mount(){await act(async()=>{renderer=create(<Compare workspace={workspace} requestedBoard="board" requestedPaper={paper} requestedField={field} navigate={navigate}/>);});mounted=true;await observed(()=>ready(renderer),"initial editor ready");}
 await mount();
 async function close(){if(!mounted)return;await act(async()=>{if(conflict)await flushDrafts().catch(()=>{});else await flushDrafts();renderer.unmount();});mounted=false;}
 async function submitNull(){await click(renderer,"Continue with notes or missing information");await act(async()=>{control(renderer,"Reason").props.onChange({target:{value:"SYNTHETIC interface check only"}});control(renderer,"Missing information").props.onChange({target:{value:"No scientific value entered"}});});await click(renderer,"Review entry before saving");await click(renderer,"Save reviewed entry");await observed(()=>renderer.root.findAllByProps({"aria-label":"Next unfinished cell destination"}).length===1,"saved destination preview");}
 return {get renderer(){return renderer;},requests,navigation,submissions,drafts,mount,close,submitNull,blockDraft(){conflict=true;}};
}

function noResearchActions(requests:{route:string;method:string}[]){assert.equal(requests.some(request=>/\/(?:candidates|sources|preparation-jobs|source-preparations|hybrid-index|hybrid-runs|proposals|prepare-generation)(?:\/|$)/.test(request.route)),false);}

test("one paper's three fields retain their exact context across steps and same-paper navigation",async()=>{
 const f=await fixture();try{
  assert.equal(position(f.renderer),"Paper 1 of 1 · Field 1 of 3");
  const identity=f.renderer.root.findByProps({className:"cell-editor-identity"});assert.match(text(identity),/SYNTHETIC report 1/);assert.match(text(identity),/Abstract only/);assert.match(text(identity),/one paper\. All 3 fields describe this same report/);
  assert.equal(f.requests.some(request=>request.method!=="GET"),false,"context projection is read-only on open");
  for(let index=1;index<=3;index++){
   assert.equal(position(f.renderer),`Paper 1 of 1 · Field ${index} of 3`);
   await f.submitNull();
   assert.equal(position(f.renderer),`Paper 1 of 1 · Field ${index} of 3`,"review step retains the current identity");
   if(index<3){assert.equal(destination(f.renderer),`Next: another field in the same paper — Field ${index+1} for SYNTHETIC report 1.`);await click(f.renderer,"Next unfinished cell");}
   else{assert.equal(destination(f.renderer),"No unfinished cells remain.");assert.equal(disabled(button(f.renderer,"Next unfinished cell")),true);}
  }
  assert.equal(f.submissions.length,3);assert.ok(f.submissions.every(row=>row.paper_id==="p1"&&row.semantic_assessment==="unassessed"&&row.references.length===0));noResearchActions(f.requests);
 }finally{await f.close();}
});

test("the next-cell preview distinguishes a different paper and matches its actual destination",async()=>{
 const f=await fixture({papers:2,field:"f3",completed:["p1/f1","p1/f2"]});try{
  assert.equal(position(f.renderer),"Paper 1 of 2 · Field 3 of 3");await f.submitNull();
  assert.equal(destination(f.renderer),"Next: a different paper — Field 1 for SYNTHETIC report 2.");
  await click(f.renderer,"Next unfinished cell");assert.equal(position(f.renderer),"Paper 2 of 2 · Field 1 of 3");assert.match(text(f.renderer.root.findByProps({className:"cell-editor-identity"})),/SYNTHETIC report 2/);assert.equal(f.submissions.length,1);noResearchActions(f.requests);
 }finally{await f.close();}
});

test("historical and reopened cells show the retained paper/field context without writing navigation",async()=>{
 const f=await fixture({papers:2,paper:"p2",field:"f2",historical:true});try{
  for(const label of ["2. Comment & judge","3. Review & save"]){await click(f.renderer,label);assert.equal(position(f.renderer),"Paper 2 of 2 · Field 2 of 3");}
  assert.match(text(f.renderer.root.findByProps({className:"cell-editor-identity"})),/HISTORICAL/);await f.close();await f.mount();assert.equal(position(f.renderer),"Paper 2 of 2 · Field 2 of 3");assert.equal(f.requests.some(request=>request.method!=="GET"),false);noResearchActions(f.requests);
 }finally{await f.close();}
});

test("a draft conflict blocks leaving and preserves the visible source context and typed note",async()=>{
 const f=await fixture({field:"f2"});try{
  await click(f.renderer,"Continue with notes or missing information");await act(async()=>{control(f.renderer,"Manual cell value").props.onChange({target:{value:"SYNTHETIC retained unsent note"}});});
  f.blockDraft();await click(f.renderer,"Back to table");
  assert.equal(position(f.renderer),"Paper 1 of 1 · Field 2 of 3");assert.equal(control(f.renderer,"Manual cell value").props.value,"SYNTHETIC retained unsent note");assert.match(text(f.renderer.root),/SYNTHETIC draft conflict/);assert.equal(f.navigation.length,0);assert.equal(f.submissions.length,0);noResearchActions(f.requests);
 }finally{await f.close();}
});
