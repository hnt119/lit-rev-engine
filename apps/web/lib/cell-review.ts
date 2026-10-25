import type {CellData} from "./board-drafts";

export type CellReviewStep="evidence"|"comment"|"review";
export const cellReviewSteps=[{id:"evidence",label:"1. Select evidence"},{id:"comment",label:"2. Comment & judge"},{id:"review",label:"3. Review & save"}] as const;

/** Existing research content determines the sensible fallback; no new workflow state. */
export function derivedCellStep(data:CellData,submitted=false):CellReviewStep {
  if(submitted)return "review";
  if(data.references.length||data.value?.trim()||data.reason.trim()||data.missing_information.trim())return "comment";
  return "evidence";
}

export function sameExcerpt(a:CellData["references"][number],b:CellData["references"][number]):boolean {
  return a.source_id===b.source_id&&a.source_version===b.source_version&&a.source_sha256===b.source_sha256&&a.blocks_sha256===b.blocks_sha256&&a.block_id===b.block_id&&a.start===b.start&&a.end===b.end;
}
