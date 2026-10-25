"use client";
import {useEffect,useState} from "react";
import {api,type Schema} from "../lib/api";
import type {CellData} from "../lib/board-drafts";
import {Failure} from "./ui";

/** A small read-only projection of an existing bound reference, never an evidence editor. */
export default function RetainedExcerpt({range,quote,index,endpoint,revisionId,paperId,citation,disabled,canRemove,onInspect,onRemove}:{range:CellData["references"][number];quote?:string;index:number;endpoint:string;revisionId:string;paperId:string;citation:string;disabled:boolean;canRemove:boolean;onInspect:()=>Promise<void>;onRemove:()=>void}) {
  const [text,setText]=useState(quote??""),[omitted,setOmitted]=useState(0),[error,setError]=useState("");
  useEffect(()=>{let active=true;setText(quote??"");setError("");setOmitted(0);if(quote!==undefined)return;
    const params=new URLSearchParams({revision_id:revisionId,block_id:range.block_id,start:String(range.start),offset:"0",limit:"1"});
    api<Schema<"BoardSourceInspection">>(endpoint+"/sources/"+encodeURIComponent(range.source_id)+"/blocks?"+params).then(value=>{
      const block=value.blocks.find(block=>block.block_id===range.block_id);
      if(!block||block.paper_id!==paperId||block.source_id!==range.source_id||block.reference.source_version!==range.source_version||block.reference.source_sha256!==range.source_sha256||block.reference.blocks_sha256!==range.blocks_sha256||range.start<block.start||range.start>=block.end)throw new Error("This retained excerpt could not be displayed against its exact source binding. Inspect it before changing the entry.");
      if(active){setText(Array.from(block.text).slice(range.start-block.start,Math.min(range.end,block.end)-block.start).join(""));setOmitted(Math.max(0,range.end-block.end));}
    }).catch(error=>{if(active)setError(error.message);});return()=>{active=false;};
  },[endpoint,revisionId,paperId,range.source_id,range.source_version,range.source_sha256,range.blocks_sha256,range.block_id,range.start,range.end,quote]);
  return <article className="retained-excerpt"><p className="meta">EXCERPT {index+1} · {citation}</p>{text?<blockquote>{text}</blockquote>:!error&&<p className="muted">Loading the retained exact excerpt…</p>}<Failure message={error}/>{omitted>0&&<p className="muted">This summary omits {omitted} later code points. Inspect adjacent source ranges to read the rest.</p>}<div className="actions"><button type="button" disabled={disabled} onClick={()=>onInspect()}>Inspect selected excerpt {index+1}</button>{canRemove&&<button type="button" disabled={disabled} onClick={onRemove}>Remove selected excerpt {index+1}</button>}</div></article>;
}
