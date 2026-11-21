"use client";
import {useEffect,useState} from "react";
import {api,workspacePath,type Schema} from "../lib/api";
import {Failure,Notice,Time} from "./ui";
import type {Navigate} from "./workspace-app";

function SavedComparisons({workspaceId,navigate}:{workspaceId:string;navigate:Navigate}) {
  const [listing,setListing]=useState<Schema<"BoardListing">|null>(null),[error,setError]=useState("");
  const [attempt,setAttempt]=useState(0),[includeHistory,setIncludeHistory]=useState(false);
  useEffect(()=>{
    let disposed=false;setListing(null);setError("");
    api<Schema<"BoardListing">>(workspacePath(workspaceId)+"/boards").then(value=>{if(!disposed)setListing(value);}).catch(error=>{if(!disposed)setError(error.message);});
    return()=>{disposed=true;};
  },[workspaceId,attempt]);
  return <section aria-labelledby="history-comparisons"><h2 id="history-comparisons" data-workspace-section="Saved comparisons" tabIndex={-1}>Saved comparisons</h2>
    <p>Reopen a comparison or export its saved entries, source references and judgment states. Drafts are separate and are not included in these exports.</p>
    <Failure message={error}/>{error?<button type="button" onClick={()=>setAttempt(value=>value+1)}>Retry loading comparisons</button>:!listing?<p role="status">Loading saved comparisons…</p>:!listing.boards.length?<><p>No saved comparison boards yet.</p><button type="button" onClick={()=>void navigate({page:"compare",workspace:workspaceId})}>Open comparison workspace</button></>:<>
      <label className="check"><input type="checkbox" checked={includeHistory} onChange={event=>setIncludeHistory(event.target.checked)}/>Include all saved board definitions in audit JSON</label>
      <p className="muted">Each download uses the definition listed below. Audit JSON includes its immutable cell history and candidate retrieval audit. To inspect another definition or check source freshness, open the comparison.</p>
      {listing.boards.map(board=>{
        const endpoint=workspacePath(workspaceId)+"/boards/"+encodeURIComponent(board.board_id),query=`history=${includeHistory}&revision_id=${encodeURIComponent(board.revision_id)}`;
        return <article className="history-item" key={board.board_id}><h3>{board.question}</h3><p className="meta">{board.paper_count} reports × {board.field_count} fields · <Time value={board.created_at}/></p>
          <div className="actions"><button type="button" onClick={()=>void navigate({page:"compare",workspace:workspaceId,board:board.board_id,revision:board.revision_id})}>Open comparison board</button><a className="button" download href={`/api/v1/${endpoint}/exports?format=csv&${query}`}>Download board CSV</a><a className="button" download href={`/api/v1/${endpoint}/exports?format=json&${query}`}>Download board audit JSON</a></div>
        </article>;
      })}
    </>}
  </section>;
}

export default function History({workspace,refresh,navigate}:{workspace:Schema<"WorkspaceSummary">;refresh:()=>Promise<void>;navigate:Navigate}) {
  const [confirm,setConfirm]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const [mapSearch,setMapSearch]=useState(workspace.searches.at(-1)?.id??"");
  const [mapListing,setMapListing]=useState<Schema<"MapListing">|null>(null);const [mapError,setMapError]=useState("");
  useEffect(()=>{
    setMapListing(null);setMapError("");if(!mapSearch)return;
    let disposed=false;api<Schema<"MapListing">>(workspacePath(workspace.id)+"/maps?search_id="+encodeURIComponent(mapSearch)).then(value=>{if(!disposed)setMapListing(value);}).catch(error=>{if(!disposed)setMapError(error.message);});
    return()=>{disposed=true;};
  },[workspace.id,mapSearch]);
  async function remove(){setBusy(true);try{await api(workspacePath(workspace.id),"DELETE");await navigate({page:"workspaces"});await refresh();}catch(error){setError((error as Error).message);}finally{setBusy(false);}}
  return <><h1>History & export</h1><SavedComparisons key={workspace.id} workspaceId={workspace.id} navigate={navigate}/><section><h2 id="history-export" data-workspace-section="Export passage evidence" tabIndex={-1}>Export passage evidence</h2><p>Passage CSV and versioned JSON audits include exact quotations and source versions. The JSON audit also retains passage assessment history and available collection and search-plan provenance. Comparison entries use the separate board exports above.</p><div className="actions"><a className="button primary" href={`/api/v1/${workspacePath(workspace.id)}/exports?format=csv`} download>Download passage CSV</a><a className="button" href={`/api/v1/${workspacePath(workspace.id)}/exports?format=json`} download>Download passage audit JSON</a></div><Notice>These are exploratory records. They do not create formal inclusion, study linkage, independent verification or a complete systematic-review capture.</Notice></section>
    <section><h2 id="history-runs" data-workspace-section="Evidence runs" tabIndex={-1}>Evidence runs</h2>{!workspace.runs.length?<p>No evidence runs yet.</p>:[...workspace.runs].reverse().map(run=><article className="history-item" key={run.id}><p className="eyebrow">{run.id===workspace.current_run_id?"CURRENT":"HISTORICAL · READ ONLY"}</p><h3>{run.question}</h3><p className="meta">{run.passage_count} passages · source revision {run.source_revision} · <Time value={run.created_at}/></p><button onClick={()=>void navigate({page:"evidence",workspace:workspace.id,run:run.id})}>{run.id===workspace.current_run_id?"Open current evidence":"Inspect original historical evidence"}</button></article>)}</section>
    <section><h2 id="history-searches" data-workspace-section="Saved searches" tabIndex={-1}>Saved searches</h2>{[...workspace.searches].reverse().map(search=><article className="history-item" key={search.id}><p className="preserve">{search.query}</p><p className="meta">{search.mode.replaceAll("_"," ")} · {search.total_reported} reported · {search.fetched_count} fetched · {search.distinct_count} distinct · <Time value={search.searched_at}/></p><button onClick={()=>void navigate({page:"discover",workspace:workspace.id,search:search.id})}>Open this saved preview</button></article>)}</section>
    <section><h2 id="history-maps" data-workspace-section="Saved semantic maps" tabIndex={-1}>Saved semantic maps</h2><p>Inspect the original persisted artifact for one saved search. Opening a map does not build or refit it.</p><Failure message={mapError}/>{!workspace.searches.length?<p>No saved searches to map.</p>:<><label>Map history for search<select value={mapSearch} onChange={event=>setMapSearch(event.target.value)}>{[...workspace.searches].reverse().map(search=><option key={search.id} value={search.id}>{search.query.slice(0,90)} · {new Date(search.searched_at).toLocaleString()}</option>)}</select></label>{!mapListing?<p>{mapError?"Map history is unavailable.":"Loading saved map metadata…"}</p>:<>{!mapListing.maps.length?<p>No saved map for this search.</p>:mapListing.maps.map(map=><article className="history-item" key={map.map_id}><p>{map.projection_method.replaceAll("_"," ")} · {map.embedded_count} embedded · {map.excluded_count} excluded</p><p className="meta"><Time value={map.created_at}/> · MAP {map.map_id}</p><button onClick={()=>void navigate({page:"discover",workspace:workspace.id,search:map.search_id,map:map.map_id})}>Inspect this saved map</button></article>)}{mapListing.jobs.some(job=>["queued","running","cancel_requested"].includes(job.status))&&<button onClick={()=>void navigate({page:"discover",workspace:workspace.id,search:mapSearch})}>Open this search to follow its active map job</button>}</>}</>}</section>
    <section><h2 id="history-assessments" data-workspace-section="Passage assessments" tabIndex={-1}>Passage assessments</h2>{workspace.assessments.length?workspace.assessments.map(item=><p key={item.id}>{item.status} · <Time value={item.created_at}/> · <span className="meta">{item.id}{item.supersedes_id&&` · supersedes ${item.supersedes_id}`}</span></p>):<p>No submitted passage assessments. Comparison entries are retained in their boards; drafts are separate.</p>}</section>
    <section><h2 id="history-delete" data-workspace-section="Delete this local workspace" tabIndex={-1}>Delete this local workspace</h2><p>Deletes this workspace and its session access, drafts and auxiliary records. Export first. This is not secure disk erasure of backups or SQLite pages.</p><label className="check"><input type="checkbox" checked={confirm} onChange={event=>setConfirm(event.target.checked)}/>I understand and want to delete this workspace</label><Failure message={error}/><button disabled={!confirm||busy} onClick={()=>void remove()}>{busy?"Deleting…":"Delete workspace"}</button></section>
  </>;
}
