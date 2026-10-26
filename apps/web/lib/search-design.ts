/** Additive design-note DTOs; legacy plan/compiler schemas remain unchanged. */
export type CollectionRef={kind:"collection";collection_id:string;collection_snapshot_sha256:string};
export type DesignNotes={extraction_questions:{id:string;question:string;source_span:{start:number;end:number;text:string}|null}[];term_notes:{concept_id:string;term_id:string;note:string;authority_reference:string}[];external_searches:{id:string;database:string;platform:string;query:string;executed_on:string|null;reported_count:number|null;limits_note:string;collection_ref:CollectionRef|null}[]};
export type DesignNotesView={schema_version:"mvp.search-plan-metadata.v1";plan_id:string;revision_id:string;version:number;latest_version:number;metadata:DesignNotes;term_bindings:{concept_id:string;term_id:string;term_sha256:string;origin:string;state:string;field:string;verification:"unavailable"}[];current:boolean;history:{version:number;saved_at:string}[];saved_at:string|null;terminology_verification:"unavailable"};
export type DesignNotesDraft={plan_id:string;revision_id:string;base_metadata_version:number;metadata:DesignNotes};
export function checkedDesignNotes(value:unknown,plan:string,revision:string):DesignNotesView{
  const item=value as DesignNotesView;
  if(!item||item.schema_version!=="mvp.search-plan-metadata.v1"||item.plan_id!==plan||item.revision_id!==revision||!Number.isSafeInteger(item.version)||item.version<0||!Number.isSafeInteger(item.latest_version)||item.latest_version<item.version||!item.metadata||!Array.isArray(item.metadata.extraction_questions)||!Array.isArray(item.metadata.term_notes)||!Array.isArray(item.metadata.external_searches)||!Array.isArray(item.history)||!Array.isArray(item.term_bindings))throw Error("The design-note response does not match this exact plan revision and schema. Existing notes remain unchanged.");
  return item;
}
