"use client";
import {useEffect,useState} from "react";
import {api,workspacePath,type Schema} from "../lib/api";
import {canonical} from "../lib/helpers";
import type {Navigate} from "./workspace-app";
import {Failure} from "./ui";

/** Read the immutable collection's origins, never infer prior human judgments. */
export default function ComparisonLineage({definition,navigate}:{definition:Schema<"BoardView">["definition"];navigate:Navigate}){
  const [origins,setOrigins]=useState<Schema<"InvestigationMemberOrigin">[]>([]),[error,setError]=useState("");
  const collection='collection_ref' in definition?definition.collection_ref:null;
  const identity=canonical(collection),paper=definition.paper_ids[0];
  useEffect(()=>{let active=true;setOrigins([]);setError("");if(!collection||collection.kind!=="collection"||!paper)return;
    void api<Schema<"CollectionPaperDetail">>(workspacePath(definition.workspace_id)+"/collections/"+encodeURIComponent(collection.collection_id)+"/paper?paper_id="+encodeURIComponent(paper)).then(result=>{
      if(canonical(result.origin)!==identity)throw new Error("This comparison's retained collection identity could not be confirmed.");
      if(active)setOrigins(result.member.origins.filter((value):value is Schema<"InvestigationMemberOrigin">=>'investigation_id' in value));
    }).catch(error=>{if(active)setError(error.message);});return()=>{active=false;};
  },[definition.workspace_id,identity,paper]);
  const distinct=origins.filter((item,index)=>origins.findIndex(other=>other.investigation_id===item.investigation_id&&other.original_board_revision_id===item.original_board_revision_id)===index);
  if(!distinct.length&&!error)return null;
  return <aside aria-label="Expanded comparison provenance"><Failure message={error}/>{distinct.length>0&&<><p>This comparison was created from an explicit investigation selection. Its cells start unassessed; original judgments remain on their original board.</p>{distinct.map(item=><div key={item.investigation_id}><button onClick={()=>void navigate({page:"compare",workspace:definition.workspace_id,board:item.original_board_id,revision:item.original_board_revision_id})}>Open original comparison and judgments</button><details><summary>Investigation and original revision provenance</summary><pre>{JSON.stringify(item,null,2)}</pre></details></div>)}</>}</aside>;
}
