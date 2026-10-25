import assert from "node:assert/strict";
import test from "node:test";
import {deploymentBoundary,deploymentPolicy} from "../lib/deployment.ts";
import {allowedRoute,allowedQuery,boundedBody,BodyReadTimeout} from "../lib/bridge.ts";
import {GET,POST} from "../app/api/v1/[...path]/route.ts";
import {GET as health} from "../app/healthz/route.ts";

const env={MVP_DEPLOYMENT_MODE:"hosted",MVP_HOSTED_INGRESS:"render",MVP_PUBLIC_ORIGIN:"https://review.example.org",MVP_API_ORIGIN:"http://127.0.0.1:8765"};
const headers={host:"review.example.org",origin:env.MVP_PUBLIC_ORIGIN,"x-forwarded-proto":"https"};
async function configured(work:()=>Promise<void>){
  const keys=[...Object.keys(env),"MVP_WEB_ORIGIN"],saved=Object.fromEntries(keys.map(key=>[key,process.env[key]]));
  Object.assign(process.env,env);delete process.env.MVP_WEB_ORIGIN;
  try{await work();}finally{for(const key of keys){if(saved[key]===undefined)delete process.env[key];else process.env[key]=saved[key];}}
}
test("hosted configuration is explicit, canonical and fixed upstream; local rules remain strict",()=>{
  const policy=deploymentPolicy(env);assert.equal(policy.web.origin,env.MVP_PUBLIC_ORIGIN);
  for(const origin of ["http://review.example.org","https://review.example.org/","https://user:pass@review.example.org","https://review.example.org/path","https://*.example.org","https://127.0.0.1","https://localhost","https://foo.localhost","https://review.example.org?url=other"," https://review.example.org","https://REVIEW.example.org","https://-review.example.org","https://review..example.org","https://review.example.org-","https://review.example.org:0",`https://${"x".repeat(64)}.example.org`])
    assert.throws(()=>deploymentPolicy({...env,MVP_PUBLIC_ORIGIN:origin}));
  for(const override of [{MVP_PUBLIC_ORIGIN:undefined},{MVP_HOSTED_INGRESS:undefined},{MVP_HOSTED_INGRESS:"arbitrary"},{MVP_API_ORIGIN:"https://provider.example.org"},{MVP_API_ORIGIN:undefined},{MVP_API_ORIGIN:"http://localhost:8765"},{MVP_WEB_ORIGIN:"http://127.0.0.1:3000"},{MVP_DEPLOYMENT_MODE:"typo"}])assert.throws(()=>deploymentPolicy({...env,...override}));
  assert.equal(deploymentPolicy({}).mode,"local");assert.throws(()=>deploymentPolicy({MVP_API_ORIGIN:"https://elsewhere.example.org"}));
});
test("proxy headers confirm configured origin and cannot override actual Host or browser Origin",()=>{
  const policy=deploymentPolicy(env);
  assert.equal(deploymentBoundary(new Headers(headers),policy,true),true);
  const overrides:Record<string,string>[]=[{host:"evil.example.org","x-forwarded-host":"review.example.org"},{origin:"https://evil.example.org"},{"x-forwarded-proto":"http"},{"x-forwarded-proto":"https,http"},{"x-forwarded-host":"evil.example.org"}];
  for(const override of overrides)assert.equal(deploymentBoundary(new Headers({...headers,...override}),policy,true),false);
  const absent=new Headers(headers);absent.delete("x-forwarded-proto");assert.equal(deploymentBoundary(absent,policy,false),false);
  absent.set("x-forwarded-proto","https");absent.delete("origin");assert.equal(deploymentBoundary(absent,policy,true),false);assert.equal(deploymentBoundary(absent,policy,false),true);
  assert.equal(deploymentBoundary(new Headers({...headers,"x-forwarded-for":"127.0.0.1","forwarded":"host=evil.example.org;proto=http"}),policy,true),true,"unused forwarding headers confer no authority");
});
test("admission has only bounded explicit routes and no capability URL parameters",()=>{
  for(const [method,path] of [["GET","admission/status"],["POST","admission/login"],["POST","admission/logout"]])assert.equal(allowedRoute(method,path),true);
  for(const method of ["GET","PUT","DELETE"])assert.equal(allowedRoute(method,"admission/login"),false);
  assert.equal(allowedQuery("admission/status",new URLSearchParams("code=secret")),false);
  assert.equal(allowedQuery("admission/login",new URLSearchParams("code=secret"),"POST"),false);
});
test("slow body deadline cancels trickled input before admission or upstream buffering can hang",async()=>{
  let cancelled=0;
  const request=new Request("http://internal/api/v1/workspaces/w/imports/csv",{method:"POST",duplex:"half",body:new ReadableStream({start(controller){controller.enqueue(new Uint8Array([65]));},cancel(){cancelled++;}})} as RequestInit);
  await assert.rejects(boundedBody(request,1024*1024,20),BodyReadTimeout);
  assert.equal(cancelled,1);
});
test("actual bridge retains public Origin and opaque cookies, strips forwarded identity, never redirects upstream",async()=>configured(async()=>{
  const original=globalThis.fetch;let calls=0;
  globalThis.fetch=async(input,init)=>{
    calls++;assert.equal(String(input),"http://127.0.0.1:8765/api/v1/admission/login");
    const forwarded=new Headers(init?.headers);assert.equal(forwarded.get("origin"),env.MVP_PUBLIC_ORIGIN);assert.equal(forwarded.get("cookie"),"__Host-litrev_admission=software-test");assert.equal(forwarded.get("x-forwarded-for"),null);assert.equal(forwarded.get("x-forwarded-host"),null);assert.equal(init?.redirect,"error");
    return new Response('{"admitted":true}',{headers:{"Content-Type":"application/json","Set-Cookie":"__Host-litrev_admission=software-test; Path=/; HttpOnly; Secure; SameSite=Strict"}});
  };
  try{
    const context={params:Promise.resolve({path:["admission","login"]})};
    const response=await POST(new Request("http://internal/api/v1/admission/login",{method:"POST",headers:{...headers,"Content-Type":"application/json",cookie:"__Host-litrev_admission=software-test","x-forwarded-for":"spoof"},body:JSON.stringify({code:"software-test"})}),context);
    assert.equal(response.status,200);assert.equal(response.headers.get("cache-control"),"no-store");assert.match(response.headers.get("set-cookie")!,/Secure/);
    const denied=await POST(new Request("http://internal/api/v1/admission/login",{method:"POST",headers:{...headers,origin:"https://evil.example.org"},body:"{}"}),context);assert.equal(denied.status,403);assert.equal(calls,1);
    const query=await GET(new Request("http://internal/api/v1/admission/status?code=secret",{headers}),{params:Promise.resolve({path:["admission","status"]})});assert.equal(query.status,400);assert.equal(calls,1);
  }finally{globalThis.fetch=original;}
}));
test("public readiness contains no upstream state or credentials and accepts managed internal probe",async()=>configured(async()=>{
  const original=globalThis.fetch;
  globalThis.fetch=async(input,init)=>{assert.equal(String(input),"http://127.0.0.1:8765/readyz");assert.equal(init?.redirect,"error");return new Response('{"private":"must not forward"}',{status:200});};
  try{
    const response=await health(new Request("http://internal/healthz",{headers:{host:"review.example.org"}}));assert.equal(response.status,200);assert.deepEqual(await response.json(),{status:"ok"});assert.equal(response.headers.get("cache-control"),"no-store");
    globalThis.fetch=async()=>new Response("private failure",{status:503});assert.equal((await health(new Request("http://internal/healthz",{headers:{host:"review.example.org"}}))).status,503);
  }finally{globalThis.fetch=original;}
}));
