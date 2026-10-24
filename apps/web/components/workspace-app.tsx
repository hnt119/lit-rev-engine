"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,initializeSession,requestId,acknowledgeRequest,workspacePath,type Schema} from "../lib/api";
import {flushDrafts,recoverDrafts} from "../lib/drafts";
import {Failure,Notice,Time} from "./ui";
import Discover from "./discover";
import Evidence from "./evidence";
import History from "./history";
import Compare from "./compare";
import ReviewPilot from "./review-pilot";

export type Destination="workspaces"|"discover"|"compare"|"evidence"|"history"|"pilot";
export type LocationState={page:Destination;workspace?:string;search?:string;collection?:string;plan?:string;planRevision?:string;run?:string;map?:string;board?:string;revision?:string;paper?:string;field?:string;intake?:"search"|"import"|"collections";preparation?:string;handoff?:string;setup?:"new";focusResult?:string;passage?:string;returnTo?:"cell"|"comparison"};
export type NavigationOutcome={status:"success"}|{status:"blocked";message:string};
export type Navigate=(next:LocationState)=>Promise<NavigationOutcome|void>;
function locationState():LocationState {
  const p=new URLSearchParams(window.location.search),value=p.get("page");
  return {page:["workspaces","discover","compare","evidence","history","pilot"].includes(value??"")?value as Destination:"workspaces",workspace:p.get("workspace")??undefined,search:p.get("search")??undefined,collection:p.get("collection")??undefined,plan:p.get("plan")??undefined,planRevision:p.get("planRevision")??undefined,run:p.get("run")??undefined,map:p.get("map")??undefined,board:p.get("board")??undefined,revision:p.get("revision")??undefined,paper:p.get("paper")??undefined,field:p.get("field")??undefined,intake:["search","import","collections"].includes(p.get("intake")??"")?p.get("intake") as LocationState["intake"]:undefined,preparation:p.get("preparation")??undefined,handoff:p.get("handoff")??undefined,setup:p.get("setup")==="new"?"new":undefined,focusResult:p.get("focusResult")??undefined,passage:p.get("passage")??undefined,returnTo:["cell","comparison"].includes(p.get("returnTo")??"")?p.get("returnTo") as LocationState["returnTo"]:undefined};
}
function locationURL(next:LocationState) {
  const p=new URLSearchParams({page:next.page});
  for(const key of ["workspace","search","collection","plan","planRevision","run","map","board","revision","paper","field","intake","preparation","handoff","setup","focusResult","passage","returnTo"] as const)if(next[key])p.set(key,next[key]!);
  return "/?"+p;
}
export default function WorkspaceApp({hosted=false}:{hosted?:boolean}={}) {
  const [location,setLocation]=useState<LocationState>({page:"workspaces"});
  const currentLocation=useRef(location);currentLocation.current=location;
  const [capabilities,setCapabilities]=useState<Schema<"Capabilities">|null>(null);
  const [workspaces,setWorkspaces]=useState<Schema<"WorkspaceSummary">[]>([]);
  const [workspace,setWorkspace]=useState<Schema<"WorkspaceSummary">|null>(null);
  const [error,setError]=useState("");const [blocked,setBlocked]=useState<{next:LocationState;message:string}|null>(null);const [recovering,setRecovering]=useState(false);const [ready,setReady]=useState(false);const [busy,setBusy]=useState(false);
  const [newQuestion,setNewQuestion]=useState("");const [newMode,setNewMode]=useState<"saved_example"|"live">("saved_example");
  const [boardOrigin,setBoardOrigin]=useState<{scope:string;collection:boolean}|null>(null);
  const boardScope=JSON.stringify([location.workspace,location.board,location.revision]);
  const reportBoardOrigin=useCallback((collection:boolean)=>setBoardOrigin(previous=>previous?.scope===boardScope&&previous.collection===collection?previous:{scope:boardScope,collection}),[boardScope]);
  const navigationAttempt=useRef(0);
  const historyIndex=useRef(0),restoringHistory=useRef(false);
  const navigate:Navigate=useCallback(async next=>{
    const attempt=++navigationAttempt.current;
    try {await flushDrafts();}catch(error){const message=(error as Error).message;
      const localIntake=next.page==="discover"&&!!next.intake&&currentLocation.current.page==="discover"&&next.workspace===currentLocation.current.workspace;
      if(!localIntake)setBlocked({next,message});return {status:"blocked",message};}
    if(attempt!==navigationAttempt.current)return {status:"blocked",message:"A newer navigation request is already in progress."};
    setError("");setBlocked(null);
    window.history.replaceState({...window.history.state,index:historyIndex.current,scrollY:window.scrollY},"",window.location.href);
    historyIndex.current++;
    window.history.pushState({index:historyIndex.current,scrollY:0,comparisonPosition:window.history.state?.comparisonPosition},"",locationURL(next));
    const sameBoard=next.page==="compare"&&next.board&&currentLocation.current.page==="compare"&&next.board===currentLocation.current.board;
    if(!next.map&&!next.focusResult&&!sameBoard)window.scrollTo({top:0,behavior:"instant"});
    setLocation(next);return {status:"success"};
  },[]);
  async function recoverNavigation(mode:"retry"|"restore"){
    if(!blocked||recovering)return;
    if(mode==="restore"&&!window.confirm("Discard unsaved local edits and restore the latest saved drafts before leaving? Saved research records are retained."))return;
    setRecovering(true);try{await recoverDrafts(mode);await navigate(blocked.next);}catch(error){setBlocked(previous=>previous?{...previous,message:(error as Error).message}:previous);}finally{setRecovering(false);}
  }
  const refresh=useCallback(async()=>{
    const list=await api<Schema<"WorkspaceList">>("workspaces");setWorkspaces(list.workspaces);
    if(location.workspace)setWorkspace(await api<Schema<"WorkspaceSummary">>(workspacePath(location.workspace)));
  },[location.workspace]);
  useEffect(()=>{
    historyIndex.current=window.history.state?.index??0;
    window.history.replaceState({...window.history.state,index:historyIndex.current},"",window.location.href);
    initializeSession().then(async()=>{
      setCapabilities(await api<Schema<"Capabilities">>("capabilities"));setLocation(locationState());setReady(true);
    }).catch(error=>setError(error.message));
    const back=()=>{
      if(restoringHistory.current){restoringHistory.current=false;return;}
      const next=locationState();
      const scroll=window.history.state?.scrollY??0,index=window.history.state?.index??historyIndex.current;
      void flushDrafts().then(()=>{historyIndex.current=index;setError("");setBlocked(null);setLocation(next);if(!next.focusResult)window.scrollTo(0,scroll);}).catch(error=>{
        setBlocked({next,message:error.message});
        if(index!==historyIndex.current){restoringHistory.current=true;window.history.go(historyIndex.current-index);}
        else window.history.replaceState({...window.history.state,index:historyIndex.current},"",locationURL(currentLocation.current));
      });
    };window.addEventListener("popstate",back);
    return()=>window.removeEventListener("popstate",back);
  },[]);
  useEffect(()=>{if(ready)refresh().catch(error=>{setError(error.message);setWorkspace(null);});},[ready,refresh]);
  async function create(destination:Destination="discover") {
    setBusy(true);setError("");try {
      const payload={question:newQuestion,mode:destination==="pilot"?"saved_example":newMode};
      const created=await api<Schema<"WorkspaceSummary">>("workspaces","POST",{...payload,request_id:await requestId("create",payload)});
      acknowledgeRequest("create");
      setWorkspace(created);setNewQuestion("");await navigate({page:destination,workspace:created.id});
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
    <header className="site-header"><a className="wordmark" href="/?page=workspaces" onClick={event=>{event.preventDefault();void navigate({page:"workspaces"});}}>LITERATURE REVIEW ENGINE</a><span className="meta">{hosted?"HOSTED BETA":"LOCAL WORKSPACE"} · v0.3</span></header>
    <div className={location.page==="workspaces"?"app-shell landing":"app-shell"}>
      <nav aria-label="Research workflow"><button aria-current={location.page==="workspaces"?"page":undefined} onClick={()=>void navigate({page:"workspaces"})}>Workspaces</button>
        {([["discover","Discover & explore"],["compare","Comparison board"],["evidence","Passage search"],["history","History & export"]] as const).map(([page,label])=><button key={page} disabled={!location.workspace} aria-current={location.page===page?"page":undefined} onClick={()=>void navigate({page,workspace:location.workspace})}>{label}</button>)}{!hosted&&<button disabled={!location.workspace} aria-current={location.page==="pilot"?"page":undefined} onClick={()=>void navigate({page:"pilot",workspace:location.workspace})}>Review pilot</button>}</nav>
      <main id="main">{blocked&&<aside className="notice error" role="alert" aria-label="Navigation needs draft recovery"><p>Your draft could not be saved. You are still on the current page. {blocked.message}</p><div className="actions"><button disabled={recovering} onClick={()=>void recoverNavigation("retry")}>Retry and continue</button><button disabled={recovering} onClick={()=>setBlocked(null)}>Stay here</button><button disabled={recovering} onClick={()=>void recoverNavigation("restore")}>Restore saved drafts and continue…</button></div></aside>}<Failure message={error}/>{!ready?<><h1>Follow the evidence.</h1><p>Connecting to the local Python service…</p>{error&&<button onClick={()=>window.location.reload()}>Retry connection</button>}</>:location.page==="workspaces"?<>
        <p className="eyebrow">EVIDENCE YOU CAN INSPECT</p><h1>Follow the evidence.</h1><p className="intro">Ask a research question, explore a bounded search preview, and inspect the source behind every passage.</p>
        <section><h2>Create a workspace</h2><form onSubmit={event=>{event.preventDefault();void create();}}>
          <label>Research question<textarea value={newQuestion} onChange={event=>setNewQuestion(event.target.value)} rows={3} maxLength={10000} placeholder="How does diet relate to the gut microbiome in Asian women?"/></label>
          <label>Discovery mode<select value={newMode} onChange={event=>setNewMode(event.target.value as "live"|"saved_example")}><option value="saved_example">Saved example · offline</option><option value="live" disabled={!capabilities?.live_available}>Live PubMed{!capabilities?.live_available?" · contact configuration required":""}</option></select></label>
          <button className="primary" disabled={busy}>{busy?"Creating…":"Create workspace"}</button>{!hosted&&<button type="button" disabled={busy} onClick={()=>void create("pilot")}>Start an isolated review pilot</button>}</form></section>
        <section><h2>Reopen your work</h2><p className="muted">Available to this browser profile while its persistent local session remains valid. Clearing cookies loses this access; this is not a named researcher account.</p>
          {!workspaces.length?<p>No workspaces in this browser session yet.</p>:workspaces.map(item=><article className="workspace-entry" key={item.id}><h3><button className="text-button" onClick={()=>void navigate({page:"discover",workspace:item.id})}>{item.question||"Untitled research workspace"}</button></h3><p className="meta">{item.mode.replaceAll("_"," ")} · <Time value={item.created_at}/> · {item.searches.length} saved searches · {item.runs.length} evidence runs</p></article>)}</section>
      </>:!active?<p role="status">Loading the authorized workspace…</p>:<><div className="workspace-heading"><p className="eyebrow">{location.page==="pilot"?"ISOLATED PROTOCOL REVIEW PILOT":origin==="collection"?"SAVED PAPER COLLECTION":origin==="mixed"?"RETAINED RESEARCH HISTORY":origin==="loading"?"RETAINED RESEARCH WORKSPACE":active.mode==="saved_example"?"SAVED EXAMPLE · OFFLINE":"EXPLORATORY PUBMED PREVIEW"}</p><p className="workspace-question">{active.question||"Untitled research workspace"}</p><span className="meta">WORKSPACE {active.id}</span></div>
        {active.mode==="saved_example"&&origin==="legacy"&&location.page!=="pilot"&&<Notice>This is a curated saved example, not a live search, complete capture, or scientific conclusion.</Notice>}
        {location.page==="discover"&&<Discover key={active.id} workspace={active} capabilities={capabilities!} requestedSearch={location.search} requestedMap={location.map} requestedCollection={location.collection} requestedPlan={location.plan} requestedPlanRevision={location.planRevision} requestedIntake={location.intake} requestedFocusResult={location.focusResult} refresh={refresh} navigate={navigate}/>}
        {location.page==="compare"&&<Compare key={active.id} workspace={active} requestedBoard={location.board} requestedRevision={location.revision} requestedPaper={location.paper} requestedField={location.field} requestedRun={location.run} requestedPassage={location.passage} requestedReturn={location.returnTo} requestedPreparation={location.preparation} requestedHandoff={location.handoff} requestedSetup={location.setup} navigate={navigate} onOriginChange={reportBoardOrigin} retrievalCapability={capabilities!.board_span_profiles??undefined}/>}
        {location.page==="evidence"&&<Evidence key={[active.id,location.board,location.revision,location.paper,location.field].join(":")} workspace={active} requestedRun={location.run} comparison={location.board?{board_id:location.board,board_revision_id:location.revision??"",paper_id:location.paper,field_id:location.field}:undefined} maxPassages={capabilities!.limits.max_passages??5} refresh={refresh} navigate={navigate}/>}
        {location.page==="pilot"&&!hosted&&<ReviewPilot key={active.id} workspace={active} refresh={refresh} navigate={navigate}/>}
        {location.page==="history"&&<History workspace={active} refresh={refresh} navigate={navigate}/>}
      </>}</main></div><footer>Exploratory evidence workspace · Human judgments are self-declared and are not independent verification.</footer></>;
}
