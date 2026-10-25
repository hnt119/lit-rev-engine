import assert from "node:assert/strict";
import test from "node:test";
import {allowedQuery,allowedRoute} from "../lib/bridge.ts";

test("comparison board bridge admits only the implemented authorized route shapes",()=>{
  const board="workspaces/w/boards/b";
  for(const path of ["workspaces/w/boards",board,`${board}/drafts/pmid:1/f`,`${board}/cells/pmid:1/f/history`,`${board}/sources/s/blocks`,`${board}/references/r/context`,`${board}/exports`])assert.equal(allowedRoute("GET",path),true,path);
  for(const path of ["workspaces/w/boards",`${board}/revisions`,`${board}/candidates`,`${board}/cell-revisions`])assert.equal(allowedRoute("POST",path),true,path);
  assert.equal(allowedRoute("PUT",`${board}/drafts/pmid:1/f`),true);
  for(const [method,path] of [["DELETE",board],["POST",`${board}/exports`],["POST",`${board}/generate`],["PUT",board],["GET",`${board}/snapshot`],["GET",`${board}/sources/s/raw`]])assert.equal(allowedRoute(method,path),false,`${method} ${path}`);
});

test("board query keys preserve explicit revision and bounded inspection without upstream escape",()=>{
  const board="workspaces/w/boards/b";
  for(const [path,query] of [[board,"revision_id=r"],[`${board}/drafts/p/f`,"revision_id=r"],[`${board}/sources/s/blocks`,"revision_id=r&offset=1&limit=1&block_id=block:1&start=20"],[`${board}/cells/p/f/history`,"revision_id=r&offset=0&limit=10"],[`${board}/references/ref/context`,"revision_id=r"],[`${board}/exports`,"format=json&revision_id=r&history=true"]])assert.equal(allowedQuery(path,new URLSearchParams(query)),true,path);
  for(const [path,query] of [[board,"revision_id=r&revision_id=other"],[board,"url=https://elsewhere.example"],[`${board}/drafts/p/f`,"expected_assessment_head=x"],[`${board}/exports`,"format=csv&format=json"],[`${board}/sources/s/blocks`,"archived=true"],["workspaces/w/boards","revision_id=r"]])assert.equal(allowedQuery(path,new URLSearchParams(query)),false,path);
  assert.equal(allowedQuery(`${board}/candidates`,new URLSearchParams("revision_id=r"),"POST"),false);
});
