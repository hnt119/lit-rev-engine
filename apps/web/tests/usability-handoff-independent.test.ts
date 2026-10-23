import assert from "node:assert/strict";
import test from "node:test";
import {
  acknowledgeComparisonHandoff,assertHandoffJob,assertHandoffPreparation,
  createComparisonHandoff,currentExactPreparation,type ComparisonHandoff,
} from "../lib/comparison-handoff";
import {research} from "./collection-research-fixtures";
import {response} from "./import-collection-fixtures";

const captured=(f:ReturnType<typeof research>):ComparisonHandoff=>({
  question:"SOFTWARE TEST captured question",origin:{...f.collectionRef},
  selected_paper_ids:[...f.preparation.selected_paper_ids],expected_source_revision:0,
  expected_preparation_id:null,job_id:null,preparation_id:null,
});

test("current comparison preparation requires exact origin, order and current source head",()=>{
  const f=research("independent-current",30),ids=[...f.preparation.selected_paper_ids];
  assert.equal(currentExactPreparation({...f.state,selected_paper_ids:[]},f.collectionRef,ids),f.preparation);
  assert.equal(currentExactPreparation(f.state,f.collectionRef,[...ids].reverse()),undefined);
  assert.equal(currentExactPreparation(f.state,f.collectionRef,ids.slice(0,29)),undefined);
  assert.equal(currentExactPreparation({...f.state,source_revision:2},f.collectionRef,ids),undefined);
  assert.equal(currentExactPreparation({...f.state,current_preparation_id:"different"},f.collectionRef,ids),undefined);
  assert.equal(currentExactPreparation(f.state,{...f.collectionRef,collection_snapshot_sha256:"0".repeat(64)},ids),undefined);
  assert.equal(currentExactPreparation(f.state,{kind:"search",search_id:f.summary.id},ids),undefined);
});

test("job acknowledgment refuses stale, reordered, cross-workspace and cross-origin results",()=>{
  const f=research("independent-job"),data=captured(f),job=f.job();
  assert.doesNotThrow(()=>assertHandoffJob(data,job,f.state.id));
  for(const changed of [
    {...job,workspace_id:"another-workspace"},
    {...job,selected_paper_ids:[...job.selected_paper_ids].reverse()},
    {...job,expected_source_revision:1},
    {...job,expected_preparation_id:"another-preparation"},
    {...job,collection_ref:{...f.collectionRef,collection_snapshot_sha256:"0".repeat(64)}},
  ]) assert.throws(()=>assertHandoffJob(data,changed,f.state.id),/does not match/);
  assert.throws(()=>assertHandoffJob({...data,job_id:"different-job"},job,f.state.id),/does not match/);
});

test("partial preparation preserves every selected paper but must match the succeeded job receipt",()=>{
  const f=research("independent-partial",30),data=captured(f);
  const partial={...f.preparation,sources:f.preparation.sources.slice(0,1),errors:[]};
  const job=f.job({status:"succeeded",result_preparation_id:partial.id,result_source_revision:partial.source_revision});
  assert.doesNotThrow(()=>assertHandoffPreparation(data,partial,job));
  assert.doesNotThrow(()=>assertHandoffPreparation(data,partial));
  assert.throws(()=>assertHandoffPreparation(data,{...partial,source_revision:partial.source_revision+1}),/does not match/);
  const reuse={...data,expected_source_revision:partial.source_revision,expected_preparation_id:partial.id};
  assert.doesNotThrow(()=>assertHandoffPreparation(reuse,partial));
  assert.throws(()=>assertHandoffPreparation(reuse,{...partial,source_revision:partial.source_revision+1}),/does not match/);
  assert.throws(()=>assertHandoffPreparation(data,{...partial,selected_paper_ids:partial.selected_paper_ids.slice(0,1)},job),/does not match/);
  for(const changed of [
    {...job,status:"cancelled" as const},
    {...job,result_preparation_id:"different"},
    {...job,result_source_revision:partial.source_revision+1},
  ]) assert.throws(()=>assertHandoffPreparation(data,partial,changed),/does not match/);
});

test("handoff capture copies mutable selection and requires an exact persisted CAS acknowledgment",async()=>{
  const f=research("independent-capture"),input=captured(f),requests:any[]=[];
  globalThis.fetch=async(path,options)=>{
    if(String(path).endsWith("/session"))return response({csrf_token:"software"});
    const body=JSON.parse(String(options?.body));requests.push({path:String(path),...body});
    return response({scope:decodeURIComponent(String(path).split("/").at(-1)!),version:body.version+1,data:body.data});
  };
  const pending=createComparisonHandoff(f.state.id,input);
  input.selected_paper_ids.reverse();input.origin={kind:"search",search_id:"different"};input.question="mutated";
  const first=await pending,second=await createComparisonHandoff(f.state.id,captured(f));
  assert.equal(requests.length,2);assert.notEqual(first.scope,second.scope);
  assert.equal(first.version,1);assert.equal(first.data.question,"SOFTWARE TEST captured question");
  assert.deepEqual(first.data.selected_paper_ids,f.preparation.selected_paper_ids);
  assert.deepEqual(first.data.origin,f.collectionRef);assert.equal(requests[0].version,0);
  globalThis.fetch=async(path,options)=>{
    const body=JSON.parse(String(options?.body));
    return response({scope:decodeURIComponent(String(path).split("/").at(-1)!),version:body.version+1,data:{...body.data,selected_paper_ids:["server-retargeted"]}});
  };
  await assert.rejects(createComparisonHandoff(f.state.id,captured(f)),/acknowledgment did not match/);
});

test("acknowledgment extends the same captured record and repeated acknowledgments do not write",async()=>{
  const f=research("independent-ack"),data=captured(f),writes:any[]=[];
  globalThis.fetch=async(path,options)=>{
    if(String(path).endsWith("/session"))return response({csrf_token:"software"});
    const body=JSON.parse(String(options?.body));writes.push(body);
    return response({scope:decodeURIComponent(String(path).split("/").at(-1)!),version:body.version+1,data:body.data});
  };
  const record={scope:"comparison-handoff:independent",version:1,data};
  const job=f.job({status:"succeeded",result_preparation_id:f.preparation.id,result_source_revision:1});
  const result=await acknowledgeComparisonHandoff(f.state.id,record,{job,preparation:f.preparation});
  assert.equal(result.scope,record.scope);assert.equal(result.version,2);
  assert.deepEqual(result.data.selected_paper_ids,record.data.selected_paper_ids);
  assert.equal(result.data.question,record.data.question);assert.equal(result.data.job_id,job.id);
  assert.equal(result.data.preparation_id,f.preparation.id);assert.equal(writes.length,1);
  assert.equal(await acknowledgeComparisonHandoff(f.state.id,result,{job,preparation:f.preparation}),result);
  assert.equal(writes.length,1);
  globalThis.fetch=async()=>response({error:{code:"stale_draft",message:"SOFTWARE TEST conflict",retryable:false}},409);
  await assert.rejects(acknowledgeComparisonHandoff(f.state.id,record,{job}),/SOFTWARE TEST conflict/);
  assert.equal(record.data.job_id,null);assert.equal(record.data.preparation_id,null);
});
