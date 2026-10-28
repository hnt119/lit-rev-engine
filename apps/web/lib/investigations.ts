import type {Schema} from "./api";

/** Match the server's meaningful unresolved local-draft entry condition. */
export function unresolvedInvestigationDraft(data:Schema<"BoardCellData">|null):boolean {
  return !!data&&!!((data.value??"").trim()||data.reason.trim()||data.missing_information.trim()||data.references.length||data.inspected_ranges.length)&&
    (data.semantic_assessment!=="human_supported"||data.scope_result!=="value_found"||data.value===null||!!data.missing_information.trim());
}

/** A workflow filter, never a scientific gap or eligibility judgment. */
export function unresolvedCell(view:Schema<"BoardView">,paperId:string,fieldId:string):boolean {
  const cell=view.cells.find(cell=>cell.paper_id===paperId&&cell.field_id===fieldId),head=cell?.head;
  const source=view.definition.sources.find(item=>item.paper_id===paperId);
  return view.freshness!=="current"||!!cell?.draft_version||!source||source.source_type==="none"||!head||
    head.semantic_assessment!=="human_supported"||head.scope_result!=="value_found"||
    head.value===null||!!head.missing_information.trim();
}

export function investigationMatches(view:Schema<"InvestigationView">,workspace:string,board:string,paper:string,field:string):boolean {
  const origin=view.origin;
  return origin.workspace_id===workspace&&origin.board.board_id===board&&origin.paper_id===paper&&origin.field_id===field&&
    view.plan.revision.plan_id===origin.plan_id&&view.plan.revision.workspace_id===workspace;
}
