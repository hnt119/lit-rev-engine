import type {CellData} from "./board-drafts";

/** Early guidance only; canonical ownership, quotations and CAS stay server-authoritative. */
export function cellGuidance(data:CellData):string[]{
  const messages:string[]=[];
  const missing=data.value===null||!data.value.trim();
  if(missing&&(!data.reason.trim()||!data.missing_information.trim()))messages.push("For a missing answer, describe the reason and the information missing from the retained material.");
  if(data.semantic_assessment!=="unassessed"&&!data.reason.trim())messages.push("Explain your human support judgment.");
  if(data.references.some(ref=>!data.inspected_ranges.some(scope=>scope.source_id===ref.source_id&&scope.source_version===ref.source_version&&scope.source_sha256===ref.source_sha256&&scope.blocks_sha256===ref.blocks_sha256&&scope.block_id===ref.block_id&&scope.start<=ref.start&&scope.end>=ref.end)))messages.push("Read and explicitly mark the inspected material containing every attached excerpt.");
  if(data.scope_result==="value_found"&&(missing||!data.inspected_ranges.length))messages.push("Value found needs an answer and material you explicitly marked as inspected.");
  if(data.semantic_assessment==="human_supported"&&(missing||!data.references.length||data.scope_result!=="value_found"))messages.push("Human-supported needs an answer, an attached excerpt and a value-found scope judgment.");
  if(data.scope_result==="not_found_in_inspected_material"&&(!missing||!data.inspected_ranges.length))messages.push("Not found in inspected material needs a blank answer and an explicitly inspected range. It does not establish absence from the paper.");
  return messages;
}
