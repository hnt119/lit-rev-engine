import type {Schema} from "./api";
import {canonical} from "./helpers";

export type ComparisonPassageIdentity={board_id:string;board_revision_id:string;paper_id?:string|null;field_id?:string|null};
// Resolved by the authorized server; URL identifiers are never source bindings.
export type ComparisonPassageContext=Schema<"BoardPassageSearchContext">;
export function comparisonPassageScope(context:ComparisonPassageIdentity){
  const hex=(value:string)=>Array.from(new TextEncoder().encode(value),byte=>byte.toString(16).padStart(2,"0")).join("");
  return "board-evidence:"+[context.board_id,context.board_revision_id,...(context.paper_id&&context.field_id?[hex(context.paper_id),hex(context.field_id)]:[])].join(":");
}

export type ComparisonTablePosition={workspace:string;board:string;revision:string;left:number;top:number};
export function comparisonTablePosition(value:unknown,workspace:string,board:string,revision:string):ComparisonTablePosition|null {
  if(!value||typeof value!=="object")return null;
  const p=value as ComparisonTablePosition;
  return p.workspace===workspace&&p.board===board&&p.revision===revision&&
    [p.left,p.top].every(number=>Number.isFinite(number)&&number>=0&&number<=10000000)?p:null;
}
export function comparisonPassageParams(context:ComparisonPassageIdentity){
  const params=new URLSearchParams({revision_id:context.board_revision_id});
  if(context.paper_id)params.set("paper_id",context.paper_id);
  if(context.field_id)params.set("field_id",context.field_id);
  return params;
}
export function matchesComparisonPassageRun(run:Schema<"RunView">["run"],context:ComparisonPassageContext){
  const stored=run.parameters.board_passage_context;
  if(!stored||typeof stored!=="object"||Array.isArray(stored))return false;
  const value=stored as Record<string,unknown>;
  return run.preparation_id===context.preparation_id&&run.source_revision===context.source_revision&&
    ["board_id","board_revision_id","preparation_id","source_revision","source_manifest_sha256","field_revision_id","board_paper_ids","paper_ids","sources"].every(key=>canonical(value[key])===canonical(context[key as keyof ComparisonPassageContext]))&&
    (value.paper_id??null)===(context.paper_id??null)&&(value.field_id??null)===(context.field_id??null)&&
    run.passages.every(passage=>context.paper_ids.includes(passage.paper_id));
}
export function matchesComparisonPassageSummary(run:Schema<"RunSummary">|Schema<"CollectionRunSummary">,context:ComparisonPassageContext){
  const scope=run.board_context;
  return !!scope&&scope.board_id===context.board_id&&scope.board_revision_id===context.board_revision_id&&
    (scope.paper_id??null)===(context.paper_id??null)&&(scope.field_id??null)===(context.field_id??null)&&
    run.preparation_id===context.preparation_id&&run.source_revision===context.source_revision;
}
