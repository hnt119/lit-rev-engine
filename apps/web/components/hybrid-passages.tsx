"use client";
import {useEffect,useState,useRef} from "react";
import {api,requestId,workspacePath,type Schema} from "../lib/api";
import {highlightParts} from "../lib/helpers";
import {registerDraftFlusher,registerUnloadGuard} from "../lib/drafts";
import {Failure,Notice} from "./ui";
import type {ComparisonPassageContext} from "../lib/comparison-passage";
import type {Navigate} from "./workspace-app";
import {SettingsLink} from "../lib/settings-navigation";

type Run=Schema<"HybridSavedRun">;
export function HybridPassages({workspace,context,profile,device,question,topK,ready,saveDraft,navigate}:{workspace:Schema<"WorkspaceSummary">;context?:ComparisonPassageContext;profile:string;device:"cpu"|"mps";question:string;topK:number;ready:boolean;saveDraft:()=>Promise<void>;navigate:Navigate}){
  const [busy,setBusy]=useState(""),[job,setJob]=useState(""),[error,setError]=useState(""),[index,setIndex]=useState<{state:string;reason?:string;coverage?:unknown}>({state:"not_checked"});
  const [runs,setRuns]=useState<Run[]>([]),[selected,setSelected]=useState<Run|null>(null),[inspected,setInspected]=useState<Schema<"HybridSourceContext">|null>(null),[failedSearch,setFailedSearch]=useState(false);
  const active=useRef(false);active.current=!!busy;
  useEffect(()=>registerDraftFlusher(async()=>{if(active.current)throw new Error("Wait for hybrid work to finish or cancel it before leaving. Source and query drafts remain saved.");}),[]);
  useEffect(()=>registerUnloadGuard(()=>active.current),[]);
  const endpoint=workspacePath(workspace.id),scope=context?{board_id:context.board_id,board_revision_id:context.board_revision_id,paper_id:context.paper_id??null,field_id:context.field_id??null}:null;
  const binding={profile_id:profile,device,expected_preparation_id:context?.preparation_id??workspace.current_preparation_id,expected_source_revision:context?.source_revision??workspace.source_revision,board_context:scope};
  const signature=JSON.stringify(binding);
  const sameScope=(run:Run)=>run.result.profile_id===profile&&JSON.stringify(run.board_context)===JSON.stringify(scope);
  async function loadHistory(){const value=await api<Schema<"HybridRunListing">>(endpoint+"/hybrid-runs");setRuns(value.runs.filter(sameScope));}
  useEffect(()=>{let active=true;setSelected(null);setInspected(null);setIndex({state:"not_checked"});api<Schema<"HybridRunListing">>(endpoint+"/hybrid-runs").then(value=>{if(active)setRuns(value.runs.filter(sameScope));}).catch(error=>{if(active)setError(error.message);});return()=>{active=false;};},[endpoint,signature]);
  async function run(kind:"status"|"index"|"search",fresh=false){
    if(!ready)return;setBusy(kind);setError("");setInspected(null);
    const id=crypto.randomUUID();setJob(id);
    try{
      await saveDraft();
      if(kind==="search"){
        const payload={...binding,question,top_k:topK};
        const operationId=await requestId(endpoint+":hybrid:"+profile,payload,fresh);setJob(operationId);
        const result=await api<Run>(endpoint+"/hybrid-runs","POST",{...payload,request_id:operationId});
        if(result.preparation_id!==binding.expected_preparation_id||result.source_revision!==binding.expected_source_revision||result.result.profile_id!==profile||JSON.stringify(result.board_context)!==JSON.stringify(scope))throw new Error("The hybrid receipt does not match this exact source and comparison scope.");
        setSelected(result);setFailedSearch(false);await loadHistory();
      }else{
        const result=await api<typeof index>(endpoint+(kind==="status"?"/hybrid-index/status":"/hybrid-index"),"POST",{...binding,request_id:id});setIndex(result);
      }
    }catch(error){setError((error as Error).message);if(kind==="search")setFailedSearch(true);}finally{setBusy("");setJob("");}
  }
  async function cancel(){if(!job)return;try{await api(endpoint+"/hybrid-jobs/"+encodeURIComponent(job)+"/cancel","POST");}catch(error){setError((error as Error).message);}}
  async function inspect(candidate:Schema<"HybridCandidate">){if(!selected)return;setError("");try{const value=await api<Schema<"HybridSourceContext">>(endpoint+"/hybrid-runs/"+encodeURIComponent(selected.id)+"/candidates/"+encodeURIComponent(candidate.candidate_id)+"/context");if(value.reference.quote!==candidate.reference.quote||value.reference.paper_id!==candidate.reference.paper_id)throw new Error("The source inspector did not return the exact saved candidate.");setInspected(value);}catch(error){setError((error as Error).message);}}
  return <section aria-label="Hybrid evidence retrieval"><p className="eyebrow">EXPERIMENTAL LOCAL HYBRID RETRIEVAL · {device.toUpperCase()} · FLOAT32</p><p>{profile.includes("medcpt")?"MedCPT passage retrieval is an adaptation of its title/abstract use case. Its relevance logits and nearest passages do not certify evidence support.":"Qwen retrieval uses separate dense candidates, rank fusion and a bounded reranker. Relevance scores do not certify evidence support."}</p><Failure message={error}/><p role="status">Source index: {index.state.replaceAll("_"," ")}{index.reason?" · "+index.reason:""}</p><p className="muted">Install and check the optional pack in Settings, then explicitly index these sources. Opening this page never embeds, reranks or downloads anything. Broad queries are validated in full; an over-budget query requires explicit shortening or researcher-defined components.</p><SettingsLink section="retrieval">Manage evidence retrieval packs</SettingsLink><div className="actions"><button type="button" disabled={!!busy||!ready} onClick={()=>void run("status")}>Check index for these sources</button><button type="button" disabled={!!busy||!ready} onClick={()=>void run("index")}>Index these sources</button><button type="button" className="primary" disabled={failedSearch||!!busy||!ready||!question.trim()||!Number.isInteger(topK)||topK<5||topK>30} onClick={()=>void run("search")}>{busy==="search"?"Retrieving with selected hybrid profile…":"Retrieve hybrid passages"}</button>{failedSearch&&<button type="button" disabled={!!busy||!ready} onClick={()=>void run("search",true)}>Start a new hybrid attempt</button>}{busy&&<button type="button" onClick={()=>void cancel()}>Cancel retrieval work</button>}</div>
    <label>Saved hybrid history<select disabled={!!busy} value={selected?.id??""} onChange={event=>{setSelected(runs.find(run=>run.id===event.target.value)??null);setInspected(null);}}><option value="">Choose a saved hybrid run</option>{runs.map(run=><option key={run.id} value={run.id}>{run.created_at} · {run.result.returned_count} candidates · {run.result.profile_id}</option>)}</select></label><p><a href={"/api/v1/"+endpoint+"/hybrid-exports"} download>Export saved hybrid receipts</a></p>
    {selected&&<><h3>{selected.result.original_query}</h3><p className="meta">{selected.result.returned_count} / {selected.result.requested_count} REQUESTED · {selected.result.coverage.indexed_windows} INDEXED WINDOWS · {selected.result.coverage.unindexed_characters} SOURCE CHARACTERS UNINDEXED</p>{!selected.result.coverage.complete&&<Notice>Indexing coverage is incomplete. Omitted source text was not searched; inspect the full receipt.</Notice>}<details><summary>Complete versioned hybrid receipt</summary><pre>{JSON.stringify(selected,null,2)}</pre></details>{selected.result.candidates.map(candidate=><article key={candidate.candidate_id} className="passage"><p className="eyebrow">CANDIDATE {candidate.rank} · {candidate.source_type.replaceAll("_"," ")} · {candidate.branch_membership.join(" + ")}</p><blockquote>{candidate.reference.quote}</blockquote><p className="meta">{candidate.reference.paper_id} · SOURCE {candidate.reference.source_version} · EXACT CODE POINTS {candidate.reference.start}–{candidate.reference.end}</p><div className="actions"><button onClick={()=>void inspect(candidate)}>Inspect exact source · candidate {candidate.rank}</button>{context?.paper_id&&context.field_id&&<button onClick={async()=>{await saveDraft();await navigate({page:"compare",workspace:workspace.id,board:context.board_id,revision:context.board_revision_id,paper:context.paper_id!,field:context.field_id!,run:selected.id,passage:candidate.candidate_id,returnTo:"cell"});}}>Open in comparison cell · candidate {candidate.rank}</button>}</div></article>)}</>}
    {inspected&&<div className="source-context-section"><h3>Exact retained source</h3><p className="meta">{inspected.paper.title} · {JSON.stringify(inspected.block.locator)} · HALF-OPEN UNICODE CODE POINTS {inspected.reference.start}–{inspected.reference.end}</p><div className="source-text">{(()=>{const parts=highlightParts(inspected.block.text,inspected.reference.start-inspected.block.start,inspected.reference.end-inspected.block.start);return <>{parts[0]}<mark>{parts[1]}</mark>{parts[2]}</>;})()}</div><p>Inspection does not attach evidence or declare support. Comparison cells retain the same explicit inspect, attach and submit flow.</p></div>}
  </section>;
}
