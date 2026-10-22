import assert from "node:assert/strict";
import test from "node:test";
import {APIError,apiUpload} from "../lib/api";
import {response} from "./import-collection-fixtures";

test("raw upload helper rejects unsupported paths and media types before session or network access",async()=>{
  let requests=0;globalThis.fetch=async()=>{requests++;throw new Error("No network expected");};
  for(const path of ["https://software.invalid/upload","workspaces/software/exports/json","workspaces/software/imports/csv?destination=x"]){await assert.rejects(apiUpload(path,new ArrayBuffer(0),"software-request"),/supported raw citation upload/);}
  await assert.rejects(apiUpload("workspaces/software/imports/csv",new ArrayBuffer(0),"software-request",undefined,"application/json"),/supported raw citation upload/);assert.equal(requests,0);
});

test("raw citation bytes, encoded filename and idempotency key use the existing same-origin CSRF session",async()=>{
  const bytes=new Uint8Array([239,187,191,84,105,116,108,101,10]),calls:{url:string;options:RequestInit|undefined}[]=[];
  globalThis.fetch=async(input,options)=>{calls.push({url:String(input),options});return response(String(input).endsWith("/session")?{csrf_token:"software-session"}:{id:"software-preview"});};
  const result=await apiUpload<{id:string}>("workspaces/software/imports/csv",bytes.buffer,"software-request","software 微生物.csv","text/csv");
  assert.equal(result.id,"software-preview");assert.equal(calls.length,2);const upload=calls[1];assert.equal(upload.url,"/api/v1/workspaces/software/imports/csv");assert.equal(upload.options?.method,"POST");assert.equal(upload.options?.credentials,"same-origin");assert.equal(upload.options?.cache,"no-store");assert.deepEqual(upload.options?.headers,{Accept:"application/json","X-CSRF-Token":"software-session","Content-Type":"text/csv","X-Request-ID":"software-request","X-Import-Filename":encodeURIComponent("software 微生物.csv")});assert.deepEqual(new Uint8Array(upload.options?.body as ArrayBuffer),bytes);
  const blob=new Blob(["PMID: 12345678\n"]);await apiUpload("workspaces/software/imports/identifiers",blob,"software-identifiers");assert.equal(calls[2].options?.body,blob);assert.equal((calls[2].options?.headers as Record<string,string>)["X-Import-Filename"],undefined);
});

test("raw upload structured failures retain their status and code without attempting a fallback",async()=>{
  let requests=0;globalThis.fetch=async()=>{requests++;return response({detail:{code:"import_size_limit",message:"Synthetic import limit"}},413);};
  await assert.rejects(apiUpload("workspaces/software/imports/ris",new ArrayBuffer(1),"software-failed"),(error:unknown)=>error instanceof APIError&&error.status===413&&error.code==="import_size_limit"&&error.message==="Synthetic import limit");assert.equal(requests,1);
});
