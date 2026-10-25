"use client";
import {useEffect,useLayoutEffect,useRef,useState} from "react";
import {api,requestId,workspacePath,type Schema} from "../lib/api";
import {DraftStatus,flushDrafts,useDraft} from "../lib/drafts";
import {adjacentVisiblePaper,preparedSourceLimit,toggleSelectedPaper} from "../lib/paper-selection";
import {Citation,Failure,Notice,SourceMetadata,Time} from "./ui";
import {CollectionPreparationJobs} from "./preparation-jobs";
import {matchesPaperOrigin} from "../lib/paper-origin";
import {CollectionMapExplorer} from "./map-explorer";
import ExplorationPanels from "./exploration-panels";
import ExplorationHeading from "./exploration-heading";
import {canonical} from "../lib/helpers";
import {IntakeGuardNotice,useIntakeGuard} from "./intake-guard";
import type {Navigate} from "./workspace-app";

type Summary=Schema<"CollectionSummary">;
type Origin=Summary["origin"];
type Props={workspaceId:string;onChoose:(summary:Summary)=>Promise<void>};
const size=50;

/** Mounting is explicit: the legacy Discover path makes no collection requests. */
export function CollectionPicker({workspaceId,onChoose,subset}:Props&{subset?:{collection:Summary;paperIds:string[]}}){
  const endpoint=workspacePath(workspaceId)+"/collections";
  const [collections,setCollections]=useState<Summary[]>(subset?[subset.collection]:[]),[error,setError]=useState(""),[busy,setBusy]=useState("");
  const [sources,setSources]=useState<string[]>(subset?[subset.collection.id]:[]),[name,setName]=useState(subset?(subset.collection.name+" · selected subset").slice(0,200):"Combined papers"),[policy,setPolicy]=useState<Schema<"CombineCollectionsRequest">["duplicate_policy"]>("review_required");
  const [preview,setPreview]=useState<Schema<"CombineCollectionsPreview">|null>(null),[conflicts,setConflicts]=useState<Record<string,"keep_separate">>({});
  const generation=useRef(0),acting=useRef(false),alive=useRef(false),pendingReview=useRef(false);
  const reviewSnapshot=canonical({sources,name,policy,conflicts,preview:preview?.input_sha256??null});
  const initialName=subset?(subset.collection.name+" · selected subset").slice(0,200):"Combined papers";
  const baseline=useRef(canonical({sources:subset?[subset.collection.id]:[],name:initialName,policy:"review_required",conflicts:{},preview:null}));
  const guard=useIntakeGuard({dirty:()=>reviewSnapshot!==baseline.current,pending:()=>pendingReview.current,restore:()=>{generation.current++;setSources(subset?[subset.collection.id]:[]);setName(initialName);setPolicy("review_required");setConflicts({});setPreview(null);baseline.current=canonical({sources:subset?[subset.collection.id]:[],name:initialName,policy:"review_required",conflicts:{},preview:null});},message:"This collection combination or subset has an unfinished local review. Commit it or explicitly reset the reviewed inputs before leaving. Existing collections remain retained."});
  useEffect(()=>{alive.current=true;let disposed=false;if(!subset)api<Schema<"CollectionListing">>(endpoint).then(value=>{if(!disposed)setCollections(value.collections);}).catch(error=>{if(!disposed)setError(error.message);});return()=>{disposed=true;alive.current=false;generation.current++;};},[endpoint,!!subset]);
  const subsetKey=subset?JSON.stringify([subset.collection.origin,subset.paperIds]):"";
  useEffect(()=>{generation.current++;setPreview(null);setConflicts({});},[subsetKey]);
  function invalidate(){generation.current++;setPreview(null);setConflicts({});setError("");}
  function selectedSources(){return subset?[{origin:subset.collection.origin,paper_ids:[...subset.paperIds]}]:sources.map(id=>collections.find(item=>item.id===id)).filter((item):item is Summary=>!!item).map(item=>({origin:item.origin,paper_ids:null}));}
  async function combine(previewOnly:boolean){
    if(acting.current||sources.length<1||sources.length>10||subset&&!subset.paperIds.length||!name.trim()||!previewOnly&&!preview)return;
    acting.current=true;pendingReview.current=true;setBusy(previewOnly?"preview":"combine");setError("");const token=generation.current;
    try{
      const payload={name,sources:selectedSources(),duplicate_policy:policy,conflict_decisions:{...conflicts},preview_sha256:previewOnly?null:preview!.input_sha256};
      const id=await requestId(workspaceId+":collection:"+(previewOnly?"preview":"combine"),payload);
      if(previewOnly){const value=await api<Schema<"CombineCollectionsPreview">>(endpoint+"/combine-preview","POST",{...payload,request_id:id});if(alive.current&&token===generation.current){setPreview(value);setConflicts({});}}
      else {const value=await api<Summary>(endpoint+"/combine","POST",{...payload,request_id:id});if(alive.current&&token===generation.current){baseline.current=reviewSnapshot;pendingReview.current=false;await onChoose(value);}}
    }catch(error){if(alive.current&&token===generation.current)setError((error as Error).message);}
    finally{pendingReview.current=false;acting.current=false;if(alive.current)setBusy("");}
  }
  const blocked=preview?.duplicate_groups.some(group=>group.kind==="exact_identifier_duplicate"?policy==="review_required":conflicts[group.id]!=="keep_separate");
  return <section aria-label={subset?"Selected subset review":"Saved paper collections"}><h2>{subset?"Selected subset review":"Saved paper collections"}</h2><Failure message={error}/><IntakeGuardNotice guard={guard}/>
    <p className="muted">Search captures, imported records and explicit combinations retain their own origins. Opening a collection makes no provider request.</p>
    {!subset&&(!collections.length?<p>No saved searches or imported collections are available yet.</p>:collections.map(item=><article key={item.id}><h3><button type="button" className="text-button" disabled={!!busy} onClick={()=>onChoose(item)}>{item.name}</button></h3><p className="meta">{item.kind.replaceAll("_"," ")} · {item.member_count} records · <Time value={item.created_at}/></p><label className="check"><input type="checkbox" checked={sources.includes(item.id)} disabled={!!busy||!sources.includes(item.id)&&sources.length>=10} onChange={()=>{invalidate();setSources(previous=>previous.includes(item.id)?previous.filter(id=>id!==item.id):previous.length<10?[...previous,item.id]:previous);}}/>Include this snapshot in an explicit combination</label></article>))}
    {!!collections.length&&<details open={subset?true:undefined}><summary>{subset?`Review ${subset.paperIds.length} selected citations`:`Combine selected snapshots (${sources.length}/10)`}</summary><p>{subset?`Only the ${subset.paperIds.length} explicitly selected paper IDs are considered. Their original citation origins remain retained.`:"All records in the chosen immutable snapshots will be considered."} Inspect duplicate and conflict groups before committing; records are never silently merged.</p><label>{subset?"Subset name":"Combined collection name"}<input value={name} maxLength={200} disabled={!!busy} onChange={event=>{invalidate();setName(event.target.value);}}/></label><label>Combination duplicate policy<select value={policy} disabled={!!busy} onChange={event=>{invalidate();setPolicy(event.target.value as typeof policy);}}><option value="review_required">Review required</option><option value="keep_separate">Keep separate</option><option value="merge_exact">Merge exact duplicates with all origins</option></select></label><button type="button" disabled={!!busy||!sources.length||!!subset&&!subset.paperIds.length||!name.trim()} onClick={()=>combine(true)}>{busy==="preview"?"Loading membership preview…":subset?"Preview selected subset":"Preview combination"}</button>
      {preview&&<><p>{preview.member_count} record occurrences before duplicate decisions.</p>{preview.duplicate_groups.length===0?<p>No duplicate groups detected.</p>:preview.duplicate_groups.map(group=><div key={group.id}><p>{group.message}</p><ul>{group.row_ids.map(id=>{const member=preview.members.find(item=>item.id===id);return <li key={id}>{member?.title||id}{member?.pmid?` · PMID ${member.pmid}`:""}{member?.doi?` · DOI ${member.doi}`:""}<span className="meta"> · {member?.collection_id??""}</span></li>;})}</ul>{group.kind!=="exact_identifier_duplicate"&&<label className="check"><input type="checkbox" checked={conflicts[group.id]==="keep_separate"} disabled={!!busy} onChange={event=>setConflicts(previous=>{const next={...previous};if(event.target.checked)next[group.id]="keep_separate";else delete next[group.id];return next;})}/>Keep these conflicting or possibly duplicate records separate</label>}</div>)}<p className="hash">REVIEWED COMBINATION {preview.input_sha256}</p><button type="button" className="primary" disabled={!!busy||blocked} onClick={()=>combine(false)}>{busy==="combine"?"Committing collection…":subset?"Commit reviewed subset":"Commit reviewed combination"}</button></>}
    </details>}
  </section>;
}

type ExplorerProps={workspace:Schema<"WorkspaceSummary">;collectionId:string;capabilities:Schema<"Capabilities">;requestedMap?:string;refresh:()=>Promise<void>;navigate:Navigate};
export default function CollectionExplorer({workspace,collectionId,capabilities,requestedMap,refresh,navigate}:ExplorerProps){
  const workspaceId=workspace.id;
  const [summary,setSummary]=useState<Summary|null>(null),[error,setError]=useState("");
  useEffect(()=>{let disposed=false;setSummary(null);setError("");api<Summary>(workspacePath(workspaceId)+"/collections/"+encodeURIComponent(collectionId)).then(value=>{if(!disposed){if(value.id!==collectionId)throw new Error("The requested immutable collection did not match the response.");setSummary(value);}}).catch(error=>{if(!disposed)setError(error.message);});return()=>{disposed=true;};},[workspaceId,collectionId]);
  return <><Failure message={error}/>{summary?<RetainedCollection key={summary.id} workspace={workspace} summary={summary} capabilities={capabilities} requestedMap={requestedMap} refresh={refresh} navigate={navigate}/>:<p role="status">Loading the authorized paper collection…</p>}</>;
}

function RetainedCollection({workspace,summary,capabilities,requestedMap,refresh,navigate}:Omit<ExplorerProps,"collectionId">&{summary:Summary}){
  const workspaceId=workspace.id,endpoint=workspacePath(workspaceId)+"/collections/"+encodeURIComponent(summary.id);
  const preparedHere=workspace.preparations.find(item=>item.id===workspace.current_preparation_id&&matchesPaperOrigin(summary.origin,item));
  const selection=useDraft(workspaceId,"collection-selection:"+summary.id,{selected_paper_ids:preparedHere?.selected_paper_ids??[] as string[]});
  const selected=selection.data.selected_paper_ids,maxSources=preparedSourceLimit(capabilities.limits),maxMapPapers=capabilities.limits.max_map_papers??0;
  const [filter,setFilter]=useState(""),[appliedFilter,setAppliedFilter]=useState(""),[filterNotice,setFilterNotice]=useState(""),[offset,setOffset]=useState(0),[page,setPage]=useState<Schema<"CollectionPaperPage">|null>(null),[error,setError]=useState("");
  const [paper,setPaper]=useState<Schema<"Paper">|null>(null),[detail,setDetail]=useState<Schema<"CollectionPaperDetail">|null>(null),[mapPapers,setMapPapers]=useState<Schema<"Paper">[]>([]),[hovered,setHovered]=useState<string|null>(null);
  const [reveal,setReveal]=useState<{id:string;sequence:number}>(),[showSubset,setShowSubset]=useState(false),[preparation,setPreparation]=useState<Schema<"CollectionPreparationView">|null>(null);
  const preparationRead=useRef(0),knownPapers=useRef(new Map<string,Schema<"Paper">>()),inspector=useRef<HTMLElement>(null),navigation=useRef<HTMLDivElement>(null),anchor=useRef<{top:number}|null>(null);
  const visible=page?.papers??[],index=visible.findIndex(item=>item.id===paper?.id);
  const canMap=summary.origin.kind==="collection"&&maxMapPapers>0&&summary.member_count<=maxMapPapers;
  useEffect(()=>{
    let disposed=false;setPage(null);setError("");
    api<Schema<"CollectionPaperPage">>(endpoint+`/papers?offset=${offset}&limit=${size}&filter=`+encodeURIComponent(appliedFilter)).then(value=>{
      if(disposed)return;
      if(value.collection_id!==summary.id||JSON.stringify(value.origin)!==JSON.stringify(summary.origin))throw new Error("The paper page belongs to a different collection snapshot.");
      for(const item of value.papers)knownPapers.current.set(item.id,item);
      if(offset===0&&!appliedFilter&&value.total===value.papers.length)setMapPapers(value.papers);
      setPage(value);
    }).catch(error=>{if(!disposed)setError(error.message);});
    return()=>{disposed=true;};
  },[endpoint,summary.id,summary.origin,offset,appliedFilter]);
  useEffect(()=>{
    let disposed=false;setDetail(null);
    if(paper)api<Schema<"CollectionPaperDetail">>(endpoint+"/paper?paper_id="+encodeURIComponent(paper.id)).then(value=>{
      if(disposed)return;
      if(value.collection_id!==summary.id||value.member.paper.id!==paper.id||JSON.stringify(value.origin)!==JSON.stringify(summary.origin))throw new Error("The inspected citation belongs to a different paper or collection snapshot.");
      setDetail(value);
    }).catch(error=>{if(!disposed)setError(error.message);});
    return()=>{disposed=true;};
  },[endpoint,summary.id,summary.origin,paper?.id]);
  useEffect(()=>{
    const token=++preparationRead.current;setPreparation(previous=>previous?.id===preparedHere?.id?previous:null);
    if(preparedHere)api<Schema<"CollectionPreparationView">>(workspacePath(workspaceId)+"/source-preparations/"+encodeURIComponent(preparedHere.id)).then(value=>{
      if(token!==preparationRead.current)return;
      if(value.id!==preparedHere.id||!matchesPaperOrigin(summary.origin,value))throw new Error("Prepared sources belong to a different collection snapshot.");
      setPreparation(value);
    }).catch(error=>{if(token===preparationRead.current)setError(error.message);});
    return()=>{preparationRead.current++;};
  },[workspaceId,preparedHere?.id,summary.origin]);
  function toggle(id:string){selection.setData(previous=>{const updated=toggleSelectedPaper(previous.selected_paper_ids,id,maxSources);return updated===previous.selected_paper_ids?previous:{...previous,selected_paper_ids:updated};});}
  function adjacent(direction:-1|1){
    if(index<0||direction===-1&&index===0||direction===1&&index>=visible.length-1)return;
    if(navigation.current&&!anchor.current)anchor.current={top:navigation.current.getBoundingClientRect().top};
    const ids=visible.map(item=>item.id);setPaper(current=>{const id=adjacentVisiblePaper(current?.id??null,ids,direction);return visible.find(item=>item.id===id)??current;});
  }
  useLayoutEffect(()=>{const captured=anchor.current;anchor.current=null;if(captured&&navigation.current){const delta=navigation.current.getBoundingClientRect().top-captured.top;if(delta)window.scrollBy({top:delta,left:0,behavior:"instant"});}},[paper?.id]);
  function revealPaper(id:string){
    const item=knownPapers.current.get(id);if(!item)return;
    if(!visible.some(value=>value.id===id)){
      setFilter("");setAppliedFilter("");setOffset(0);setFilterNotice("Collection filter cleared to show the requested paper.");
      if(mapPapers.length)setPage({collection_id:summary.id,origin:summary.origin,papers:mapPapers,offset:0,total:mapPapers.length,next_offset:null});
    }
    setPaper(item);setReveal(previous=>({id,sequence:(previous?.sequence??0)+1}));
  }
  function inspectPaper(value:Schema<"Paper">){setPaper(value);setTimeout(()=>inspector.current?.scrollIntoView({behavior:"instant",block:"start"}),0);}
  function published(value:Schema<"CollectionPreparationView">){if(!matchesPaperOrigin(summary.origin,value))return;preparationRead.current++;setPreparation(value);}
  const changed=JSON.stringify([...selected].sort())!==JSON.stringify([...(preparation?.selected_paper_ids??[])].sort());
  const inspectorView=paper&&<aside ref={inspector} className="paper-inspector" aria-label="Collection paper inspector"><ExplorationHeading title="Paper inspector" level={3} selectedIds={selected} maxSources={maxSources} visibleIds={new Set(visible.map(item=>item.id))}/><Citation paper={paper}/><p className="preserve">{paper.abstract||"No abstract supplied; citation metadata only."}</p>
    <label className="check"><input type="checkbox" checked={selected.includes(paper.id)} disabled={!selection.ready||!selected.includes(paper.id)&&selected.length>=maxSources} onChange={()=>toggle(paper.id)}/>Select this paper for exploration</label>
    <div ref={navigation} className="paper-inspector-navigation" aria-label="Paper inspector navigation"><button type="button" aria-label="Previous paper" disabled={index<=0} onClick={()=>adjacent(-1)}>← Previous</button><span className="meta">{index<0?"Outside the displayed page":`${index+1} of ${visible.length} on this page`}</span><button type="button" aria-label="Next paper" disabled={index<0||index>=visible.length-1} onClick={()=>adjacent(1)}>Next →</button></div>
    <p role="status" className="visually-hidden">{paper.title}. {index<0?"Outside the displayed page.":`Paper ${index+1} of ${visible.length} on this page.`}</p>{index<0&&<p className="muted">This inspected paper is outside the displayed page or applied filter. Inspect a visible paper to continue navigation. Your selections are unchanged.</p>}
    {detail?<details><summary>Metadata version and original citation provenance</summary><p className="hash">METADATA VERSION {detail.member.metadata_version.id}</p><p className="meta">ABSTRACT ORIGIN {detail.member.metadata_version.abstract_provider}</p><pre>{JSON.stringify({field_origins:detail.member.metadata_version.field_origins,resolution_receipts:detail.member.metadata_version.resolution_receipts,origins:detail.member.origins},null,2)}</pre></details>:<p role="status">Loading citation provenance…</p>}
  </aside>;
  const papersView=<section><ExplorationHeading title="Papers & source selection" selectedIds={selected} maxSources={maxSources} visibleIds={new Set(visible.map(item=>item.id))} sticky/><DraftStatus draft={selection}/>{!page?<p role="status">Loading citation records…</p>:!visible.length?<p>No citation records match the applied filter.</p>:<><p className="meta">RECORDS {offset+1}–{Math.min(offset+visible.length,page.total)} OF {page.total} MATCHING</p>{visible.map(item=><article key={item.id} data-paper-id={item.id} tabIndex={-1} className={["paper",paper?.id===item.id?"selected":"",hovered===item.id?"hovered":""].join(" ")} onMouseEnter={()=>setHovered(item.id)} onMouseLeave={()=>setHovered(null)} onFocus={()=>setHovered(item.id)} onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node|null))setHovered(null);}}><label className="check"><input type="checkbox" checked={selected.includes(item.id)} disabled={!selection.ready||!selected.includes(item.id)&&selected.length>=maxSources} onChange={()=>toggle(item.id)}/>Select for exploration</label><Citation paper={item}/><button type="button" aria-pressed={paper?.id===item.id} onClick={()=>inspectPaper(item)}>Inspect paper</button></article>)}<div className="actions"><button type="button" disabled={offset===0} onClick={()=>setOffset(previous=>Math.max(0,previous-size))}>Previous collection page</button><button type="button" disabled={page.next_offset===null} onClick={()=>setOffset(page.next_offset!)}>Next collection page</button></div></>}</section>;
  const mapView=canMap&&mapPapers.length===summary.member_count&&summary.origin.kind==="collection"?<CollectionMapExplorer workspaceId={workspaceId} collectionRef={summary.origin} papers={mapPapers} capability={capabilities.map} requestedMap={requestedMap} visibleIds={new Set(visible.map(item=>item.id))} selectedIds={new Set(selected)} selectionLimit={maxSources} inspectedId={paper?.id??null} hoveredId={hovered} onInspect={revealPaper} onHover={setHovered} onChooseMap={id=>void navigate({page:"discover",workspace:workspaceId,collection:summary.id,map:id})}/>:<section className="map-section"><ExplorationHeading title="Semantic map" selectedIds={selected} maxSources={maxSources} visibleIds={new Set(visible.map(item=>item.id))} sticky/>{canMap?<p role="status">Loading retained map input metadata…</p>:<Notice>This collection contains {summary.member_count} records. Map input is limited to {maxMapPapers} retained papers; save an explicit selected subset to map a smaller set. No records are silently truncated.</Notice>}</section>;
  return <><section><h2>{summary.name}</h2><p className="counts">{summary.member_count} retained citation records · {page?.total??"…"} matching the applied filter · {selected.length} selected · {preparation?.selected_paper_ids.length??0} prepared</p><p className="meta">{summary.kind.replaceAll("_"," ")} · {summary.coverage.replaceAll("_"," ")} · <Time value={summary.created_at}/></p><Notice>Imported and combined collections are citation sets, not a complete database search or formal review inclusion.</Notice><details><summary>Exact collection provenance</summary><dl><dt>Snapshot</dt><dd>{summary.id}</dd><dt>Revision</dt><dd>{summary.revision} · {summary.revision_id}</dd><dt>Input binding</dt><dd><pre>{JSON.stringify(summary.origin,null,2)}</pre></dd><dt>Parent snapshots</dt><dd><pre>{JSON.stringify(summary.parents,null,2)}</pre></dd><dt>Recorded search</dt><dd>{summary.search_metadata.original_query||"Not recorded for this citation collection"}</dd><dt>Search date</dt><dd>{summary.search_metadata.searched_at?<Time value={summary.search_metadata.searched_at}/>:"Unknown"}</dd><dt>Reported search count</dt><dd>{summary.search_metadata.total_reported??"Unknown"}</dd></dl></details></section>
    <section><h2>Explore retained citations</h2><Failure message={error}/><p className="muted">Select up to {maxSources} citations for exploration. Filtering and selection preserve saved map coordinates and source bindings.</p><form onSubmit={event=>{event.preventDefault();setOffset(0);setAppliedFilter(filter);setFilterNotice("");}}><label>Filter collection papers<input type="search" maxLength={200} value={filter} onChange={event=>setFilter(event.target.value)} placeholder="Title or author"/></label><div className="actions"><button type="submit">Apply collection filter</button><button type="button" disabled={!appliedFilter&&!filter} onClick={()=>{setFilter("");setAppliedFilter("");setOffset(0);setFilterNotice("");}}>Clear collection filter</button></div></form>{filterNotice&&<p role="status" className="muted">{filterNotice}</p>}</section>
    <ExplorationPanels map={mapView} papers={papersView} inspector={inspectorView} revealPaper={reveal}/>
    <section><h2>Prepare selected sources</h2><p>Select up to {maxSources} retained papers. A comparison board still uses at most 10 prepared reports and {capabilities.boards.max_cells} cells.</p>{changed&&preparation&&<Notice>Selection changed; the retained current passages still use the previous preparation.</Notice>}
      {summary.origin.kind==="collection"&&capabilities.preparation_jobs_ready?<CollectionPreparationJobs workspace={workspace} collectionRef={summary.origin} papers={Array.from(knownPapers.current.values())} selectedPaperIds={selected} selectionReady={selection.ready} maxSources={maxSources} flushSelection={selection.save} refresh={refresh} onPublished={published} navigate={navigate} question={workspace.question}/>:<Notice>Source preparation jobs are unavailable for this collection.</Notice>}
      {preparation&&<><p className="meta">PREPARATION {preparation.id} · SOURCE REVISION {preparation.source_revision}</p>{preparation.sources.map(source=><article key={source.id}><h3>{knownPapers.current.get(source.paper_id)?.title??source.paper_id}</h3><SourceMetadata source={source}/></article>)}<div className="actions"><button type="button" onClick={()=>navigate({page:"evidence",workspace:workspaceId})}>Optional passage search</button></div></>}
    </section>
    <section><h2>Save an explicit subset</h2><p className="muted">Keep the selected membership as another immutable collection before preparing or mapping that smaller set. The original collection remains retained.</p><button type="button" disabled={!selection.ready||selected.length===0} onClick={async()=>{try{if(showSubset)await flushDrafts();else await selection.save();setShowSubset(previous=>!previous);}catch(error){setError((error as Error).message);}}}>{showSubset?"Close subset review":"Review selected subset"}</button>{showSubset&&<CollectionPicker workspaceId={workspaceId} subset={{collection:summary,paperIds:selected}} onChoose={async value=>{await refresh();await navigate({page:"discover",workspace:workspaceId,collection:value.id});}}/>}</section>
  </>;
}
