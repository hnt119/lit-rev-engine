import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestRenderer} from "react-test-renderer";
import {emptyCell,useBoardDraft} from "../lib/board-drafts.tsx";
import {flushDrafts} from "../lib/drafts.tsx";
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}});

function record(){return {board_id:"b",board_revision_id:"r",paper_id:"p",field_id:"f",version:0,expected_cell_head_id:null as string|null,data:emptyCell(),updated_at:null};}

test("board drafts drain latest edits with board-specific CAS before navigation and reopen",async()=>{
  let server=record(),puts=0,release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);
  const requests:Record<string,unknown>[]=[];
  globalThis.fetch=async(url,options)=>{
    if(String(url).endsWith("/session"))return response({csrf_token:"test"});
    if(options?.method!=="PUT")return response(server);
    const body=JSON.parse(String(options.body));requests.push(body);puts++;if(puts===1)await gate;
    assert.equal(body.version,server.version);assert.equal(body.expected_revision_id,"r");assert.equal("expected_assessment_head" in body,false);
    server={...server,version:server.version+1,expected_cell_head_id:body.expected_cell_head_id,data:body.data};return response(server);
  };
  let draft!:ReturnType<typeof useBoardDraft>,renderer!:ReactTestRenderer;
  function Harness(){draft=useBoardDraft("workspaces/board-drain/boards/b/drafts/p/f","r",null);return null;}
  await act(async()=>{renderer=create(<Harness/>);});
  await act(async()=>draft.setData({...emptyCell(),value:"first"}));
  let saving!:Promise<void>;act(()=>{saving=draft.save();});
  await act(async()=>draft.setData({...emptyCell(),value:"latest"}));
  let navigation!:Promise<void>;act(()=>{navigation=flushDrafts();});
  await act(async()=>{release();await Promise.all([saving,navigation]);});
  assert.equal(puts,2);assert.equal(server.data.value,"latest");assert.equal(draft.snapshot().version,2);assert.equal(draft.state,"saved");
  await act(async()=>renderer.unmount());await act(async()=>{renderer=create(<Harness/>);});
  assert.equal(draft.data.value,"latest");assert.equal(draft.version,2);assert.equal(requests.length,2);await act(async()=>renderer.unmount());
});

test("board conflict retains edits and blocks leaving until an explicit rebase",async()=>{
  let server=record(),conflict=true,puts=0;
  globalThis.fetch=async(url,options)=>{
    if(String(url).endsWith("/session"))return response({csrf_token:"test"});
    if(options?.method!=="PUT")return response(server);
    puts++;if(conflict){server={...server,version:1,data:{...emptyCell(),value:"other tab"}};return response({detail:{code:"stale_board_draft",message:"Another cell draft was saved"}},409);}
    const body=JSON.parse(String(options.body));assert.equal(body.version,server.version);server={...server,version:server.version+1,data:body.data,expected_cell_head_id:body.expected_cell_head_id};return response(server);
  };
  let draft!:ReturnType<typeof useBoardDraft>,renderer!:ReactTestRenderer;
  function Harness(){draft=useBoardDraft("workspaces/board-conflict/boards/b/drafts/p/f","r",null);return null;}
  await act(async()=>{renderer=create(<Harness/>);});await act(async()=>draft.setData({...emptyCell(),value:"my retained edit"}));
  await act(async()=>{await assert.rejects(draft.save(),/Another cell draft/);});
  assert.equal(draft.state,"conflict");assert.equal(draft.data.value,"my retained edit");await assert.rejects(flushDrafts(),/Another cell draft/);
  await act(async()=>draft.retry());assert.equal(puts,1,"retry does not overwrite a newer draft");assert.equal(draft.state,"conflict");
  conflict=false;await act(async()=>draft.rebase(draft.data,"head-2"));await act(async()=>draft.save());
  assert.equal(server.data.value,"my retained edit");assert.equal(server.expected_cell_head_id,"head-2");assert.equal(server.version,2);assert.equal(draft.state,"saved");await act(async()=>renderer.unmount());
});

test("old-head drafts remain stale and historical board inspection makes no writes",async()=>{
  let server={...record(),version:2,data:{...emptyCell(),reason:"prior notes"}},puts=0;
  globalThis.fetch=async(url,options)=>{if(String(url).endsWith("/session"))return response({csrf_token:"test"});if(options?.method==="PUT")puts++;return response(server);};
  let draft!:ReturnType<typeof useBoardDraft>,renderer!:ReactTestRenderer;
  function Current(){draft=useBoardDraft("workspaces/board-stale/boards/b/drafts/p/f","r","head-latest");return null;}
  await act(async()=>{renderer=create(<Current/>);});assert.equal(draft.state,"conflict");assert.equal(draft.data.reason,"prior notes");await assert.rejects(draft.save(),/older cell head/);await act(async()=>renderer.unmount());
  function Historical(){draft=useBoardDraft("workspaces/board-historical/boards/b/drafts/p/f","r","head-latest",true);return null;}
  await act(async()=>{renderer=create(<Historical/>);});await flushDrafts();assert.equal(draft.state,"saved");assert.equal(puts,0);await act(async()=>renderer.unmount());
});

test("retry after an initial read failure restores the durable server draft without replacing it with an empty cell",async()=>{
  const server={...record(),version:4,expected_cell_head_id:"head-4",data:{...emptyCell(),value:"durable manual value",reason:"retained server notes"}};let failRead=true,puts=0;
  globalThis.fetch=async(url,options)=>{if(String(url).endsWith("/session"))return response({csrf_token:"test"});if(options?.method==="PUT")puts++;if(failRead)return response({detail:{code:"read_failed",message:"Temporary read failure"}},503);return response(server);};
  let draft!:ReturnType<typeof useBoardDraft>,renderer!:ReactTestRenderer;
  function Harness(){draft=useBoardDraft("workspaces/board-read-recovery/boards/b/drafts/p/f","r","head-4");return null;}
  await act(async()=>{renderer=create(<Harness/>);});assert.equal(draft.ready,false);assert.equal(draft.state,"error");
  failRead=false;await act(async()=>draft.retry());assert.equal(draft.ready,true);assert.equal(draft.state,"saved");assert.equal(draft.data.value,"durable manual value");assert.equal(draft.expectedHead,"head-4");assert.equal(draft.version,4);assert.equal(puts,0);
  await act(async()=>renderer.unmount());
});
