"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,requestId,workspacePath,type Schema} from "../lib/api";
import {Failure,Notice,Time} from "./ui";
import SemanticMap from "./semantic-map";
import type {Coordinate} from "../lib/map-view";

type Props={workspaceId:string;search:Schema<"SearchPreview">;capability:Schema<"MapCapability">;requestedMap?:string;visibleIds:Set<string>;selectedIds:Set<string>;inspectedId:string|null;hoveredId:string|null;onInspect:(id:string)=>void;onHover:(id:string|null)=>void;onChooseMap:(id:string)=>void};
const active=(job:Schema<"MapJobView">|null)=>!!job&&["queued","running","cancel_requested"].includes(job.status);

export default function MapExplorer({workspaceId,search,capability,requestedMap,visibleIds,selectedIds,inspectedId,hoveredId,onInspect,onHover,onChooseMap}:Props) {
  const root=workspacePath(workspaceId);
  const [listing,setListing]=useState<Schema<"MapListing">|null>(null);
  const [view,setView]=useState<Schema<"MapView">|null>(null);
  const [job,setJob]=useState<Schema<"MapJobView">|null>(null);
  const [neighbors,setNeighbors]=useState<Schema<"Neighbors">|null>(null);
  const [error,setError]=useState("");const [neighborError,setNeighborError]=useState("");const [busy,setBusy]=useState(false);
  const autoSelect=useRef<string|null>(null);
  const loadListing=useCallback(async()=>{
    const value=await api<Schema<"MapListing">>(root+"/maps?search_id="+encodeURIComponent(search.id));
    setListing(value);
    const newest=[...value.jobs].sort((a,b)=>b.created_at.localeCompare(a.created_at))[0];
    setJob(previous=>previous&&active(previous)?previous:newest??null);
    return value;
  },[root,search.id]);
  useEffect(()=>{void loadListing().catch(error=>setError(error.message));},[loadListing]);
  const maps=listing?[...listing.maps].sort((a,b)=>b.created_at.localeCompare(a.created_at)):[];
  const mapId=requestedMap??maps[0]?.map_id;
  useEffect(()=>{
    setView(null);setNeighbors(null);setNeighborError("");
    if(!mapId||!listing)return;
    if(!listing.maps.some(map=>map.map_id===mapId)){setError("This map is not part of the selected saved search. Choose one of its saved maps.");return;}
    let disposed=false;
    api<Schema<"MapView">>(root+"/maps/"+encodeURIComponent(mapId)).then(value=>{if(disposed)return;if(value.artifact.search_id!==search.id)throw new Error("The map does not belong to this saved search.");setView(value);setError("");}).catch(error=>{if(!disposed)setError(error.message);});
    return()=>{disposed=true;};
  },[root,search.id,mapId,listing]);
  useEffect(()=>{
    if(!job||!active(job))return;
    let disposed=false;let timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{
      try {
        const updated=await api<Schema<"MapJobView">>(root+"/jobs/"+encodeURIComponent(job.id));
        if(disposed)return;setJob(updated);
        if(!active(updated)){
          await loadListing();
          if(!disposed&&updated.status==="succeeded"&&autoSelect.current===updated.map_id){autoSelect.current=null;onChooseMap(updated.map_id);}
        }else timer=setTimeout(()=>void poll(),1500);
      }catch(error){if(!disposed){setError((error as Error).message);timer=setTimeout(()=>void poll(),5000);}}
    };
    timer=setTimeout(()=>void poll(),1000);
    return()=>{disposed=true;clearTimeout(timer);};
    // Polling follows one persisted job; paper navigation and filters do not submit work.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[root,job?.id,loadListing]);
  useEffect(()=>{
    setNeighbors(null);setNeighborError("");
    if(!view||!inspectedId||!(inspectedId in view.artifact.coordinates_by_paper_id)||view.counts.embedded_papers<2)return;
    let disposed=false;
    api<Schema<"Neighbors">>(root+"/maps/"+encodeURIComponent(view.artifact.map_id)+"/neighbors/"+encodeURIComponent(inspectedId)).then(value=>{if(!disposed)setNeighbors(value);}).catch(error=>{if(!disposed)setNeighborError(error.message);});
    return()=>{disposed=true;};
  },[root,view,inspectedId]);
  async function build(rebuild=false){setBusy(true);setError("");try{
    const payload={search_id:search.id,profile_id:"paper_bge_v1",rebuild};
    const submitted=await api<Schema<"MapSubmission">>(root+"/maps","POST",{...payload,request_id:await requestId(workspaceId+":map:"+search.id,payload,rebuild)});
    setJob(submitted.job);autoSelect.current=submitted.job.map_id;
    await loadListing();
    if(submitted.job.status==="succeeded"){autoSelect.current=null;onChooseMap(submitted.job.map_id);}
  }catch(error){setError((error as Error).message);}finally{setBusy(false);}}
  async function cancel(){if(!job)return;setBusy(true);setError("");try{setJob(await api<Schema<"MapJobView">>(root+"/jobs/"+encodeURIComponent(job.id)+"/cancel","POST",{}));}catch(error){setError((error as Error).message);}finally{setBusy(false);}}
  const coordinates=view?.artifact.coordinates_by_paper_id as Record<string,Coordinate>|undefined;
  const visibleCount=coordinates?Object.keys(coordinates).filter(id=>visibleIds.has(id)).length:0;
  const excludedInspected=view?.artifact.excluded_papers_with_reasons.find(paper=>paper.paper_id===inspectedId);
  return <section className="map-section" aria-label="Semantic exploration"><h2>Semantic map</h2><Notice>Approximate semantic layout of this search preview; not all literature and not evidence quality.</Notice><Failure message={error}/>
    {!capability.ready&&<Notice>Map unavailable: setup required. {capability.reason} The paper list and evidence workflow remain available; saved maps can still be inspected.</Notice>}
    <div className="actions"><button className="primary" disabled={!capability.ready||busy||active(job)} onClick={()=>void build()}>{busy?"Submitting…":maps.length?"Create or reuse map":"Build map of this saved search"}</button>{!!maps.length&&<button disabled={!capability.ready||busy||active(job)} onClick={()=>void build(true)}>Explicitly rebuild as a new map</button>}</div>
    {job&&<div className="map-job" role="status"><p className="meta">MAP JOB {job.id} · {job.status.replaceAll("_"," ")} · ATTEMPT {job.attempt}/{job.max_attempts}{job.interrupted_count?` · ${job.interrupted_count} interrupted attempt(s) recovered`:""}</p><p>{job.progress_completed} of {job.progress_total} papers processed</p>{job.progress_total>0&&<progress max={job.progress_total} value={job.progress_completed}>{job.progress_completed}/{job.progress_total}</progress>}{job.error&&<Failure message={job.error.message}/>}<div className="actions">{active(job)&&job.status!=="cancel_requested"&&<button disabled={busy} onClick={()=>void cancel()}>Cancel map build</button>}{job.status==="cancel_requested"&&<p>Cancellation requested; completed work may already have finished.</p>}{["failed","cancelled"].includes(job.status)&&<button disabled={!capability.ready||busy} onClick={()=>void build(true)}>Retry map build as a new artifact</button>}</div></div>}
    {maps.length>0&&<label>Saved maps of this search<select value={mapId} onChange={event=>{autoSelect.current=null;onChooseMap(event.target.value);}}>{maps.map(map=><option key={map.map_id} value={map.map_id}>{new Date(map.created_at).toLocaleString()} · {map.projection_method.replaceAll("_"," ")} · {map.embedded_count} papers · {map.map_id.slice(0,8)}</option>)}</select></label>}
    {!listing?<p role="status">Loading saved map records…</p>:!maps.length&&!active(job)?<p>No persisted semantic map for this saved search yet. Opening this page does not download a model or build one.</p>:null}
    {view&&coordinates&&<><p className="counts">{view.counts.provider_reported} provider matches · {view.counts.fetched_records} fetched · {view.counts.distinct_records} distinct · {view.counts.embedded_papers} embedded · {view.counts.excluded_papers} excluded · {visibleCount} visible points · {selectedIds.size} selected for exploration</p><p className="meta">{view.artifact.projection_method.replaceAll("_"," ")} · <Time value={view.artifact.created_at}/> · SAVED COORDINATES</p>
      {view.artifact.status==="single_paper"?<Notice>One embedded paper: there is no semantic landscape or within-search neighbor comparison.</Notice>:view.artifact.status==="empty"?<Notice>No usable embeddings. Exclusions are recorded below; no positions were fabricated.</Notice>:<p className="muted">Nearby points can reflect projection distortion. Similarity values below use original embedding vectors, not screen distance.</p>}
      {view.counts.embedded_papers>0&&<SemanticMap key={view.artifact.map_id} coordinates={coordinates} papers={search.papers} visibleIds={visibleIds} selectedIds={selectedIds} inspectedId={inspectedId} hoveredId={hoveredId} onInspect={onInspect} onHover={onHover}/>}
      {inspectedId&&<div className="neighbor-list"><h3>Similar in this search</h3><Failure message={neighborError}/>{excludedInspected?<p>This paper was excluded from embedding: {excludedInspected.reason}</p>:view.counts.embedded_papers<2?<p>No neighboring papers are available in this map.</p>:neighbors?<><p className="muted">Original-space cosine similarity; it does not measure study quality, applicability or evidence strength.</p>{neighbors.neighbors.length?<ol>{neighbors.neighbors.map(neighbor=><li key={neighbor.paper_id}><button className="text-button" onClick={()=>onInspect(neighbor.paper_id)}>{search.papers.find(paper=>paper.id===neighbor.paper_id)?.title??neighbor.paper_id}</button><span className="meta"> · COSINE {neighbor.cosine_similarity.toFixed(4)}</span></li>)}</ol>:<p>No other embedded paper is available.</p>}</>:<p role="status">Loading within-search similarities…</p>}</div>}
      {!!view.artifact.excluded_papers_with_reasons.length&&<details><summary>Excluded papers ({view.counts.excluded_papers})</summary>{view.artifact.excluded_papers_with_reasons.map(item=><p key={item.paper_id}><button className="text-button" onClick={()=>onInspect(item.paper_id)}>{search.papers.find(paper=>paper.id===item.paper_id)?.title??item.paper_id}</button><br/>{item.reason}</p>)}</details>}
      <details><summary>Saved map manifest and representation provenance</summary><p className="muted">Title-only papers: {Object.values(view.artifact.representation_by_paper_id).filter(value=>value==="title_only").length}. Long inputs use the recorded full-input window policy.</p><pre>{JSON.stringify(view.artifact,null,2)}</pre></details>
    </>}
  </section>;
}
