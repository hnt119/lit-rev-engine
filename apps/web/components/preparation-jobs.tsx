"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,APIError,requestId,workspacePath,type Schema} from "../lib/api";
import {Failure,Notice,Time} from "./ui";
import {acknowledgeComparisonHandoff,assertHandoffJob,assertHandoffPreparation,createComparisonHandoff,currentExactPreparation,sameOrderedPapers,type HandoffRecord,type HandoffPreparation} from "../lib/comparison-handoff";
import type {Navigate} from "./workspace-app";

type Job=Schema<"PreparationJobView">|Schema<"CollectionPreparationJobView">;
type Preparation=Schema<"PreparationView">|Schema<"CollectionPreparationView">;
type Origin={kind:"search";search_id:string}|Schema<"CollectionInputRef">;
type Input=Omit<Schema<"PreparationJobRequest">,"request_id">|Omit<Schema<"CollectionPreparationJobRequest">,"request_id">;
type Pending={input:Input;request_id:string;handoff?:HandoffRecord};
type SharedProps={workspace:Schema<"WorkspaceSummary">;selectedPaperIds:string[];selectionReady:boolean;maxSources:number;flushSelection:()=>Promise<void>;refresh:()=>Promise<void>;navigate?:Navigate;question?:string};
type Props=SharedProps&{search:Schema<"SearchPreview">;onPublished:(preparation:Schema<"PreparationView">)=>void};
type CollectionProps=SharedProps&{collectionRef:Schema<"CollectionInputRef">;papers:Schema<"Paper">[];onPublished:(preparation:Schema<"CollectionPreparationView">)=>void};
type ManagerProps=SharedProps&{origin:Origin;papers:Schema<"Paper">[];onPublished:(preparation:Preparation)=>void};
const active=(job:Job|null)=>!!job&&["queued","running","cancel_requested"].includes(job.status);
const failed=(job:Job|null)=>!!job&&["failed","cancelled","stale"].includes(job.status);
const MAX_PROGRESS_CHECKS=1800;
const POLL_INTERVAL_MS=1500;
const words=(value:string)=>value.replaceAll("_"," ");

/** Progress reads never submit provider work; a job always retains its clicked input. */
export default function PreparationJobs(props:Props) {
  return <PreparationManager {...props} origin={{kind:"search",search_id:props.search.id}} papers={props.search.papers} onPublished={value=>{if(!("collection_ref" in value))props.onPublished(value);}}/>;
}

/** A genuine collection binding reuses job lifecycle behavior without inventing a search. */
export function CollectionPreparationJobs(props:CollectionProps){
  return <PreparationManager {...props} origin={props.collectionRef} onPublished={value=>{if("collection_ref" in value)props.onPublished(value);}}/>;
}

function PreparationManager(props:ManagerProps) {
  const {workspace,origin,papers}=props,base=workspacePath(workspace.id),collection=origin.kind==="collection";
  const scopeId=collection?origin.collection_id:origin.search_id,scopeHash=collection?origin.collection_snapshot_sha256:"";
  const endpoint=base+(collection?"/collection-preparation-jobs":"/preparation-jobs");
  function belongs(value:Job|Preparation){return collection?"collection_ref" in value&&value.collection_ref.collection_id===scopeId&&value.collection_ref.collection_snapshot_sha256===scopeHash:"search_id" in value&&value.search_id===scopeId;}
  const latest=useRef(props);latest.current=props;
  const [jobs,setJobs]=useState<Job[]>([]),[job,setJob]=useState<Job|null>(null);
  const jobRef=useRef<Job|null>(null);
  const [ready,setReady]=useState(false),[loading,setLoading]=useState(false),[busy,setBusy]=useState("");
  const [error,setError]=useState(""),[paused,setPaused]=useState(false),[pending,setPending]=useState<Pending|null>(null);
  const [epoch,setEpoch]=useState(0),generation=useRef(0),alive=useRef(false),action=useRef(0),acting=useRef(false);
  const [publicationRetry,setPublicationRetry]=useState(0),[publicationError,setPublicationError]=useState(false),[publicationLoading,setPublicationLoading]=useState(false);
  const completed=useRef(new Set<string>());
  const foreground=useRef<{jobId:string;handoff:HandoffRecord}|null>(null);
  const [preparedReady,setPreparedReady]=useState<Preparation|null>(null);
  const [readyHandoff,setReadyHandoff]=useState<HandoffRecord|null>(null);
  function invalidate(){const next=++generation.current;setEpoch(next);setPaused(false);return next;}
  function current(token:number){return alive.current&&token===generation.current;}
  function remember(value:Job){
    jobRef.current=value;setJob(value);
    setJobs(previous=>[...previous.filter(item=>item.id!==value.id),value].sort((a,b)=>b.created_at.localeCompare(a.created_at)));
  }
  function choose(value:Job){foreground.current=null;setPreparedReady(null);invalidate();setError("");remember(value);}
  async function openComparison(record:HandoffRecord){
    if(!record.data.preparation_id||!latest.current.navigate)return;
    const result=await latest.current.navigate({page:"compare",workspace:workspace.id,preparation:record.data.preparation_id,handoff:record.scope,setup:"new"});
    if(result&&result.status==="blocked")throw new Error(result.message);
  }
  async function continuePrepared(value:HandoffPreparation){
    if(acting.current||!props.navigate)return;
    const ownAction=++action.current;acting.current=true;setBusy("continue");setError("");
    const captured={question:props.question??workspace.question,origin:{...origin},selected_paper_ids:[...value.selected_paper_ids],expected_source_revision:value.source_revision,expected_preparation_id:value.id};
    try{await props.flushSelection();if(!alive.current||ownAction!==action.current)return;const record=await createComparisonHandoff(workspace.id,captured);const acknowledged=await acknowledgeComparisonHandoff(workspace.id,record,{preparation:value});if(!alive.current||ownAction!==action.current)return;setReadyHandoff(acknowledged);await openComparison(acknowledged);}catch(error){if(alive.current)setError((error as Error).message);}finally{if(alive.current&&ownAction===action.current){acting.current=false;setBusy("");}}
  }
  const load=useCallback(async()=>{
    const token=++generation.current;setEpoch(token);setLoading(true);setPaused(false);
    try {
      const result=await api<Schema<"PreparationJobListing">|Schema<"CollectionPreparationJobListing">>(endpoint+(collection?"?collection_id=":"?search_id=")+encodeURIComponent(scopeId));
      if(!alive.current||token!==generation.current)return;
      if(result.jobs.some(item=>item.workspace_id!==workspace.id||!belongs(item)))throw new Error("Preparation jobs do not belong to this retained paper snapshot.");
      const ordered=[...result.jobs].sort((a,b)=>b.created_at.localeCompare(a.created_at));
      setJobs(ordered);setReady(true);setError("");
      const selected=ordered.find(item=>item.id===jobRef.current?.id)??ordered.find(active)??ordered[0]??null;
      jobRef.current=selected;setJob(selected);
    }catch(error){if(alive.current&&token===generation.current)setError((error as Error).message);}
    finally{if(alive.current&&token===generation.current)setLoading(false);}
  },[endpoint,collection,scopeId,scopeHash,workspace.id]);
  useEffect(()=>{
    alive.current=true;acting.current=false;action.current++;completed.current.clear();foreground.current=null;setPreparedReady(null);setReadyHandoff(null);setReady(false);setJobs([]);setJob(null);jobRef.current=null;setPending(null);setError("");
    void load();
    return()=>{alive.current=false;generation.current++;action.current++;};
  },[load]);
  useEffect(()=>{
    if(!active(job))return;
    const token=generation.current,id=job!.id;let disposed=false,checks=0,failures=0;
    let timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{
      if(disposed||!current(token)||jobRef.current?.id!==id)return;
      if(checks++>=MAX_PROGRESS_CHECKS){setPaused(true);return;}
      try {
        const next=await api<Job>(endpoint+"/"+encodeURIComponent(id));
        if(disposed||!current(token)||jobRef.current?.id!==id)return;
        if(next.id!==id||next.workspace_id!==workspace.id||!belongs(next))throw new Error("This preparation receipt does not match the selected job.");
        const previous=jobRef.current;
        if(previous)assertHandoffJob({question:"",origin,selected_paper_ids:previous.selected_paper_ids,expected_source_revision:previous.expected_source_revision,expected_preparation_id:previous.expected_preparation_id,job_id:previous.id,preparation_id:null},next,workspace.id);
        failures=0;remember(next);setError("");
        if(active(next))timer=setTimeout(()=>void poll(),POLL_INTERVAL_MS);
      }catch(error){
        if(disposed||!current(token))return;
        setError((error as Error).message);
        if(++failures>=5)setPaused(true);else timer=setTimeout(()=>void poll(),5000);
      }
    };
    timer=setTimeout(()=>void poll(),POLL_INTERVAL_MS);
    return()=>{disposed=true;clearTimeout(timer);};
    // A single selected persisted job is polled; progress updates do not restart its budget.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[endpoint,job?.id,epoch]);
  useEffect(()=>{
    setPublicationError(false);setPublicationLoading(false);
    if(job?.status!=="succeeded"||!job.result_preparation_id)return;
    const id=job.id,preparationId=job.result_preparation_id,key=id+":"+preparationId,token=generation.current;
    if(completed.current.has(key))return;
    let disposed=false;setPublicationLoading(true);
    void Promise.all([api<Schema<"WorkspaceSummary">>(base),api<Preparation>(base+"/source-preparations/"+encodeURIComponent(preparationId))]).then(async([state,preparation])=>{
      if(disposed||!current(token)||jobRef.current?.id!==id)return;
      if(preparation.id!==preparationId||!belongs(preparation)||!sameOrderedPapers(job.selected_paper_ids,preparation.selected_paper_ids)||job.result_source_revision!==preparation.source_revision)throw new Error("Published sources do not match this preparation job's exact ordered papers and source revision.");
      const currentPreparation=state.current_preparation_id===preparationId&&state.source_revision===preparation.source_revision;
      if(currentPreparation){latest.current.onPublished(preparation);setPreparedReady(preparation);}
      const own=foreground.current;
      if(own?.jobId===id){
        assertHandoffJob(own.handoff.data,job,workspace.id);assertHandoffPreparation(own.handoff.data,preparation,job);
        const acknowledged=await acknowledgeComparisonHandoff(workspace.id,own.handoff,{job,preparation});
        foreground.current=null;setReadyHandoff(acknowledged);
        if(!currentPreparation)throw new Error("This preparation completed, but current sources changed. Open the ready comparison request explicitly after reviewing its retained preparation.");
        await latest.current.refresh();
        if(disposed||!current(token)||jobRef.current?.id!==id)return;
        await openComparison(acknowledged);
      }
      completed.current.add(key);
      if(own?.jobId!==id)await latest.current.refresh();
    }).catch(error=>{if(!disposed&&current(token)){setError((error as Error).message);setPublicationError(true);}}).finally(()=>{if(!disposed&&current(token))setPublicationLoading(false);});
    return()=>{disposed=true;};
    // Callback identities and draft edits must not refetch or reapply an old publication.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[base,scopeId,scopeHash,job?.id,job?.status,job?.result_preparation_id,publicationRetry,epoch]);
  async function submit(fresh=false,retry?:Pending){
    if(acting.current||!ready)return;
    const source=latest.current;
    if(!retry&&(!source.selectionReady||source.selectedPaperIds.length===0||source.selectedPaperIds.length>source.maxSources||jobs.some(active)))return;
    const input:Input=retry?.input??{...(origin.kind==="collection"?{collection_ref:{...origin}}:{search_id:origin.search_id}),paper_ids:[...source.selectedPaperIds],expected_source_revision:source.workspace.source_revision,expected_preparation_id:source.workspace.current_preparation_id};
    const captured={question:source.question??source.workspace.question,origin:{...origin},selected_paper_ids:[...input.paper_ids],expected_source_revision:input.expected_source_revision,expected_preparation_id:input.expected_preparation_id};
    const token=invalidate(),ownAction=++action.current;acting.current=true;setBusy("submit");setError("");
    let attempted:Pending|undefined=retry;
    try {
      if(!retry)await source.flushSelection();
      if(!current(token))return;
      const handoff=retry?.handoff??(source.navigate?await createComparisonHandoff(workspace.id,captured):undefined);
      if(!current(token))return;
      attempted=retry??{input,request_id:await requestId(workspace.id+(collection?":collection-preparation-job:":":preparation-job:")+scopeId,input,fresh),...(handoff?{handoff}:{})};
      if(!current(token))return;
      setPending(attempted);
      const result=await api<Schema<"PreparationSubmission">|Schema<"CollectionPreparationSubmission">>(endpoint,"POST",{...attempted.input,request_id:attempted.request_id});
      if(!current(token))return;
      if(result.job.workspace_id!==workspace.id||!belongs(result.job))throw new Error("Submitted preparation does not match this retained paper snapshot.");
      assertHandoffJob({...captured,job_id:null,preparation_id:null},result.job,workspace.id);
      if(handoff){const acknowledged=await acknowledgeComparisonHandoff(workspace.id,handoff,{job:result.job});if(!current(token))return;foreground.current={jobId:result.job.id,handoff:acknowledged};}
      setPending(null);remember(result.job);
    }catch(error){
      if(current(token)){
        setError((error as Error).message);
        if(error instanceof APIError&&error.status<500)setPending(null);
        else if(attempted)setPending(attempted);
      }
    }finally{if(alive.current&&ownAction===action.current){acting.current=false;setBusy("");}}
  }
  async function cancel(){
    const selected=jobRef.current;if(acting.current||!active(selected)||selected?.status==="cancel_requested")return;
    const id=selected!.id,token=invalidate(),ownAction=++action.current;acting.current=true;setBusy("cancel");setError("");
    try {
      const result=await api<Job>(endpoint+"/"+encodeURIComponent(id)+"/cancel","POST",{});
      if(current(token)&&jobRef.current?.id===id){invalidate();remember(result);}
    }catch(error){if(current(token))setError((error as Error).message);}
    finally{if(alive.current&&ownAction===action.current){acting.current=false;setBusy("");}}
  }
  const selectionChanged=!!job&&JSON.stringify(job.selected_paper_ids)!==JSON.stringify(props.selectedPaperIds);
  const summary=job?["full_text","abstract_only","unavailable","failed","cancelled","pending","preparing"].map(status=>`${job.outcomes.filter(outcome=>outcome.outcome===status).length} ${words(status)}`).join(" · "):"";
  const failedAbstracts=job?.outcomes.filter(outcome=>outcome.outcome==="failed"&&outcome.source_type==="abstract").length??0;
  const disabled=!ready||loading||!!busy||publicationLoading||!!pending||!props.selectionReady||props.selectedPaperIds.length===0||props.selectedPaperIds.length>props.maxSources||jobs.some(active);
  const reusable=currentExactPreparation(workspace,origin,props.selectedPaperIds);
  return <div aria-label="Source preparation jobs"><Failure message={error}/>
    <p className="muted">Preparation runs as a saved job. Per-paper outcomes are retained; the previous current sources stay usable until a new preparation is published.</p>
    <div className="actions">{props.navigate&&reusable?<button type="button" className="primary" disabled={!!busy||!props.selectionReady||!!pending} onClick={()=>continuePrepared(reusable)}>{busy==="continue"?"Opening comparison…":`Continue to comparison (${reusable.selected_paper_ids.length})`}</button>:<button type="button" className="primary" disabled={disabled} onClick={()=>submit(failed(job))}>{busy==="submit"?"Submitting preparation…":props.navigate?`Prepare & compare (${props.selectedPaperIds.length})`:failed(job)?"Start a new preparation attempt":"Prepare selected sources"}</button>}
      {workspace.current_preparation_id&&<button type="button" disabled={disabled} onClick={()=>submit(true)}>Explicitly refresh sources</button>}
      <button type="button" disabled={!!busy||loading} onClick={load}>{loading?"Loading jobs…":"Reload preparation jobs"}</button></div>
    {readyHandoff&&<p role="status">The captured papers are ready for comparison. <button type="button" disabled={!!busy} onClick={()=>openComparison(readyHandoff).catch(error=>setError(error.message))}>Open ready comparison ({readyHandoff.data.selected_paper_ids.length})</button></p>}
    {pending&&<Notice>The submission result is unresolved. Retry the same saved input ({pending.input.paper_ids.length} papers); editing the current selection does not retarget it. <button type="button" disabled={!!busy} onClick={()=>submit(false,pending)}>Retry same submission</button></Notice>}
    {!ready&&!error&&<p role="status">Loading saved preparation jobs…</p>}
    {jobs.length>1&&<label>Saved preparation job<select value={job?.id??""} disabled={!!busy} onChange={event=>{const value=jobs.find(item=>item.id===event.target.value);if(value)choose(value);}}>{jobs.map(item=><option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} · {words(item.status)} · {item.selected_paper_ids.length} papers</option>)}</select></label>}
    {job&&<section aria-label="Preparation job receipt"><p className="meta">PREPARATION JOB {job.id} · {words(job.status)} · <Time value={job.created_at}/></p>
      <p role="status" aria-live="polite">{job.progress_completed} of {job.progress_total} sources processed · attempt {job.attempt} of {job.max_attempts}{job.interrupted_count?` · ${job.interrupted_count} interrupted attempt(s) recovered`:""}</p>
      <p className="counts" aria-label="Per-paper preparation outcome counts">{summary}{failedAbstracts>0&&` · ${failedAbstracts} failed outcome(s) retain an abstract fallback`}</p>
      {job.progress_total>0&&<progress max={job.progress_total} value={job.progress_completed}>{job.progress_completed}/{job.progress_total}</progress>}
      <p className="meta">ELAPSED {Math.round(job.elapsed_seconds)} SECONDS · RUNTIME LIMIT {job.max_runtime_seconds} SECONDS</p>
      {active(job)&&job.active_paper_id&&<p className="muted">Processing: {papers.find(paper=>paper.id===job.active_paper_id)?.title??job.active_paper_id}</p>}
      {selectionChanged&&<Notice>Your selection differs from this job's frozen input. The running or saved job keeps its original ordered papers.</Notice>}
      <Failure message={job.error?.message??""}/>
      {active(job)&&<div className="actions"><button type="button" disabled={!!busy||job.status==="cancel_requested"} onClick={cancel}>{job.status==="cancel_requested"?"Cancellation requested":busy==="cancel"?"Requesting cancellation…":"Cancel preparation"}</button></div>}
      {paused&&<Notice>Automatic progress checks are paused after a bounded number of reads or repeated connection failures. The server job may still be running. <button type="button" onClick={()=>{invalidate();setError("");}}>Resume progress checks</button></Notice>}
      {job.status==="succeeded"&&<p>Published preparation {job.result_preparation_id} · source revision {job.result_source_revision}. Completion includes the recorded abstract-only, unavailable and failed outcomes; it does not establish complete full-text coverage.</p>}
      {props.navigate&&preparedReady&&!reusable&&!readyHandoff&&<button type="button" disabled={!!busy} onClick={()=>continuePrepared(preparedReady)}>Compare this prepared selection ({preparedReady.selected_paper_ids.length})</button>}
      {failed(job)&&<Notice>This job did not publish a new current preparation. Its recorded staged outcomes remain inspectable; starting another attempt is an explicit action.</Notice>}
      {publicationLoading&&<p role="status">Loading published source metadata…</p>}
      {publicationError&&<button type="button" onClick={()=>{completed.current.delete(job.id+":"+job.result_preparation_id);setPublicationRetry(previous=>previous+1);}}>Reload published source metadata</button>}
      <details><summary>Per-paper outcomes and exact job input ({job.selected_paper_ids.length})</summary><p className="meta">{"collection_ref" in job?`COLLECTION ${job.collection_ref.collection_id}`:`SEARCH ${job.search_id}`} · EXPECTED SOURCE REVISION {job.expected_source_revision} · EXPECTED PREPARATION {job.expected_preparation_id??"none"}</p><p className="hash">SNAPSHOT {"collection_ref" in job?job.collection_ref.collection_snapshot_sha256:job.search_snapshot_sha256}</p><ol>{job.outcomes.map(outcome=><li key={outcome.paper_id}><p>{papers.find(paper=>paper.id===outcome.paper_id)?.title??outcome.paper_id}</p><p className="meta">{outcome.paper_id} · {words(outcome.outcome)}{outcome.source_type?` · ${words(outcome.source_type)}`:""}{outcome.source_status?` · ${words(outcome.source_status)}`:""}</p><Failure message={outcome.error?.message??""}/></li>)}</ol></details>
    </section>}
  </div>;
}
