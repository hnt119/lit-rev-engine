import assert from "node:assert/strict";
import test from "node:test";
import {allowedRoute,allowedQuery,browserBoundary,localOrigin,boundedBody,MAX_REQUEST_BYTES} from "../lib/bridge.ts";
import {highlightParts,safeExternal} from "../lib/helpers.ts";
import {requestId,acknowledgeRequest} from "../lib/api.ts";

test("thin bridge exposes only supported methods and paths",()=>{
  assert.equal(allowedRoute("GET","workspaces/a/runs/r/passages/p/context"),true);
  assert.equal(allowedRoute("POST","workspaces/a/assessments"),true);
  assert.equal(allowedRoute("GET","workspaces/a/maps"),true);
  assert.equal(allowedRoute("GET","workspaces/a/maps/m/neighbors/pmid:1"),true);
  assert.equal(allowedRoute("POST","workspaces/a/jobs/j/cancel"),true);
  for(const path of ["https://other.example/","admin","workspaces/a/snapshot","workspaces/a/run/r"])assert.equal(allowedRoute("GET",path),false);
  assert.equal(allowedRoute("DELETE","workspaces/a/runs/r"),false);
});
test("Host, Origin and fixed loopback upstream are enforced",()=>{
  const origin=localOrigin("http://127.0.0.1:3000");
  assert.equal(browserBoundary("127.0.0.1:3000",origin.origin,origin,true),true);
  assert.equal(browserBoundary("127.0.0.1:3000",null,origin,true),false);
  assert.equal(browserBoundary("evil.example",origin.origin,origin,false),false);
  assert.equal(browserBoundary(origin.host,"https://evil.example",origin,false),false);
  for(const value of ["http://example.com:8765","http://localhost:8765","http://127.0.0.1:8765/path","http://user:secret@127.0.0.1:8765"])assert.throws(()=>localOrigin(value));
});
test("query allowlist rejects duplicates and arbitrary proxy destinations",()=>{
  assert.equal(allowedQuery("workspaces/a/exports",new URLSearchParams("format=csv")),true);
  assert.equal(allowedQuery("workspaces/a/exports",new URLSearchParams("format=csv&format=json")),false);
  assert.equal(allowedQuery("capabilities",new URLSearchParams("url=https://elsewhere.example")),false);
  assert.equal(allowedQuery("workspaces/a/runs/r/passages/p/context",new URLSearchParams("offset=5&limit=5&archived=true")),true);
  assert.equal(allowedQuery("workspaces/a/maps",new URLSearchParams("search_id=s")),true);
  assert.equal(allowedQuery("workspaces/a/maps",new URLSearchParams()),false);
  assert.equal(allowedQuery("workspaces/a/maps",new URLSearchParams(),"POST"),true);
});
test("bridge bounds both declared and streamed bodies before upstream buffering",async()=>{
  assert.equal(new TextDecoder().decode(await boundedBody(new Request("http://127.0.0.1",{method:"POST",body:"{}"}))),"{}");
  await assert.rejects(boundedBody(new Request("http://127.0.0.1",{method:"POST",headers:{"Content-Length":String(MAX_REQUEST_BYTES+1)}})),RangeError);
  const request=new Request("http://127.0.0.1",{method:"POST",body:new ReadableStream({start(controller){controller.enqueue(new Uint8Array(MAX_REQUEST_BYTES));controller.enqueue(new Uint8Array(1));controller.close();}}),duplex:"half"} as RequestInit);
  await assert.rejects(boundedBody(request),RangeError);
});
test("canonical source highlight uses Unicode code points including escaped markup",()=>{
  const text="A 🧬 e\u0301 <script>alert(1)</script> Z";
  const quote="🧬 e\u0301 <script>";
  const start=2,end=start+Array.from(quote).length;
  assert.deepEqual(highlightParts(text,start,end),["A ",quote,"alert(1)</script> Z"]);
  assert.equal(highlightParts(text,start,end).join(""),text);
  assert.equal(safeExternal("javascript:alert(1)"),undefined);
  assert.equal(safeExternal("https://unknown.example/private"),undefined);
  assert.equal(safeExternal("https://pubmed.ncbi.nlm.nih.gov.evil.example/"),undefined);
  assert.equal(safeExternal("https://creativecommons.org/licenses/by/4.0/"),"https://creativecommons.org/licenses/by/4.0/");
  assert.equal(safeExternal("https://pubmed.ncbi.nlm.nih.gov/123/"),"https://pubmed.ncbi.nlm.nih.gov/123/");
});
test("ambiguous retry retains request ID; intentional new create after acknowledgement is new",async()=>{
  const entries=new Map<string,string>();
  Object.defineProperty(globalThis,"sessionStorage",{configurable:true,value:{getItem:(key:string)=>entries.get(key)??null,setItem:(key:string,value:string)=>entries.set(key,value),removeItem:(key:string)=>entries.delete(key)}});
  const payload={question:"Private research question",query:"private query"};
  const first=await requestId("create",payload);
  assert.equal(await requestId("create",payload),first);
  const stored=[...entries.values()].join();assert.equal(stored.includes("Private"),false);assert.equal(stored.includes("private query"),false);
  acknowledgeRequest("create");assert.notEqual(await requestId("create",payload),first);
});
