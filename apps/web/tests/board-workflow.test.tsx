import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import Compare from "../components/compare.tsx";
import {emptyCell} from "../lib/board-drafts.tsx";
import type {Schema} from "../lib/api.ts";
const pending=new Map<string,string>();
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,sessionStorage:{getItem:(key:string)=>pending.get(key)??null,setItem:(key:string,value:string)=>pending.set(key,value),removeItem:(key:string)=>pending.delete(key)}});
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}});
function content(node:ReactTestInstance):string{return node.children.map(child=>typeof child==="string"?child:content(child)).join("");}
function button(renderer:ReactTestRenderer,label:string){const value=renderer.root.findAllByType("button").find(item=>content(item)===label);assert.ok(value,`Missing button: ${label}`);return value;}
function disabled(node:ReactTestInstance):boolean {let current:ReactTestInstance|null=node;while(current){if(current.props.disabled)return true;current=current.parent;}return false;}
function control(renderer:ReactTestRenderer,label:string,type:"textarea"|"select"|"input"="textarea"){const value=renderer.root.findAllByType("label").find(item=>item.children.some(child=>typeof child==="string"&&child===label));assert.ok(value,`Missing control: ${label}`);return value.findByType(type);}
const text="女性😀 participants were Chinese women. Diet was assessed using a questionnaire.";
const fieldList=[{id:"population",revision_id:"fp",label:"Population",subquestion:"What participants were studied?"},{id:"design",revision_id:"fd",label:"Design",subquestion:"What design was used?"},{id:"exposure",revision_id:"fe",label:"Exposure",subquestion:"What diet was measured?"}];

async function fixture(id:string,{historical=false}={}){
  const papers=[1,2,3].map(i=>({id:"p"+i,title:`SOFTWARE TEST Report ${i}`,authors:["Fixture author"],year:2026,pmid:String(i),doi:null,pmcid:null,url:"https://pubmed.ncbi.nlm.nih.gov/"+i+"/"}));
  const sources=papers.map((paper,i)=>({source_id:"s"+(i+1),paper_id:paper.id,version:"v1",source_sha256:"a".repeat(64),blocks_sha256:"b".repeat(64),parser_id:"fixture",source_type:i===2?"abstract":"full_text",status:i===2?"abstract_only":"full_text_available",block_count:1}));
  const definition={board_id:"b",revision_id:"r",workspace_id:id,parent_revision_id:null,search_id:"search",search_sha256:"c".repeat(64),question:"SOFTWARE TEST question",question_sha256:"d".repeat(64),preparation_id:"prep",source_revision:1,source_manifest_sha256:"e".repeat(64),papers,paper_ids:papers.map(p=>p.id),sources,fields:fieldList,retrieval_profile:{method:"lexical"},retrieval_profile_sha256:"f".repeat(64),created_at:"2026-10-21T00:00:00Z"};
  const summary={board_id:"b",revision_id:"r",question:definition.question,paper_count:3,field_count:3,created_at:definition.created_at};
  const view={definition,current_revision_id:"r",freshness:historical?"historical":"current",freshness_reasons:historical?["Definition is historical."]:[],cells:papers.flatMap(paper=>fieldList.map(field=>({paper_id:paper.id,field_id:field.id,head:null as unknown,draft_version:0}))),definitions:[summary],limits:{max_fields:6}};
  const workspace={id,question:definition.question,mode:"live",created_at:definition.created_at,source_revision:1,current_preparation_id:"prep",selected_paper_ids:papers.map(p=>p.id),current_run_id:null,current_assessment_ids:{},searches:[{id:"search"}],preparations:[{id:"prep",search_id:"search",selected_paper_ids:papers.map(p=>p.id),source_revision:1,prepared_at:definition.created_at}],runs:[],assessments:[]} as unknown as Schema<"WorkspaceSummary">;
  const drafts=new Map<string,{board_id:string;board_revision_id:string;paper_id:string;field_id:string;version:number;expected_cell_head_id:string|null;data:ReturnType<typeof emptyCell>;updated_at:null}>();
  const revisions:Record<string,unknown>[]=[];const requests:{path:string;method:string;body:Record<string,unknown>|null}[]=[];
  let refForPaper=(paperId:string)=>{const source=sources.find(s=>s.paper_id===paperId)!;return {id:"ref-"+paperId,paper_id:paperId,source_id:source.source_id,source_version:source.version,source_sha256:source.source_sha256,blocks_sha256:source.blocks_sha256,block_id:"block-"+paperId,start:0,end:Array.from(text).length,quote:text,locator:{section:"Abstract"},integrity:"checked"};};
  globalThis.fetch=async(url,options)=>{
    const path=String(url),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):null;requests.push({path,method,body});
    if(path.endsWith("/session"))return response({csrf_token:"test"});
    if(path.endsWith("/boards"))return response({boards:[summary],limits:{max_fields:6}});
    if(path.endsWith("/boards/b"))return response(view);
    if(path.includes("/drafts/")){
      const match=path.match(/\/drafts\/([^/]+)\/([^/?]+)/)!;const paper_id=decodeURIComponent(match[1]),field_id=decodeURIComponent(match[2]),key=paper_id+"/"+field_id;
      const old=drafts.get(key)??{board_id:"b",board_revision_id:"r",paper_id,field_id,version:0,expected_cell_head_id:null,data:emptyCell(),updated_at:null};
      if(method==="GET")return response(old);
      assert.equal(body.expected_revision_id,"r");assert.equal(body.version,old.version);assert.equal("expected_assessment_head" in body,false);
      const value={...old,version:old.version+1,expected_cell_head_id:body.expected_cell_head_id,data:body.data};drafts.set(key,value);return response(value);
    }
    if(path.endsWith("/candidates")){
      const reference=refForPaper(body.paper_id);return response({id:"candidate-run",board_id:"b",board_revision_id:"r",paper_id:body.paper_id,field_id:body.field_id,field_revision_id:"fe",indexed_blocks:1,matched_blocks:1,returned_count:1,omitted_matched_blocks:0,candidates:[{rank:1,score:1,reference,total_block_characters:Array.from(text).length,omitted_characters:0}]});
    }
    if(path.includes("/sources/")){
      const sourceId=path.match(/\/sources\/([^/]+)/)![1],source=sources.find(s=>s.source_id===sourceId)!;const reference=refForPaper(source.paper_id);return response({board_revision_id:"r",source,freshness:view.freshness,blocks:[{source_id:sourceId,paper_id:source.paper_id,block_id:reference.block_id,ordinal:0,locator:reference.locator,start:0,end:Array.from(text).length,total_characters:Array.from(text).length,text,omitted_before:0,omitted_after:0,reference}],offset:0,limit:3,total_blocks:1});
    }
    if(path.endsWith("/cell-revisions")){
      const key=body.paper_id+"/"+body.field_id,draft=drafts.get(key)!;assert.ok(draft);assert.equal(body.draft_version,draft.version);assert.equal(body.supersedes_id,draft.expected_cell_head_id);
      const reference=refForPaper(body.paper_id);const result={...draft.data,id:"cell-"+(revisions.length+1),board_id:"b",board_revision_id:"r",field_revision_id:"fe",paper_id:body.paper_id,field_id:body.field_id,supersedes_id:body.supersedes_id,references:draft.data.references.map(range=>({...reference,...range,quote:Array.from(text).slice(range.start,range.end).join("")})),inspected_ranges:draft.data.inspected_ranges.map(range=>({...reference,...range,quote:Array.from(text).slice(range.start,range.end).join("")})),reference_integrity:draft.data.references.length?"checked":"not_applicable",review_state:"single_human_self_declared_not_independently_verified",created_at:definition.created_at};
      revisions.push(result);const cell=view.cells.find(c=>c.paper_id===body.paper_id&&c.field_id===body.field_id)!;cell.head={...result,references:result.references.map(({quote,...rest})=>rest),inspected_ranges:result.inspected_ranges.map(({quote,...rest})=>rest)};drafts.delete(key);return response(result);
    }
    if(path.includes("/history?"))return response({items:[...revisions].reverse(),offset:0,limit:10,total:revisions.length});
    if(path.includes("/references/")){const reference=refForPaper("p3"),source=sources[2];return response({reference,paper:papers[2],source,freshness:view.freshness,block:{source_id:source.source_id,paper_id:"p3",block_id:reference.block_id,ordinal:0,locator:reference.locator,start:0,end:Array.from(text).length,total_characters:Array.from(text).length,text,omitted_before:0,omitted_after:0,reference}});}
    assert.fail("Unexpected request "+method+" "+path);
  };
  let renderer!:ReactTestRenderer;
  async function mount(){await act(async()=>{renderer=create(<Compare workspace={workspace} requestedBoard="b" navigate={async()=>{}}/>);});return renderer;}
  await mount();return {renderer,requests,drafts,revisions,mount,view,workspace};
}

test("nine-cell board performs only explicit per-cell retrieval, inspection, manual submission, revision and reopening",async()=>{
  const fixtureState=await fixture("board-workflow");let renderer=fixtureState.renderer;
  const {requests,drafts,revisions}=fixtureState;
  try{
    assert.equal(renderer.root.findAll(node=>node.type==="button"&&String(node.props["aria-label"]??"").includes(" for SOFTWARE TEST Report")).length,9);
    assert.equal(requests.some(request=>request.method!=="GET"),false,"opening a board is read-only");
    await act(async()=>renderer.root.findByProps({"aria-label":"Exposure for SOFTWARE TEST Report 3"}).props.onClick());
    assert.ok(JSON.stringify(renderer.toJSON()).includes("Only the retained abstract is available"));
    await act(async()=>button(renderer,"Retrieve candidates for this cell").props.onClick());
    const retrieval=requests.find(request=>request.path.endsWith("/candidates"))!;assert.equal(retrieval.body?.paper_id,"p3");assert.equal(retrieval.body?.field_id,"exposure");assert.equal(retrieval.body?.top_k,3);
    assert.equal(drafts.size,0,"candidate retrieval does not create an inspection or judgment");
    await act(async()=>button(renderer,"Inspect candidate 1 in exact source").props.onClick());
    assert.equal(drafts.size,0,"opening canonical source does not declare inspection");
    assert.equal(renderer.root.findByType("mark").children.join(""),text,"Unicode code points highlight the exact canonical range");
    await act(async()=>button(renderer,"Mark selected range as inspected").props.onClick());
    await act(async()=>button(renderer,"Add selected range as reference").props.onClick());
    await act(async()=>control(renderer,"Manual cell value").props.onChange({target:{value:"SOFTWARE WALKTHROUGH: diet questionnaire"}}));
    await act(async()=>control(renderer,"Reason").props.onChange({target:{value:"SOFTWARE WALKTHROUGH: inspected exact abstract range; support remains unassessed"}}));
    await act(async()=>control(renderer,"Inspected scope result","select").props.onChange({target:{value:"value_found"}}));
    const form=renderer.root.findAllByType("form").find(form=>form.findAllByType("textarea").some(textarea=>textarea.props.value==="SOFTWARE WALKTHROUGH: diet questionnaire"))!;
    await act(async()=>form.props.onSubmit({preventDefault(){}}));
    assert.equal(revisions.length,1);assert.equal(revisions[0].semantic_assessment,"unassessed");assert.equal((revisions[0].references as unknown[]).length,1);assert.equal(drafts.size,0,"submission consumes acknowledged draft");
    assert.equal(control(renderer,"Manual cell value").parent?.props.disabled,undefined);
    assert.equal(disabled(button(renderer,"Submit revised cell")),true,"submitted cell stays read-only until explicit revision");
    await act(async()=>button(renderer,"Revise saved cell").props.onClick());
    await act(async()=>control(renderer,"Reason").props.onChange({target:{value:"SOFTWARE WALKTHROUGH: explicit second revision"}}));
    await act(async()=>renderer.root.findAllByType("form").at(-1)!.props.onSubmit({preventDefault(){}}));
    assert.equal(revisions.length,2);assert.equal(revisions[1].supersedes_id,"cell-1");
    await act(async()=>button(renderer,"Load immutable cell history").props.onClick());assert.ok(content(renderer.root.findByProps({"aria-label":"Immutable cell history"})).includes("2 of 2 revisions"));
    const csv=renderer.root.findAllByType("a").find(link=>content(link)==="Download board CSV")!;assert.ok(csv.props.href.includes("/boards/b/exports?format=csv"));
    await act(async()=>renderer.unmount());renderer=await fixtureState.mount();
    assert.ok(JSON.stringify(renderer.toJSON()).includes("SOFTWARE WALKTHROUGH: diet questionnaire"));
    await act(async()=>renderer.root.findByProps({"aria-label":"Exposure for SOFTWARE TEST Report 3"}).props.onClick());
    assert.equal(control(renderer,"Reason").props.value,"SOFTWARE WALKTHROUGH: explicit second revision");
    assert.equal(requests.filter(request=>request.path.endsWith("/candidates")).length,1,"reopening does not retrieve again");
  }finally{await act(async()=>renderer.unmount());}
});

test("abstract-only missing information stays null and does not become an unsupported literature-wide absence claim",async()=>{
  const {renderer,revisions}=await fixture("board-missing");
  try{
    await act(async()=>renderer.root.findByProps({"aria-label":"Design for SOFTWARE TEST Report 3"}).props.onClick());
    await act(async()=>button(renderer,"Browse retained source").props.onClick());
    await act(async()=>button(renderer,"Mark selected range as inspected").props.onClick());
    await act(async()=>control(renderer,"Inspected scope result","select").props.onChange({target:{value:"not_found_in_inspected_material"}}));
    await act(async()=>control(renderer,"Reason").props.onChange({target:{value:"SOFTWARE WALKTHROUGH: no allocation detail in the inspected abstract range"}}));
    await act(async()=>control(renderer,"Missing information").props.onChange({target:{value:"Allocation method; full text not retained"}}));
    await act(async()=>renderer.root.findAllByType("form").at(-1)!.props.onSubmit({preventDefault(){}}));
    assert.equal(revisions.length,1);assert.equal(revisions[0].value,null);assert.equal(revisions[0].semantic_assessment,"unassessed");assert.equal(revisions[0].scope_result,"not_found_in_inspected_material");
    assert.ok(content(renderer.root.findByProps({"aria-label":"Design for SOFTWARE TEST Report 3"})).includes("Not found in inspected material"));assert.ok(content(renderer.root.findByProps({"aria-label":"Population for SOFTWARE TEST Report 1"})).includes("Not yet submitted"));
  }finally{await act(async()=>renderer.unmount());}
});

test("historical definitions permit inspection and exports while edits and retrieval remain disabled",async()=>{
  const {renderer,requests}=await fixture("board-historical-workflow",{historical:true});
  try{
    await act(async()=>renderer.root.findByProps({"aria-label":"Population for SOFTWARE TEST Report 1"}).props.onClick());
    assert.equal(button(renderer,"Retrieve candidates for this cell").props.disabled,true);
    await act(async()=>button(renderer,"Browse retained source").props.onClick());
    assert.ok(renderer.root.findByType("mark"));assert.equal(disabled(button(renderer,"Mark selected range as inspected")),true);assert.equal(requests.some(request=>request.method!=="GET"),false);
  }finally{await act(async()=>renderer.unmount());}
});

for(const failOld of [false,true])test(`late definition ${failOld?"failure":"success"} cannot replace a newer revision of the same board`,async()=>{
  const {renderer,view,workspace}=await fixture("board-load-race-"+failOld);
  const originalFetch=globalThis.fetch;let resolveOld!:(value:Response)=>void;const old=new Promise<Response>(resolve=>resolveOld=resolve);
  globalThis.fetch=async(url,options)=>{
    const path=String(url);
    if(path.includes("revision_id=old"))return old;
    if(path.includes("revision_id=new"))return response({...view,definition:{...view.definition,revision_id:"new",question:"CURRENT NEW DEFINITION"}});
    return originalFetch(url,options);
  };
  try{
    await act(async()=>renderer.update(<Compare workspace={workspace} requestedBoard="b" requestedRevision="old" navigate={async()=>{}}/>));
    await act(async()=>renderer.update(<Compare workspace={workspace} requestedBoard="b" requestedRevision="new" navigate={async()=>{}}/>));
    assert.ok(content(renderer.root).includes("CURRENT NEW DEFINITION"));
    await act(async()=>resolveOld(failOld?response({detail:{code:"old_failure",message:"OLD REQUEST FAILED"}},500):response({...view,definition:{...view.definition,revision_id:"old",question:"STALE OLD DEFINITION"}})));
    assert.ok(content(renderer.root).includes("CURRENT NEW DEFINITION"));assert.equal(content(renderer.root).includes("STALE OLD DEFINITION"),false);assert.equal(content(renderer.root).includes("OLD REQUEST FAILED"),false);
  }finally{await act(async()=>renderer.unmount());}
});

test("late source context stays with its original paper and URL cell navigation restores the requested editor",async()=>{
  const {renderer,workspace}=await fixture("board-cell-read-race");
  const originalFetch=globalThis.fetch;let resolveOld!:(value:Response)=>void;const delayed=new Promise<Response>(resolve=>resolveOld=resolve);let originalRequest:[RequestInfo|URL,RequestInit|undefined]|null=null;
  globalThis.fetch=async(url,options)=>{if(String(url).includes("/sources/s1/")){originalRequest=[url,options];return delayed;}return originalFetch(url,options);};
  try{
    await act(async()=>renderer.update(<Compare workspace={workspace} requestedBoard="b" requestedPaper="p1" requestedField="exposure" navigate={async()=>{}}/>));
    act(()=>{void button(renderer,"Browse retained source").props.onClick();});
    await act(async()=>renderer.update(<Compare workspace={workspace} requestedBoard="b" requestedPaper="p2" requestedField="population" navigate={async()=>{}}/>));
    assert.ok(renderer.root.findByProps({"aria-label":"Population cell editor"}));
    assert.ok(content(renderer.root.findByProps({"aria-label":"Population cell editor"})).includes("SOFTWARE TEST Report 2"));
    assert.ok(originalRequest);await act(async()=>resolveOld(await originalFetch(...originalRequest!)));
    assert.equal(renderer.root.findAllByType("mark").length,0,"old paper response cannot mount its source in the new paper cell");
    await act(async()=>renderer.update(<Compare workspace={workspace} requestedBoard="b" requestedPaper="p1" requestedField="exposure" navigate={async()=>{}}/>));
    assert.ok(renderer.root.findByProps({"aria-label":"Exposure cell editor"}));
  }finally{await act(async()=>renderer.unmount());}
});

test("historical definitions expose retained unsubmitted drafts separately from submitted cell values without writes",async()=>{
  const {renderer,drafts,requests}=await fixture("board-historical-retained-draft",{historical:true});
  drafts.set("p3/exposure",{board_id:"b",board_revision_id:"r",paper_id:"p3",field_id:"exposure",version:2,expected_cell_head_id:null,data:{...emptyCell(),value:"RETAINED UNSUBMITTED DRAFT VALUE",reason:"Historical draft notes"},updated_at:null});
  try{
    await act(async()=>renderer.root.findByProps({"aria-label":"Exposure for SOFTWARE TEST Report 3"}).props.onClick());
    const retained=renderer.root.findByProps({className:"board-historical-draft"});assert.ok(content(retained).includes("RETAINED UNSUBMITTED DRAFT VALUE"));assert.ok(content(retained).includes("DRAFT VERSION 2"));assert.ok(content(retained).includes("not submitted"));
    assert.equal(control(renderer,"Manual cell value").props.value,"","historical draft does not replace a submitted or neutral cell value");assert.equal(disabled(control(renderer,"Manual cell value")),true);assert.equal(requests.some(request=>request.method!=="GET"),false);
  }finally{await act(async()=>renderer.unmount());}
});
