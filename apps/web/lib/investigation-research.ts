import type {Schema} from "./api";
export type ResearchDraft={
  schema_version:"mvp.investigation-research-draft.v1";
  investigation_id:string;candidate_ids:string[];original_paper_ids:string[];collection_name:string;
  duplicate_policy:"review_required"|"keep_separate"|"merge_exact";
  handoff_id:string|null;preparation_id:string|null;retrieval_question:string;run_id:string|null;
  inspection_id:string|null;research_question:string;interpretation:string;note_id:string|null;
  expected_note_revision_id:string|null;confirm_inspected:boolean;acknowledge_related_paper:boolean;
  board_question:string;board_paper_ids:string[];
};
export function researchDraft(origin:Schema<"InvestigationOrigin">):ResearchDraft {
  const question=origin.board.question;
  return {schema_version:"mvp.investigation-research-draft.v1",investigation_id:origin.id,candidate_ids:[],original_paper_ids:[],collection_name:"Follow-up research selection",duplicate_policy:"review_required",handoff_id:null,preparation_id:null,retrieval_question:origin.board.fields.find(field=>field.id===origin.field_id)?.subquestion??question,run_id:null,inspection_id:null,research_question:question,interpretation:"",note_id:null,expected_note_revision_id:null,confirm_inspected:false,acknowledge_related_paper:false,board_question:question,board_paper_ids:[]};
}
export const toggleIdentity=(ids:string[],id:string)=>ids.includes(id)?ids.filter(value=>value!==id):[...ids,id];
