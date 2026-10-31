"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,requestId,workspacePath,type Schema} from "../lib/api";
import {Failure,Notice,Time} from "./ui";
import SemanticMap from "./semantic-map";
import ExplorationHeading from "./exploration-heading";
import type {Coordinate} from "../lib/map-view";
import {SettingsLink} from "../lib/settings-navigation";

type Props={workspaceId:string;search:Schema<"SearchPreview">;capability:Schema<"MapCapability">;requestedMap?:string;visibleIds:Set<string>;selectedIds:Set<string>;selectionLimit?:number;inspectedId:string|null;hoveredId:string|null;onInspect:(id:string)=>void;onHover:(id:string|null)=>void;onChooseMap:(id:string)=>void};
type SharedProps=Omit<Props,"search">;
type Origin={kind:"search";search_id:string}|Schema<"CollectionInputRef">;
type MapJob=Schema<"MapJobView">|Schema<"CollectionMapJobView">;
type View=Schema<"MapView">|Schema<"CollectionMapView">;
type Listing=Schema<"MapListing">|Schema<"CollectionMapListing">;
const active=(job:MapJob|null)=>!!job&&["queued","running","cancel_requested"].includes(job.status);

export default function MapExplorer({search,...props}:Props){return <MapManager key={search.id} {...props} origin={{kind:"search",search_id:search.id}} papers={search.papers}/>;}
export function CollectionMapExplorer({collectionRef,...props}:SharedProps&{collectionRef:Schema<"CollectionInputRef">;papers:Schema<"Paper">[]}){return <MapManager key={collectionRef.collection_id+":"+collectionRef.collection_snapshot_sha256} {...props} origin={collectionRef}/>;}

function MapManager({workspaceId,origin,papers,capability,requestedMap,visibleIds,selectedIds,selectionLimit=30,inspectedId,hoveredId,onInspect,onHover,onChooseMap}:SharedProps&{origin:Origin;papers:Schema<"Paper">[]}) {
  const root=workspacePath(workspaceId);
  const collection=origin.kind==="collection",scopeId=collection?origin.collection_id:origin.search_id,scopeHash=collection?origin.collection_snapshot_sha256:"";
  const mapsEndpoint=root+(collection?"/collection-maps":"/maps"),jobsEndpoint=root+(collection?"/collection-map-jobs":"/jobs");
  function belongs(value:{search_id?:string;collection_ref?:Schema<"CollectionInputRef">}){return collection?value.collection_ref?.collection_id===scopeId&&value.collection_ref.collection_snapshot_sha256===scopeHash:!value.collection_ref&&value.search_id===scopeId;}
  const [listing,setListing]=useState<Listing|null>(null);
  const [view,setView]=useState<View|null>(null);
  const [job,setJob]=useState<MapJob|null>(null);
  const [neighbors,setNeighbors]=useState<Schema<"Neighbors">|null>(null);
  const [error,setError]=useState("");const [neighborError,setNeighborError]=useState("");const [busy,setBusy]=useState(false);
  const autoSelect=useRef<string|null>(null);
  const alive=useRef(false),listingRead=useRef(0),acting=useRef(false),progressGeneration=useRef(0);
  const [progressEpoch,setProgressEpoch]=useState(0);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;listingRead.current++;progressGeneration.current++;};},[]);
  const loadListing=useCallback(async()=>{
    const token=++listingRead.current;
    const value=await api<Listing>(mapsEndpoint+(collection?"?collection_id=":"?search_id=")+encodeURIComponent(scopeId));
    if(!alive.current||token!==listingRead.current)return value;
    if(value.maps.some(item=>!belongs(item))||value.jobs.some(item=>!belongs(item)))throw new Error("Saved map metadata belongs to a different retained paper snapshot.");
    setListing(value);
    const newest=[...value.jobs].sort((a,b)=>b.created_at.localeCompare(a.created_at))[0];
    setJob(previous=>previous&&active(previous)?previous:newest??null);
    return value;
  },[mapsEndpoint,collection,scopeId,scopeHash]);
  useEffect(()=>{void loadListing().catch(error=>setError(error.message));},[loadListing]);
  const maps=listing?[...listing.maps].sort((a,b)=>b.created_at.localeCompare(a.created_at)):[];
  const mapId=requestedMap??maps[0]?.map_id;
  useEffect(()=>{
    setView(null);setNeighbors(null);setNeighborError("");
    if(!mapId||!listing)return;
    if(!listing.maps.some(map=>map.map_id===mapId)){setError("This map is not part of the selected retained paper snapshot. Choose one of its saved maps.");return;}
    let disposed=false;
    api<View>(mapsEndpoint+"/"+encodeURIComponent(mapId)).then(value=>{if(disposed)return;if(!belongs(value.artifact))throw new Error("The map does not belong to this retained paper snapshot.");setView(value);setError("");}).catch(error=>{if(!disposed)setError(error.message);});
    return()=>{disposed=true;};
  },[mapsEndpoint,scopeId,scopeHash,mapId,listing]);
  useEffect(()=>{
    if(!job||!active(job))return;
    let disposed=false;let timer:ReturnType<typeof setTimeout>;const token=progressGeneration.current;
    const poll=async()=>{
      try {
        const updated=await api<MapJob>(jobsEndpoint+"/"+encodeURIComponent(job.id));
        if(disposed||!alive.current||token!==progressGeneration.current)return;if(updated.id!==job.id||!belongs(updated))throw new Error("Map progress belongs to a different retained input.");setJob(updated);
        if(!active(updated)){
          await loadListing();
          if(!disposed&&updated.status==="succeeded"&&autoSelect.current===updated.map_id){autoSelect.current=null;onChooseMap(updated.map_id);}
        }else timer=setTimeout(()=>void poll(),1500);
      }catch(error){if(!disposed&&alive.current&&token===progressGeneration.current){setError((error as Error).message);timer=setTimeout(()=>void poll(),5000);}}
    };
    timer=setTimeout(()=>void poll(),1000);
    return()=>{disposed=true;clearTimeout(timer);};
    // Polling follows one persisted job; paper navigation and filters do not submit work.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[jobsEndpoint,job?.id,loadListing,progressEpoch]);
  useEffect(()=>{
    setNeighbors(null);setNeighborError("");
    if(!view||!inspectedId||!(inspectedId in view.artifact.coordinates_by_paper_id)||view.counts.embedded_papers<2)return;
    let disposed=false;
    api<Schema<"Neighbors">>(mapsEndpoint+"/"+encodeURIComponent(view.artifact.map_id)+"/neighbors/"+encodeURIComponent(inspectedId)).then(value=>{if(!disposed)setNeighbors(value);}).catch(error=>{if(!disposed)setNeighborError(error.message);});
    return()=>{disposed=true;};
  },[mapsEndpoint,view,inspectedId]);
  async function build(rebuild=false){if(acting.current||active(job))return;acting.current=true;setBusy(true);setError("");try{
    const payload={...(origin.kind==="collection"?{collection_ref:{...origin}}:{search_id:origin.search_id}),profile_id:"paper_bge_v1",rebuild};
    const submitted=await api<Schema<"MapSubmission">|Schema<"CollectionMapSubmission">>(mapsEndpoint,"POST",{...payload,request_id:await requestId(workspaceId+(collection?":collection-map:":":map:")+scopeId,payload,rebuild)});
    if(!alive.current)return;
    if(!belongs(submitted.job))throw new Error("The submitted map belongs to a different retained paper snapshot.");
    setJob(submitted.job);autoSelect.current=submitted.job.map_id;
    await loadListing();
    if(alive.current&&submitted.job.status==="succeeded"){autoSelect.current=null;onChooseMap(submitted.job.map_id);}
  }catch(error){if(alive.current)setError((error as Error).message);}finally{acting.current=false;if(alive.current)setBusy(false);}}
  async function cancel(){if(!job||acting.current)return;acting.current=true;setProgressEpoch(++progressGeneration.current);setBusy(true);setError("");try{const next=await api<MapJob>(jobsEndpoint+"/"+encodeURIComponent(job.id)+"/cancel","POST",{});if(!alive.current)return;if(next.id!==job.id||!belongs(next))throw new Error("The cancellation receipt belongs to a different map job.");setProgressEpoch(++progressGeneration.current);setJob(next);}catch(error){if(alive.current)setError((error as Error).message);}finally{acting.current=false;if(alive.current)setBusy(false);}}
  const coordinates=view?.artifact.coordinates_by_paper_id as Record<string,Coordinate>|undefined;
  const visibleCount=coordinates?Object.keys(coordinates).filter(id=>visibleIds.has(id)).length:0;
  const excludedInspected=view?.artifact.excluded_papers_with_reasons.find(paper=>paper.paper_id===inspectedId);
  const needsJobAttention=!!job&&(active(job)||["failed","cancelled"].includes(job.status));
  const buildActions=<div className="actions"><button className="primary" disabled={!capability.ready||busy||active(job)} onClick={()=>build()}>{busy?"Submitting…":maps.length?"Create or reuse map":collection?"Build map of this saved collection":"Build map of this saved search"}</button>{!!maps.length&&<button disabled={!capability.ready||busy||active(job)} onClick={()=>build(true)}>Explicitly rebuild as a new map</button>}</div>;
  const jobStatus=job&&<div className="map-job" role="status"><p className="meta">MAP JOB {job.id} · {job.status.replaceAll("_"," ")} · ATTEMPT {job.attempt}/{job.max_attempts}{job.interrupted_count?` · ${job.interrupted_count} interrupted attempt(s) recovered`:""}</p><p>{job.progress_completed} of {job.progress_total} papers processed</p>{job.progress_total>0&&<progress max={job.progress_total} value={job.progress_completed}>{job.progress_completed}/{job.progress_total}</progress>}{job.error&&<Failure message={job.error.message}/>}<div className="actions">{active(job)&&job.status!=="cancel_requested"&&<button disabled={busy} onClick={()=>cancel()}>Cancel map build</button>}{job.status==="cancel_requested"&&<p>Cancellation requested; completed work may already have finished.</p>}{["failed","cancelled"].includes(job.status)&&<button disabled={!capability.ready||busy} onClick={()=>build(true)}>Retry map build as a new artifact</button>}</div></div>;
  return <section className="map-section" aria-label="Semantic exploration"><ExplorationHeading title="Semantic map" selectedIds={[...selectedIds]} maxSources={selectionLimit} visibleIds={visibleIds} sticky/><Notice>Approximate semantic layout of this {collection?"explicit saved collection":"search preview"}; not all literature and not evidence quality.</Notice><Failure message={error}/>
    {!capability.ready&&!maps.length&&<Notice>New map calculation is not configured. {capability.reason} Saved maps can still be inspected without model weights. <SettingsLink section="maps">Set up semantic maps</SettingsLink></Notice>}
    {!maps.length&&buildActions}
    {(!maps.length||needsJobAttention)&&jobStatus}
    {!listing?<p role="status">Loading saved map records…</p>:!maps.length&&!active(job)?<p>No persisted semantic map for this saved {collection?"collection":"search"} yet. Opening this page does not download a model or build one.</p>:null}
    {view&&coordinates&&<><p className="map-selection-status" role="status" aria-live="polite" aria-atomic="true"><strong>{selectedIds.size} selected for exploration.</strong> Filled markers show selection.</p>
      {view.artifact.status==="single_paper"?<Notice>One embedded paper: there is no semantic landscape or within-{collection?"collection":"search"} neighbor comparison.</Notice>:view.artifact.status==="empty"?<Notice>No usable embeddings. Exclusions are recorded below; no positions were fabricated.</Notice>:null}
      {view.counts.embedded_papers>0&&<SemanticMap key={view.artifact.map_id} coordinates={coordinates} papers={papers} visibleIds={visibleIds} selectedIds={selectedIds} inspectedId={inspectedId} hoveredId={hoveredId} onInspect={onInspect} onHover={onHover}/>}
    </>}
    {maps.length>0&&<details className="map-record-controls"><summary>Saved map & build controls</summary>{!capability.ready&&<Notice>New map calculation requires optional local model setup. This saved map remains usable without it. {capability.reason} <SettingsLink section="maps">Set up semantic maps</SettingsLink></Notice>}<label>Saved maps of this {collection?"collection":"search"}<select value={mapId} onChange={event=>{autoSelect.current=null;onChooseMap(event.target.value);}}>{maps.map(map=><option key={map.map_id} value={map.map_id}>{new Date(map.created_at).toLocaleString()} · {map.projection_method.replaceAll("_"," ")} · {map.embedded_count} papers · {map.map_id.slice(0,8)}</option>)}</select></label>{buildActions}{!needsJobAttention&&jobStatus}</details>}
    {view&&coordinates&&<>
      <p className="counts">{!collection&&<>{view.counts.provider_reported} provider matches · {view.counts.fetched_records} fetched · </>}{view.counts.distinct_records} distinct · {view.counts.embedded_papers} embedded · {view.counts.excluded_papers} excluded · {visibleCount} visible points</p><p className="meta">{view.artifact.projection_method.replaceAll("_"," ")} · <Time value={view.artifact.created_at}/> · SAVED COORDINATES</p>
      {!!view.artifact.projection_parameters?.saved_example_bundle&&<p className="muted">Bundled offline map, computed once from the recorded title/abstract embeddings. Opening, filtering and selecting papers do not run the model or refit these coordinates.</p>}
      {view.counts.embedded_papers>1&&<p className="muted">Nearby points can reflect projection distortion. Similarity values below use original embedding vectors, not screen distance.</p>}
      {inspectedId&&<div className="neighbor-list"><h3>Similar in this {collection?"collection":"search"}</h3><Failure message={neighborError}/>{excludedInspected?<p>This paper was excluded from embedding: {excludedInspected.reason}</p>:view.counts.embedded_papers<2?<p>No neighboring papers are available in this map.</p>:neighbors?<><p className="muted">Original-space cosine similarity; it does not measure study quality, applicability or evidence strength.</p>{neighbors.neighbors.length?<ol>{neighbors.neighbors.map(neighbor=><li key={neighbor.paper_id}><button className="text-button" onClick={()=>onInspect(neighbor.paper_id)}>{papers.find(paper=>paper.id===neighbor.paper_id)?.title??neighbor.paper_id}</button><span className="meta"> · COSINE {neighbor.cosine_similarity.toFixed(4)}</span></li>)}</ol>:<p>No other embedded paper is available.</p>}</>:<p role="status">Loading within-{collection?"collection":"search"} similarities…</p>}</div>}
      {!!view.artifact.excluded_papers_with_reasons.length&&<details><summary>Excluded papers ({view.counts.excluded_papers})</summary>{view.artifact.excluded_papers_with_reasons.map(item=><p key={item.paper_id}><button className="text-button" onClick={()=>onInspect(item.paper_id)}>{papers.find(paper=>paper.id===item.paper_id)?.title??item.paper_id}</button><br/>{item.reason}</p>)}</details>}
      <details><summary>Saved map manifest and representation provenance</summary><p className="muted">Title-only papers: {Object.values(view.artifact.representation_by_paper_id).filter(value=>value==="title_only").length}. Long inputs use the recorded full-input window policy.</p><pre>{JSON.stringify(view.artifact,null,2)}</pre></details>
    </>}
  </section>;
}
