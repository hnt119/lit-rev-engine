import type {Schema} from "./api";

type Origin=Schema<"CollectionSummary">["origin"];
type Binding={search_id?:string|null;collection_ref?:Extract<Origin,{kind:"collection"}>};

/** Bibliographic projections must retain the actual search or collection binding. */
export function matchesPaperOrigin(origin:Origin,binding:Binding){
  if(origin.kind==="search")return !binding.collection_ref&&binding.search_id===origin.search_id;
  return binding.collection_ref?.collection_id===origin.collection_id&&binding.collection_ref.collection_snapshot_sha256===origin.collection_snapshot_sha256;
}
