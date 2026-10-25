import assert from "node:assert/strict";
import test from "node:test";
import {settingsDestination,researchDestination} from "../lib/settings-navigation";
import {allowedRoute,allowedQuery} from "../lib/bridge";
import type {LocationState} from "../components/workspace-app";

test("settings return retains opaque comparison/source navigation and no additional research content",()=>{
  const original:LocationState={page:"compare",workspace:"workspace",board:"board",revision:"revision",paper:"paper",field:"field",run:"run",passage:"passage",returnTo:"cell",preparation:"preparation"};
  const target=settingsDestination(original,"ai");assert.deepEqual(target,{...original,page:"settings",settingsReturn:"compare",settingsSection:"ai"});assert.deepEqual(researchDestination(target),original);assert.deepEqual(researchDestination(settingsDestination(target,"privacy")),original);assert.deepEqual(Object.keys(target).filter(key=>!(key in original)),["settingsReturn","settingsSection"]);
});

test("settings and generation preparation expose only intended local bridge shapes",()=>{
  for(const [method,path] of [["GET","settings"],["PUT","settings"],["POST","settings/test-pubmed"],["POST","workspaces/w/search-plans/p/prepare-generation"],["POST","workspaces/w/boards/b/prepare-generation"]])assert.equal(allowedRoute(method,path),true,path);
  for(const [method,path] of [["POST","settings"],["GET","settings/test-pubmed"],["POST","settings/test-any-provider"],["GET","workspaces/w/boards/b/prepare-generation"]])assert.equal(allowedRoute(method,path),false,path);
  assert.equal(allowedQuery("settings",new URLSearchParams()),true);for(const key of ["url","key","question","notes"])assert.equal(allowedQuery("settings",new URLSearchParams({[key]:"untrusted"})),false);
});
