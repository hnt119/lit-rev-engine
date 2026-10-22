"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,initializeSession,requestId,acknowledgeRequest,workspacePath,type Schema} from "../lib/api";
import {flushDrafts} from "../lib/drafts";
import {Failure,Notice,Time} from "./ui";
import Discover from "./discover";
import Evidence from "./evidence";
import History from "./history";
import Compare from "./compare";

export type Destination="workspaces"|"discover"|"compare"|"evidence"|"history";
export type LocationState={page:Destination;workspace?:string;search?:string;collection?:string;plan?:string;planRevision?:string;run?:string;map?:string;board?:string;revision?:string;paper?:string;field?:string};
export type Navigate=(next:LocationState)=>Promise<void>;
function locationState():LocationState {
  const p=new URLSearchParams(window.location.search),value=p.get("page");
  return {page:["workspaces","discover","compare","evidence","history"].includes(value??"")?value as Destination:"workspaces",workspace:p.get("workspace")??undefined,search:p.get("search")??undefined,collection:p.get("collection")??undefined,plan:p.get("plan")??undefined,planRevision:p.get("planRevision")??undefined,run:p.get("run")??undefined,map:p.get("map")??undefined,board:p.get("board")??undefined,revision:p.get("revision")??undefined,paper:p.get("paper")??undefined,field:p.get("field")??undefined};
}
function locationURL(next:LocationState) {
  const p=new URLSearchParams({page:next.page});
  for(const key of ["workspace","search","collection","plan","planRevision","run","map","board","revision","paper","field"] as const)if(next[key])p.set(key,next[key]!);
  return "/?"+p;
}
export default function WorkspaceApp() {
  const [location,setLocation]=useState<LocationState>({page:"workspaces"});
  const currentLocation=useRef(location);currentLocation.current=location;
  const [capabilities,setCapabilities]=useState<Schema<"Capabilities">|null>(null);
  const [workspaces,setWorkspaces]=useState<Schema<"WorkspaceSummary">[]>([]);
  const [workspace,setWorkspace]=useState<Schema<"WorkspaceSummary">|null>(null);
  const [error,setError]=useState("");const [ready,setReady]=useState(false);const [busy,setBusy]=useState(false);
  const [newQuestion,setNewQuestion]=useState("");const [newMode,setNewMode]=useState<"saved_example"|"live">("saved_example");
  const [boardOrigin,setBoardOrigin]=useState<{scope:string;collection:boolean}|null>(null);
  const boardScope=JSON.stringify([location.workspace,location.board,location.revision]);
  const reportBoardOrigin=useCallback((collection:boolean)=>setBoardOrigin(previous=>previous?.scope===boardScope&&previous.collection===collection?previous:{scope:boardScope,collection}),[boardScope]);
  const navigate:Navigate=useCallback(async next=>{
    try {await flushDrafts();}catch(error){setError((error as Error).message);return;}
    setError("");
    window.history.pushState(null,"",locationURL(next));setLocation(next);if(!next.map)window.scrollTo({top:0,behavior:"instant"});
  },[]);
  const refresh=useCallback(async()=>{
    const list=await api<Schema<"WorkspaceList">>("workspaces");setWorkspaces(list.workspaces);
    if(location.workspace)setWorkspace(await api<Schema<"WorkspaceSummary">>(workspacePath(location.workspace)));
  },[location.workspace]);
  useEffect(()=>{
    initializeSession().then(async()=>{
      setCapabilities(await api<Schema<"Capabilities">>("capabilities"));setLocation(locationState());setReady(true);
    }).catch(error=>setError(error.message));
    const back=()=>{
      const next=locationState();
      void flushDrafts().then(()=>{setError("");setLocation(next);window.scrollTo(0,0);}).catch(error=>{
        setError(error.message);window.history.pushState(null,"",locationURL(currentLocation.current));
      });
    };window.addEventListener("popstate",back);
    return()=>window.removeEventListener("popstate",back);
  },[]);
  useEffect(()=>{if(ready)refresh().catch(error=>{setError(error.message);setWorkspace(null);});},[ready,refresh]);
  async function create() {
    setBusy(true);setError("");try {
      const payload={question:newQuestion,mode:newMode};
      const created=await api<Schema<"WorkspaceSummary">>("workspaces","POST",{...payload,request_id:await requestId("create",payload)});
      acknowledgeRequest("create");
      setWorkspace(created);setNewQuestion("");await navigate({page:"discover",workspace:created.id});
    }catch(error){setError((error as Error).message);}finally{setBusy(false);}
  }
  const active=workspace?.id===location.workspace?workspace:null;
  const currentPreparation=active?.preparations.find(item=>item.id===active.current_preparation_id);
  const selectedRun=active?.runs.find(item=>item.id===(location.run??active.current_run_id));
  const collectionPreparation=!!currentPreparation&&"collection_ref" in currentPreparation;
  let origin:"legacy"|"collection"|"mixed"|"loading"=location.collection?"collection":"legacy";
  if(location.page==="evidence")origin=selectedRun?("collection_ref" in selectedRun?"collection":"legacy"):location.run?"loading":collectionPreparation?"collection":"legacy";
  if(location.page==="compare")origin=location.board?(boardOrigin?.scope===boardScope?(boardOrigin.collection?"collection":"legacy"):"loading"):collectionPreparation?"collection":"legacy";
  if(location.page==="history"&&(active?.preparations.some(item=>"collection_ref" in item)||active?.runs.some(item=>"collection_ref" in item)))origin="mixed";
  return <><a className="skip-link" href="#main">Skip to workspace</a>
    <header className="site-header"><a className="wordmark" href="/?page=workspaces" onClick={event=>{event.preventDefault();void navigate({page:"workspaces"});}}>LITERATURE REVIEW ENGINE</a><span className="meta">LOCAL WORKSPACE · v0.2</span></header>
    <div className={location.page==="workspaces"?"app-shell landing":"app-shell"}>
      <nav aria-label="Research workflow"><button aria-current={location.page==="workspaces"?"page":undefined} onClick={()=>void navigate({page:"workspaces"})}>Workspaces</button>
        {([["discover","Discover & explore"],["compare","Compare"],["evidence","Evidence"],["history","History & export"]] as const).map(([page,label])=><button key={page} disabled={!location.workspace} aria-current={location.page===page?"page":undefined} onClick={()=>void navigate({page,workspace:location.workspace})}>{label}</button>)}</nav>
      <main id="main"><Failure message={error}/>{!ready?<><h1>Follow the evidence.</h1><p>Connecting to the local Python service…</p>{error&&<button onClick={()=>window.location.reload()}>Retry connection</button>}</>:location.page==="workspaces"?<>
        <p className="eyebrow">EVIDENCE YOU CAN INSPECT</p><h1>Follow the evidence.</h1><p className="intro">Ask a research question, explore a bounded search preview, and inspect the source behind every passage.</p>
        <section><h2>Create a workspace</h2><form onSubmit={event=>{event.preventDefault();void create();}}>
          <label>Research question<textarea value={newQuestion} onChange={event=>setNewQuestion(event.target.value)} rows={3} maxLength={10000} placeholder="How does diet relate to the gut microbiome in Asian women?"/></label>
          <label>Discovery mode<select value={newMode} onChange={event=>setNewMode(event.target.value as "live"|"saved_example")}><option value="saved_example">Saved example · offline</option><option value="live" disabled={!capabilities?.live_available}>Live PubMed{!capabilities?.live_available?" · contact configuration required":""}</option></select></label>
          <button className="primary" disabled={busy}>{busy?"Creating…":"Create workspace"}</button></form></section>
        <section><h2>Reopen your work</h2><p className="muted">Available to this browser profile while its persistent local session remains valid. Clearing cookies loses this access; this is not a named researcher account.</p>
          {!workspaces.length?<p>No workspaces in this browser session yet.</p>:workspaces.map(item=><article className="workspace-entry" key={item.id}><h3><button className="text-button" onClick={()=>void navigate({page:"discover",workspace:item.id})}>{item.question||"Untitled research workspace"}</button></h3><p className="meta">{item.mode.replaceAll("_"," ")} · <Time value={item.created_at}/> · {item.searches.length} saved searches · {item.runs.length} evidence runs</p></article>)}</section>
      </>:!active?<p role="status">Loading the authorized workspace…</p>:<><div className="workspace-heading"><p className="eyebrow">{origin==="collection"?"SAVED PAPER COLLECTION":origin==="mixed"?"RETAINED RESEARCH HISTORY":origin==="loading"?"RETAINED RESEARCH WORKSPACE":active.mode==="saved_example"?"SAVED EXAMPLE · OFFLINE":"EXPLORATORY PUBMED PREVIEW"}</p><p className="workspace-question">{active.question||"Untitled research workspace"}</p><span className="meta">WORKSPACE {active.id}</span></div>
        {active.mode==="saved_example"&&origin==="legacy"&&<Notice>This is a curated saved example, not a live search, complete capture, or scientific conclusion.</Notice>}
        {location.page==="discover"&&<Discover key={active.id} workspace={active} capabilities={capabilities!} requestedSearch={location.search} requestedMap={location.map} requestedCollection={location.collection} requestedPlan={location.plan} requestedPlanRevision={location.planRevision} refresh={refresh} navigate={navigate}/>}
        {location.page==="compare"&&<Compare key={active.id} workspace={active} requestedBoard={location.board} requestedRevision={location.revision} requestedPaper={location.paper} requestedField={location.field} navigate={navigate} onOriginChange={reportBoardOrigin} retrievalCapability={capabilities!.board_span_profiles??undefined}/>}
        {location.page==="evidence"&&<Evidence key={active.id+":"+(location.run??"current")} workspace={active} requestedRun={location.run} refresh={refresh} navigate={navigate}/>}
        {location.page==="history"&&<History workspace={active} refresh={refresh} navigate={navigate}/>}
      </>}</main></div><footer>Exploratory evidence workspace · Human judgments are self-declared and are not independent verification.</footer></>;
}
