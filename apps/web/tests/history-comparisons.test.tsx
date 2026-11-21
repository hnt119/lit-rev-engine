import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import History from "../components/history";
import type {Schema} from "../lib/api";
import {flushDrafts,registerDraftFlusher} from "../lib/drafts";
import type {LocationState,Navigate} from "../components/workspace-app";
import {response,stamp,workspace} from "./import-collection-fixtures";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(text).join("");
const button=(renderer:ReactTestRenderer,name:string)=>renderer.root.findAllByType("button").find(item=>text(item)===name)!;
const link=(renderer:ReactTestRenderer,name:string)=>renderer.root.findAllByType("a").find(item=>text(item)===name)!;
const board=(id="board:1",revision="revision:1"):Schema<"BoardSummary">=>({board_id:id,revision_id:revision,question:"SOFTWARE TEST <script>not markup</script>",paper_count:3,field_count:3,created_at:stamp,preparation_id:"preparation:1",paper_ids:["paper:1","paper:2","paper:3"]});
const listing=(...boards:Schema<"BoardSummary">[]):Schema<"BoardListing">=>({boards,limits:{max_papers:30,max_fields:6,max_cells:180,max_boards:10,max_definition_revisions:20,max_cell_revisions:50,max_references:5,max_workspace_bytes:33554432,max_candidate_characters:1200,max_inspector_characters:4000}});
const refresh=async()=>{};

test("board-only history reads summaries, exposes pinned comparison exports and retains separate passage exports",async()=>{
  const originalFetch=globalThis.fetch,calls:{path:string;method:string}[]=[],destinations:LocationState[]=[];
  const w=workspace("history:workspace"),saved=board("board:a&b","revision:a?b");let renderer!:ReactTestRenderer;
  globalThis.fetch=async(input,options)=>{
    const path=String(input),method=options?.method??"GET";calls.push({path,method});
    if(path.endsWith("/session"))return response({csrf_token:"software-test"});
    assert.equal(path,"/api/v1/workspaces/history%3Aworkspace/boards");return response(listing(saved));
  };
  try{
    await act(async()=>{renderer=create(<History workspace={w} refresh={refresh} navigate={async target=>{destinations.push(target);}}/>);});
    assert.equal(calls.filter(call=>!call.path.endsWith("/session")).length,1);
    assert.ok(calls.every(call=>call.method==="GET"));
    assert.equal(renderer.root.findAllByType("script").length,0);
    assert.equal(text(renderer.root.findByType("article").findByType("h3")),saved.question);
    assert.match(text(renderer.root),/No submitted passage assessments/);
    assert.doesNotMatch(text(renderer.root),/No committed human judgments/);
    const prefix="/api/v1/workspaces/history%3Aworkspace/boards/board%3Aa%26b/exports?format=";
    assert.equal(link(renderer,"Download board CSV").props.href,prefix+"csv&history=false&revision_id=revision%3Aa%3Fb");
    assert.equal(link(renderer,"Download board audit JSON").props.href,prefix+"json&history=false&revision_id=revision%3Aa%3Fb");
    assert.equal(link(renderer,"Download passage CSV").props.href,"/api/v1/workspaces/history%3Aworkspace/exports?format=csv");
    assert.equal(link(renderer,"Download passage audit JSON").props.href,"/api/v1/workspaces/history%3Aworkspace/exports?format=json");
    await act(async()=>button(renderer,"Open comparison board").props.onClick());
    assert.deepEqual(destinations,[{page:"compare",workspace:w.id,board:saved.board_id,revision:saved.revision_id}]);
    const history=renderer.root.findAllByType("input").find(input=>input.parent?.type==="label"&&text(input.parent).includes("all saved board definitions"))!;
    await act(async()=>history.props.onChange({target:{checked:true}}));
    assert.equal(link(renderer,"Download board audit JSON").props.href,prefix+"json&history=true&revision_id=revision%3Aa%3Fb");
    assert.equal(link(renderer,"Download board CSV").props.href,prefix+"csv&history=true&revision_id=revision%3Aa%3Fb");
    assert.equal(calls.filter(call=>!call.path.endsWith("/session")).length,1,"changing export scope does not fetch or mutate research");
  }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;}
});

test("comparison listing failure leaves passage exports usable and retries only the read",async()=>{
  const originalFetch=globalThis.fetch;let attempts=0,renderer!:ReactTestRenderer;
  globalThis.fetch=async(input,options)=>{
    assert.equal(options?.method??"GET","GET");
    if(String(input).endsWith("/session"))return response({csrf_token:"software-test"});
    assert.equal(String(input),"/api/v1/workspaces/history-failure/boards");attempts++;
    return attempts===1?response({error:{code:"temporarily_unavailable",message:"Saved comparisons could not be read."}},503):response(listing(board()));
  };
  try{
    await act(async()=>{renderer=create(<History workspace={workspace("history-failure")} refresh={refresh} navigate={async()=>{}}/>);});
    assert.match(text(renderer.root.findByProps({role:"alert"})),/could not be read/);
    assert.equal(renderer.root.findAllByType("article").length,0);
    assert.equal(link(renderer,"Download passage CSV").props.download,true);
    await act(async()=>button(renderer,"Retry loading comparisons").props.onClick());
    assert.equal(attempts,2);assert.equal(renderer.root.findAllByProps({role:"alert"}).length,0);
    assert.equal(renderer.root.findAllByType("article").length,1);
  }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;}
});

test("empty comparison history offers navigation without creating a board or changing submitted records",async()=>{
  const originalFetch=globalThis.fetch,destinations:LocationState[]=[];let reads=0,renderer!:ReactTestRenderer;
  globalThis.fetch=async(input,options)=>{
    assert.equal(options?.method??"GET","GET");if(String(input).endsWith("/session"))return response({csrf_token:"software-test"});
    assert.equal(String(input),"/api/v1/workspaces/history-empty/boards");reads++;return response(listing());
  };
  try{
    await act(async()=>{renderer=create(<History workspace={workspace("history-empty")} refresh={refresh} navigate={async target=>{destinations.push(target);}}/>);});
    assert.match(text(renderer.root),/No saved comparison boards yet/);
    assert.equal(renderer.root.findAllByType("a").filter(item=>text(item).includes("board")).length,0);
    await act(async()=>button(renderer,"Open comparison workspace").props.onClick());
    assert.deepEqual(destinations,[{page:"compare",workspace:"history-empty"}]);assert.equal(reads,1);
  }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;}
});

test("late comparison reads cannot replace another workspace's history and switching hides old exports",async()=>{
  const originalFetch=globalThis.fetch,pending=new Map<string,(value:Response)=>void>();let renderer!:ReactTestRenderer;
  globalThis.fetch=async(input,options)=>{
    assert.equal(options?.method??"GET","GET");const path=String(input);
    if(path.endsWith("/session"))return response({csrf_token:"software-test"});
    return new Promise<Response>(resolve=>pending.set(path,resolve));
  };
  const page=(id:string)=><History workspace={workspace(id)} refresh={refresh} navigate={async()=>{}}/>;
  try{
    await act(async()=>{renderer=create(page("old"));});
    assert.match(text(renderer.root),/Loading saved comparisons/);
    await act(async()=>renderer.update(page("new")));
    await act(async()=>pending.get("/api/v1/workspaces/new/boards")!(response(listing({...board("new-board"),question:"New workspace comparison"}))));
    assert.match(text(renderer.root),/New workspace comparison/);
    await act(async()=>pending.get("/api/v1/workspaces/old/boards")!(response(listing({...board("old-board"),question:"Old workspace comparison"}))));
    assert.doesNotMatch(text(renderer.root),/Old workspace comparison/);
    assert.ok(link(renderer,"Download board CSV").props.href.includes("/workspaces/new/boards/new-board/"));
    await act(async()=>renderer.update(page("third")));
    assert.doesNotMatch(text(renderer.root),/New workspace comparison/);
    assert.match(text(renderer.root),/Loading saved comparisons/);
    assert.equal(renderer.root.findAllByType("a").filter(item=>text(item)==="Download board CSV").length,0);
    await act(async()=>pending.get("/api/v1/workspaces/third/boards")!(response(listing())));
  }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;}
});

test("opening a saved board delegates through draft-protecting navigation with its original definition",async()=>{
  const originalFetch=globalThis.fetch,destinations:LocationState[]=[];let renderer!:ReactTestRenderer,blocked=0,safe=false;
  const unregister=registerDraftFlusher(async()=>{if(!safe)throw new Error("Unsaved research draft retained");});
  globalThis.fetch=async(input,options)=>{
    assert.equal(options?.method??"GET","GET");if(String(input).endsWith("/session"))return response({csrf_token:"software-test"});
    assert.equal(String(input),"/api/v1/workspaces/history-drafts/boards");return response(listing(board()));
  };
  const navigate:Navigate=async target=>{try{await flushDrafts();destinations.push(target);return {status:"success"};}catch(error){blocked++;return {status:"blocked",message:(error as Error).message};}};
  try{
    await act(async()=>{renderer=create(<History workspace={workspace("history-drafts")} refresh={refresh} navigate={navigate}/>);});
    await act(async()=>button(renderer,"Open comparison board").props.onClick());
    assert.equal(blocked,1);assert.deepEqual(destinations,[]);
    safe=true;await act(async()=>button(renderer,"Open comparison board").props.onClick());
    assert.deepEqual(destinations,[{page:"compare",workspace:"history-drafts",board:"board:1",revision:"revision:1"}]);
  }finally{unregister();if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;}
});
