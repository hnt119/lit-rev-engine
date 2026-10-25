"use client";
import {useEffect,useState} from "react";
import {api} from "../lib/api";
import {Failure} from "./ui";
export type HybridJob={id:string;kind:string;state:string;detail:string;retry_allowed?:boolean;progress?:{phase:string;component?:string;completed_batches?:number;total_batches?:number;processed_items?:number;total_items?:number;total_windows?:number}};
/** A projection of existing operational jobs, separate from scientific receipts. */
export function HybridJobStatus({job,waiting=false,error=""}:{job:HybridJob|null;waiting?:boolean;error?:string}){
  if(!job&&!waiting)return null;
  return <aside className="notice" aria-label="Retrieval job progress"><p role="status">{job?job.state.replaceAll("_"," ")+" · "+(job.progress?.phase??job.state).replaceAll("_"," "):"Waiting for the backend to record this operation…"}{job?.progress?.component?" · "+job.progress.component:""}</p>{job?.progress?.total_batches!==undefined&&<p>Completed batches: {job.progress.completed_batches??0} / {job.progress.total_batches}{job.progress.total_items!==undefined?" · processed items: "+(job.progress.processed_items??0)+" / "+job.progress.total_items:""}</p>}{job?.progress?.total_windows!==undefined&&<p>Exact source windows in this index: {job.progress.total_windows}</p>}{job?.detail&&<p>Result: {job.detail.replaceAll("_"," ")}</p>}<p className="muted">This is progress for the current server request, not a durable background task. Cancellation is checked between model loading and batches; an active forward pass may take time to finish. No result or fallback is published after cancellation. Failed or cancelled work requires an explicit new attempt.</p><Failure message={error}/></aside>;
}
/** Bounded local status reads only; opening this view cannot start retrieval. */
export function PollingHybridJobStatus({endpoint,jobId,active}:{endpoint:string;jobId:string;active:boolean}){
  const [job,setJob]=useState<HybridJob|null>(null),[error,setError]=useState(""),[cancelling,setCancelling]=useState(false);
  useEffect(()=>{if(!jobId)return;let alive=true,running=false;setJob(null);setError("");setCancelling(false);async function poll(){if(running)return;running=true;try{const value=await api<HybridJob>(endpoint+"/hybrid-jobs/"+encodeURIComponent(jobId));if(alive){setJob(value);setError("");}}catch(error){if(alive&&!(error instanceof Error&&error.message.includes("does not belong")))setError("Progress could not be refreshed. The original request may still be running; do not start another attempt automatically.");}finally{running=false;}}void poll();const timer=active?setInterval(()=>void poll(),700):null;return()=>{alive=false;if(timer)clearInterval(timer);};},[endpoint,jobId,active]);
  async function cancel(){setCancelling(true);try{setJob(await api<HybridJob>(endpoint+"/hybrid-jobs/"+encodeURIComponent(jobId)+"/cancel","POST"));}catch(error){setError((error as Error).message);setCancelling(false);}}
  if(!jobId)return null;
  return <><HybridJobStatus job={job} waiting={active} error={error}/>{active&&(!job||job.state==="running")&&<button disabled={cancelling} onClick={()=>void cancel()}>{cancelling?"Cancellation requested…":"Cancel retrieval work"}</button>}</>;
}
