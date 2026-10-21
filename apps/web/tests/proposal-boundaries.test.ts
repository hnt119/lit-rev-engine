import assert from "node:assert/strict";
import test from "node:test";
import {allowedQuery,allowedRoute} from "../lib/bridge.ts";
test("optional proposal routes expose only explicit generation/review and bounded reads",()=>{
  const b="workspaces/w/boards/b";
  for(const path of ["proposal-capabilities","proposal-runs/r","proposals","proposals/p/references/ref/context","proposal-audit"])assert.equal(allowedRoute("GET",b+"/"+path),true);
  for(const path of ["proposal-runs","proposals/p/adopt","proposals/p/dismiss"])assert.equal(allowedRoute("POST",b+"/"+path),true);
  for(const method of ["PUT","DELETE"])assert.equal(allowedRoute(method,b+"/proposals/p"),false);
  assert.equal(allowedRoute("POST",b+"/proposals/p/verify"),false);
  assert.equal(allowedQuery(b+"/proposals",new URLSearchParams("revision_id=r&paper_id=p&field_id=f&offset=0&limit=5")),true);
  assert.equal(allowedQuery(b+"/proposals",new URLSearchParams("revision_id=r&revision_id=x")),false);
  assert.equal(allowedQuery(b+"/proposals",new URLSearchParams("url=http://elsewhere/")),false);
  assert.equal(allowedQuery(b+"/proposal-runs",new URLSearchParams("model=x"),"POST"),false);
  assert.equal(allowedQuery(b+"/proposal-capabilities",new URLSearchParams("api_key=x")),false);
});
