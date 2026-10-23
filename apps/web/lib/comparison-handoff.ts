import {api,workspacePath,type Schema} from "./api";
import {matchesPaperOrigin} from "./paper-origin";
import {canonical} from "./helpers";

export type HandoffOrigin={kind:"search";search_id:string}|Schema<"CollectionInputRef">;
export type HandoffPreparation=Schema<"PreparationSummary">|Schema<"CollectionPreparationSummary">;
export type HandoffJob=Schema<"PreparationJobView">|Schema<"CollectionPreparationJobView">;
export type ComparisonHandoff={question:string;origin:HandoffOrigin;selected_paper_ids:string[];expected_source_revision:number;expected_preparation_id:string|null;job_id:string|null;preparation_id:string|null};
export type HandoffRecord={scope:string;version:number;data:ComparisonHandoff};
export const sameOrderedPapers=(a:readonly string[],b:readonly string[])=>a.length===b.length&&a.every((id,index)=>id===b[index]);
function matchesOrigin(origin:HandoffOrigin,binding:{search_id?:string|null;collection_ref?:Schema<"CollectionInputRef">}){
  return origin.kind==="search"?!binding.collection_ref&&binding.search_id===origin.search_id:matchesPaperOrigin(origin,binding);
}

export function currentExactPreparation(workspace:Schema<"WorkspaceSummary">,origin:HandoffOrigin,ids:string[]){
  return workspace.preparations.find(item=>item.id===workspace.current_preparation_id&&item.source_revision===workspace.source_revision&&matchesOrigin(origin,item)&&sameOrderedPapers(item.selected_paper_ids,ids));
}
export function assertHandoffJob(data:ComparisonHandoff,job:HandoffJob,workspaceId:string){
  if(job.workspace_id!==workspaceId||!matchesOrigin(data.origin,job)||!sameOrderedPapers(data.selected_paper_ids,job.selected_paper_ids)||job.expected_source_revision!==data.expected_source_revision||job.expected_preparation_id!==data.expected_preparation_id||data.job_id&&data.job_id!==job.id)
    throw new Error("Preparation job does not match the captured comparison request. Your current selection has not been used to retarget it.");
}
export function assertHandoffPreparation(data:ComparisonHandoff,preparation:HandoffPreparation,job?:HandoffJob){
  const expectedRevision=preparation.id===data.expected_preparation_id?data.expected_source_revision:data.expected_source_revision+1;
  if(!matchesOrigin(data.origin,preparation)||!sameOrderedPapers(data.selected_paper_ids,preparation.selected_paper_ids)||data.preparation_id&&data.preparation_id!==preparation.id||job&&(job.status!=="succeeded"||job.result_preparation_id!==preparation.id||job.result_source_revision!==preparation.source_revision)||!job&&preparation.source_revision!==expectedRevision)
    throw new Error("Published preparation does not match the exact papers and source revision captured for comparison.");
}
async function write(workspaceId:string,scope:string,version:number,data:ComparisonHandoff):Promise<HandoffRecord>{
  const endpoint=workspacePath(workspaceId)+"/drafts/"+encodeURIComponent(scope);
  let record:Schema<"DraftRecord">;
  try{record=await api<Schema<"DraftRecord">>(endpoint,"PUT",{version,data,expected_assessment_head:null});}
  catch(error){const saved=await api<Schema<"DraftRecord">>(endpoint).catch(()=>null);if(saved&&saved.version===version+1&&canonical(saved.data)===canonical(data))record=saved;else throw error;}
  if(record.scope!==scope||record.version!==version+1||canonical(record.data)!==canonical(data))throw new Error("The saved comparison handoff acknowledgment did not match the captured request.");
  return {scope,version:record.version,data};
}
/** A new immutable capture is saved before submitting any source preparation. */
export function createComparisonHandoff(workspaceId:string,input:Omit<ComparisonHandoff,"job_id"|"preparation_id">){
  const data:ComparisonHandoff={...input,origin:{...input.origin},selected_paper_ids:[...input.selected_paper_ids],job_id:null,preparation_id:null};
  return write(workspaceId,"comparison-handoff:"+crypto.randomUUID(),0,data);
}
export async function acknowledgeComparisonHandoff(workspaceId:string,record:HandoffRecord,ack:{job?:HandoffJob;preparation?:HandoffPreparation}){
  if(ack.job)assertHandoffJob(record.data,ack.job,workspaceId);
  if(ack.preparation)assertHandoffPreparation(record.data,ack.preparation,ack.job);
  const data={...record.data,job_id:ack.job?.id??record.data.job_id,preparation_id:ack.preparation?.id??record.data.preparation_id};
  if(data.job_id===record.data.job_id&&data.preparation_id===record.data.preparation_id)return record;
  return write(workspaceId,record.scope,record.version,data);
}
