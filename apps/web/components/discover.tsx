"use client";
import {useContext,useEffect,useLayoutEffect,useRef,useState} from "react";
import {api,requestId,workspacePath,type Schema} from "../lib/api";
import {DraftStatus,recoverDrafts,useDraft} from "../lib/drafts";
import {Citation,Failure,Notice,SourceMetadata,Time} from "./ui";
import MapExplorer from "./map-explorer";
import ExplorationPanels from "./exploration-panels";
import {adjacentVisiblePaper,preparedSourceLimit,toggleSelectedPaper} from "../lib/paper-selection";
import PreparationJobs from "./preparation-jobs";
import ImportPapers from "./import-papers";
import CollectionExplorer,{CollectionPicker} from "./collection-explorer";
import type {LocationState,Navigate} from "./workspace-app";
import ExplorationHeading from "./exploration-heading";
import {acknowledgeComparisonHandoff,assertHandoffPreparation,createComparisonHandoff,currentExactPreparation} from "../lib/comparison-handoff";
import SearchPlanner,{RawStrategyEditor} from "./search-planner";
import {SettingsLink,SearchDefaultsContext} from "../lib/settings-navigation";

type Props={workspace:Schema<"WorkspaceSummary">;capabilities:Schema<"Capabilities">;requestedSearch?:string;requestedMap?:string;requestedCollection?:string;requestedPlan?:string;requestedPlanRevision?:string;requestedIntake?:"search"|"import"|"collections";requestedFocusResult?:string;refresh:()=>Promise<void>;navigate:Navigate};
export default function Discover({workspace,capabilities,requestedSearch,requestedMap,requestedCollection,requestedPlan,requestedPlanRevision,requestedIntake,requestedFocusResult,refresh,navigate}:Props) {
  const offline=workspace.mode==="saved_example",structured=capabilities.search_plans_ready===true;
  const bundledQuery=String(capabilities.saved_example.query??"");
  const searchDefaults=useContext(SearchDefaultsContext);
  const bundleId=String(capabilities.saved_example.bundle_id??capabilities.saved_example.searched_at??"historical-example");
  const draft=useDraft(workspace.id,"discover",{question:workspace.question||String(capabilities.saved_example.question??""),query:offline?String(capabilities.saved_example.query??""):"",sort:offline?"relevance":searchDefaults.sort,max_results:offline?30:searchDefaults.max_results,use_dates:false,date_from:"",date_to:""});
  const latest=workspace.searches.at(-1);
  const searchId=requestedCollection?undefined:requestedSearch??latest?.id;
  const [pane,setPane]=useState<"search"|"import"|"collections">(requestedIntake??"search");
  useEffect(()=>setPane(requestedIntake??"search"),[requestedIntake]);
  const [intakeFailure,setIntakeFailure]=useState<{next:LocationState;message:string}|null>(null);
  const [switching,setSwitching]=useState(false);
  const [search,setSearch]=useState<Schema<"SearchPreview">|null>(null);
  const [busy,setBusy]=useState("");const [error,setError]=useState("");
  const [proposal,setProposal]=useState<{question:string;originalQuery:string;value:Schema<"QuerySuggestion">}|null>(null);
  const proposalGeneration=useRef(0);
  const currentProposal=proposal?.question===draft.data.question&&proposal.originalQuery===draft.data.query?proposal:null;
  const displayedQuery=offline?bundledQuery:draft.data.query;
  useEffect(()=>{let disposed=false;setSearch(current=>current?.id===searchId?current:null);if(searchId)api<Schema<"SearchPreview">>(workspacePath(workspace.id)+"/searches/"+encodeURIComponent(searchId)+"/papers").then(value=>{if(disposed)return;if(value.id!==searchId)throw new Error("The loaded search does not match the requested saved result.");setSearch(value);}).catch(error=>{if(!disposed)setError(error.message);});return()=>{disposed=true;};},[workspace.id,searchId]);
  function invalidateProposal(){proposalGeneration.current++;setProposal(null);}
  async function suggest(){setBusy("suggest");setError("");setProposal(null);const generation=++proposalGeneration.current,question=draft.data.question,originalQuery=draft.data.query;try{const value=await api<Schema<"QuerySuggestion">>(workspacePath(workspace.id)+"/query-suggestions","POST",{question});if(proposalGeneration.current===generation)setProposal({question,originalQuery,value});}catch(error){setError((error as Error).message);}finally{setBusy("");}}
  function applyProposal(){if(!currentProposal?.value.query.trim())return;draft.setData(previous=>previous.question===currentProposal.question&&previous.query===currentProposal.originalQuery?{...previous,query:currentProposal.value.query}:previous);invalidateProposal();}
  async function discover(fresh=false){setBusy("search");setError("");try{
    await draft.save();const payload={query:displayedQuery,research_question:draft.data.question||null,sort:offline?"relevance":draft.data.sort,max_results:offline?30:Number(draft.data.max_results),date_from:!offline&&draft.data.use_dates?draft.data.date_from:null,date_to:!offline&&draft.data.use_dates?draft.data.date_to:null};
    const fingerprint=offline?{...payload,saved_example_bundle:bundleId}:payload;
    const result=await api<Schema<"SearchPreview">>(workspacePath(workspace.id)+"/searches","POST",{...payload,request_id:await requestId(workspace.id+":search",fingerprint,fresh)});
    setSearch(result);await refresh();const outcome=await navigate({page:"discover",workspace:workspace.id,search:result.id,intake:"search",focusResult:result.id});if(outcome&&outcome.status==="blocked")setError(outcome.message);
  }catch(error){setError((error as Error).message);}finally{setBusy("");}}
  async function moveIntake(next:LocationState){setSwitching(true);setIntakeFailure(null);try{const result=await navigate(next);if(result&&result.status==="blocked"){setIntakeFailure({next,message:result.message});return;}setPane(next.intake??"search");}catch(error){setIntakeFailure({next,message:(error as Error).message});}finally{setSwitching(false);}}
  async function chooseCollection(value:Schema<"CollectionSummary">){await refresh();await moveIntake(value.origin.kind==="search"?{page:"discover",workspace:workspace.id,search:value.origin.search_id}:{page:"discover",workspace:workspace.id,collection:value.id});}
  async function openPane(value:typeof pane){await moveIntake({page:"discover",workspace:workspace.id,...(requestedCollection?{collection:requestedCollection}:searchId?{search:searchId}:{}),...(requestedMap?{map:requestedMap}:{}),...(requestedPlan?{plan:requestedPlan}:{}),...(requestedPlanRevision?{planRevision:requestedPlanRevision}:{}),intake:value});}
  async function recoverIntake(mode:"retry"|"restore"){if(!intakeFailure)return;if(mode==="restore"&&!window.confirm("Discard unsaved changes and restore the last saved drafts before switching?"))return;const next=intakeFailure.next;try{await recoverDrafts(mode);await moveIntake(next);}catch(error){setIntakeFailure({next,message:(error as Error).message});}}
  const planner=structured&&draft.ready&&<SearchPlanner key={workspace.id+":planner"} workspace={workspace} initialQuestion={draft.data.question} requestedPlan={requestedPlan} requestedRevision={requestedPlanRevision} onOpen={async(planId,revisionId)=>{const outcome=await navigate({page:"discover",workspace:workspace.id,...(searchId?{search:searchId}:{}),...(requestedMap?{map:requestedMap}:{}),...(planId?{plan:planId}:{}),...(revisionId?{planRevision:revisionId}:{})});if(outcome&&outcome.status==="blocked")setError(outcome.message);}} onExecuted={async result=>{setSearch(result);await refresh();const outcome=await navigate({page:"discover",workspace:workspace.id,search:result.id,intake:"search",focusResult:result.id,...(requestedPlan?{plan:requestedPlan}:{})});if(outcome&&outcome.status==="blocked")setError(outcome.message);}}/>;
  return <><h1>Discover & explore</h1><p>Add papers, select sources, then prepare them for a comparison board. Passage search is optional.</p>{!offline&&<SettingsLink section="sources">Configure PubMed connection</SettingsLink>}<Failure message={error}/>
    <div className="intake-switcher" aria-label="Add papers"><div className="actions"><button type="button" aria-pressed={pane==="search"} disabled={switching} onClick={()=>openPane("search")}>Search papers</button><button type="button" aria-pressed={pane==="import"} disabled={switching||!(capabilities.limits.max_import_bytes>0)} onClick={()=>openPane("import")}>Import papers</button><button type="button" aria-pressed={pane==="collections"} disabled={switching} onClick={()=>openPane("collections")}>Browse collections</button></div>{switching&&<p role="status">Saving drafts before opening this intake view…</p>}{!(capabilities.limits.max_import_bytes>0)&&<p className="muted">Citation import is unavailable because import limits are not configured for this workspace.</p>}{intakeFailure&&<div role="alert"><p>{intakeFailure.message}</p><p>Your edits are retained here. Retry saving, stay here, or explicitly restore the last saved drafts.</p><div className="actions"><button type="button" disabled={switching} onClick={()=>recoverIntake("retry")}>Retry</button><button type="button" onClick={()=>setIntakeFailure(null)}>Stay</button><button type="button" disabled={switching} onClick={()=>recoverIntake("restore")}>Discard changes & restore saved drafts…</button></div></div>}</div>
    {pane==="import"&&<ImportPapers key={workspace.id+":imports"} workspaceId={workspace.id} maxBytes={capabilities.limits.max_import_bytes??0} maxRows={capabilities.limits.max_import_rows??0} maxResolutionRows={capabilities.limits.max_import_resolution_rows??0} onCommitted={chooseCollection}/>}
    {pane==="collections"&&<CollectionPicker workspaceId={workspace.id} onChoose={chooseCollection}/>}
    {pane==="search"&&<div id="research-question-query">{!offline&&planner}{(!structured||offline)&&<section><h2>Research question & query</h2><DraftStatus draft={draft}/>
      <form onSubmit={event=>{event.preventDefault();void discover();}}>
        <label>Research question<textarea disabled={!draft.ready} rows={3} value={draft.data.question} maxLength={10000} onChange={event=>{invalidateProposal();draft.setData({...draft.data,question:event.target.value});}}/></label>
        {!offline&&<details><summary>Optional keyword fallback</summary><p className="meta">HEURISTIC KEYWORD FALLBACK · EDITABLE RULE-BASED SUGGESTION</p><button type="button" disabled={!draft.ready||!!busy||!draft.data.question.trim()} onClick={()=>void suggest()}>{busy==="suggest"?"Proposing…":"Propose editable query"}</button>
        {!offline&&currentProposal&&<aside role="region" aria-label="Proposed query"><h3>Proposed query</h3><p>{currentProposal.value.explanation}</p><label>Proposed PubMed query<textarea readOnly rows={6} value={currentProposal.value.query}/></label><div className="actions"><button type="button" disabled={!currentProposal.value.query.trim()} onClick={applyProposal}>Use proposed query</button><button type="button" onClick={invalidateProposal}>Dismiss proposal</button></div><p className="muted">Your current query stays unchanged until you use this proposal. No search has run.</p></aside>}</details>}
        {offline?<label>Recorded saved-example query<textarea rows={6} readOnly disabled={!draft.ready} value={displayedQuery} maxLength={20000}/></label>:<RawStrategyEditor label="PubMed query" value={displayedQuery} disabled={!draft.ready} onChange={value=>{invalidateProposal();draft.setData({...draft.data,query:value});}}/>}
        {offline?<Notice>The recorded query, date and sort belong to the bundled Europe PMC capture. Open saved example adds its {Number(capabilities.saved_example.paper_count??capabilities.saved_example.fetched_count??30)} papers and saved semantic map. Your question and earlier search history are retained; no live search or model call is needed.</Notice>:<>
          <p className="muted">This search specification belongs only to this query. Review the question, exact executable query, publication dates, ordering and record bound before searching. No hidden population, geography, language or study-type restrictions are added. Long Boolean strategies are supported, up to 20,000 characters.</p>
          <div className="control-row"><label>Sort<select value={draft.data.sort} onChange={event=>draft.setData({...draft.data,sort:event.target.value as "relevance"|"pub_date"})}><option value="relevance">Relevance</option><option value="pub_date">Publication date</option></select></label><label>Maximum records<input type="number" min={1} max={capabilities.limits.max_discovery_records??50} value={draft.data.max_results} onChange={event=>draft.setData({...draft.data,max_results:Number(event.target.value)})}/></label></div>
          <label className="check"><input type="checkbox" checked={draft.data.use_dates} onChange={event=>draft.setData({...draft.data,use_dates:event.target.checked})}/> Restrict publication dates</label>
          {draft.data.use_dates&&<div className="control-row"><label>From<input type="date" required value={draft.data.date_from} onChange={event=>draft.setData({...draft.data,date_from:event.target.value})}/></label><label>Through<input type="date" required min={draft.data.date_from} value={draft.data.date_to} onChange={event=>draft.setData({...draft.data,date_to:event.target.value})}/></label></div>}
        </>}
        <div className="actions"><button className="primary" disabled={!draft.ready||!!busy||!displayedQuery.trim()}>{busy==="search"?offline?"Opening example…":"Searching…":offline?"Open saved example":"Search papers"}</button>{search&&<button type="button" disabled={!!busy} onClick={()=>void discover(true)}>{offline?"Open a new saved-example capture":"Explicitly refresh search"}</button>}</div>
      {error&&<div role="status"><Failure message={error}/><p>Edit the query or review its filters, then explicitly search again. Saved results remain available below.</p></div>}
      </form>
    </section>}{offline&&structured&&<details open={requestedPlan?true:undefined}><summary>Plan a separate research search · manual editing available offline</summary>{planner}</details>}
    </div>}
    {requestedCollection&&<CollectionExplorer key={requestedCollection} workspace={workspace} collectionId={requestedCollection} capabilities={capabilities} requestedMap={requestedMap} refresh={refresh} navigate={navigate}/>}
    {!requestedCollection&&!!workspace.searches.length&&<label>Saved search preview<select value={searchId??""} onChange={event=>void navigate({page:"discover",workspace:workspace.id,search:event.target.value,...(requestedPlan?{plan:requestedPlan}:{}),...(requestedPlanRevision?{planRevision:requestedPlanRevision}:{})})}>{[...workspace.searches].reverse().map(item=><option key={item.id} value={item.id}>{item.query.slice(0,90)} · {new Date(item.searched_at).toLocaleString()}</option>)}</select></label>}
    {offline&&search&&search.fetched_count<Number(capabilities.saved_example.paper_count??0)&&<Notice>You are viewing an earlier {search.fetched_count}-paper example. Click Open saved example to add the current {Number(capabilities.saved_example.paper_count)}-paper collection and its semantic map. This earlier capture stays in history.</Notice>}
    {!requestedCollection&&search&&<PaperExplorer key={search.id} workspace={workspace} search={search} capabilities={capabilities} requestedMap={requestedMap} requestedFocusResult={requestedFocusResult} refresh={refresh} navigate={navigate}/>}
  </>;
}

const focusedResults=new Set<string>();
function PaperExplorer({workspace,search,capabilities,requestedMap,requestedFocusResult,refresh,navigate}:{workspace:Schema<"WorkspaceSummary">;search:Schema<"SearchPreview">;capabilities:Schema<"Capabilities">;requestedMap?:string;requestedFocusResult?:string;refresh:()=>Promise<void>;navigate:Navigate}) {
  const resultHeading=useRef<HTMLHeadingElement>(null);
  const preparationAction=useRef(0),alive=useRef(true);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;preparationAction.current++;};},[]);
  useLayoutEffect(()=>{const key=workspace.id+":"+search.id;if(requestedFocusResult!==search.id||focusedResults.has(key)||!resultHeading.current)return;focusedResults.add(key);resultHeading.current.focus({preventScroll:true});resultHeading.current.scrollIntoView({behavior:"instant",block:"start"});},[workspace.id,search.id,requestedFocusResult]);
  const preparedHere=workspace.preparations.find(item=>item.id===workspace.current_preparation_id&&item.search_id===search.id);
  const selection=useDraft(workspace.id,"selection:"+search.id,{selected_paper_ids:preparedHere?.selected_paper_ids??[]});
  const [filter,setFilter]=useState("");const [filterNotice,setFilterNotice]=useState("");const [inspected,setInspected]=useState<string|null>(null);
  const [hovered,setHovered]=useState<string|null>(null);
  const [paperReveal,setPaperReveal]=useState<{id:string;sequence:number}>();
  const [inspectorRequest,setInspectorRequest]=useState(0);
  const inspectorRef=useRef<HTMLElement>(null);
  const inspectorNavigationRef=useRef<HTMLDivElement>(null);
  const navigationAnchor=useRef<{top:number}|null>(null);
  const [preparation,setPreparation]=useState<Schema<"PreparationView">|null>(null);
  const preparationReadGeneration=useRef(0);
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  useEffect(()=>{
    const generation=++preparationReadGeneration.current;
    setPreparation(current=>current?.id===preparedHere?.id?current:null);
    if(preparedHere)api<Schema<"PreparationView">>(workspacePath(workspace.id)+"/source-preparations/"+encodeURIComponent(preparedHere.id)).then(value=>{if(generation===preparationReadGeneration.current)setPreparation(value);}).catch(error=>{if(generation===preparationReadGeneration.current)setError(error.message);});
    return()=>{preparationReadGeneration.current++;};
  },[workspace.id,preparedHere?.id]);
  function publishedPreparation(value:Schema<"PreparationView">){preparationReadGeneration.current++;setPreparation(value);}
  const selected=selection.data.selected_paper_ids as string[];
  const maxPreparedSources=preparedSourceLimit(capabilities.limits);
  const maxSynchronousSources=capabilities.limits.max_synchronous_prepared_sources??0;
  const preparationGated=!capabilities.preparation_jobs_ready&&selected.length>maxSynchronousSources;
  const changed=JSON.stringify([...selected].sort())!==JSON.stringify([...(preparedHere?.selected_paper_ids??[])].sort());
  const visible=search.papers.filter(paper=>(paper.title+" "+paper.abstract+" "+paper.authors.join(" ")).toLowerCase().includes(filter.toLowerCase()));
  function toggle(id:string){selection.setData(previous=>{
    const current=previous.selected_paper_ids as string[];
    const updated=toggleSelectedPaper(current,id,maxPreparedSources);
    return updated===current?previous:{...previous,selected_paper_ids:updated};
  });}
  const reusable=currentExactPreparation(workspace,{kind:"search",search_id:search.id},selected);
  async function prepare(fresh=false){if(preparationGated&&(fresh||!reusable)||selected.length===0||selected.length>maxPreparedSources)return;const action=++preparationAction.current;setBusy(true);setError("");const captured={question:search.research_question||workspace.question,origin:{kind:"search" as const,search_id:search.id},selected_paper_ids:[...selected],expected_source_revision:workspace.source_revision,expected_preparation_id:workspace.current_preparation_id};try{
    await selection.save();if(!alive.current||action!==preparationAction.current)return;const handoff=await createComparisonHandoff(workspace.id,captured);if(!alive.current||action!==preparationAction.current)return;
    let result=reusable&&!fresh?reusable:null;
    if(!result){const payload={search_id:search.id,paper_ids:captured.selected_paper_ids};const prepared=await api<Schema<"PreparationView">>(workspacePath(workspace.id)+"/source-preparations","POST",{...payload,request_id:await requestId(workspace.id+":prepare",payload,fresh)});if(!alive.current||action!==preparationAction.current)return;assertHandoffPreparation(handoff.data,prepared);if(prepared.source_revision!==captured.expected_source_revision+1)throw new Error("Source revision changed during preparation. Review this saved preparation before continuing.");publishedPreparation(prepared);result=prepared;await refresh();}
    const acknowledged=await acknowledgeComparisonHandoff(workspace.id,handoff,{preparation:result});if(!alive.current||action!==preparationAction.current)return;const outcome=await navigate({page:"compare",workspace:workspace.id,preparation:result.id,handoff:acknowledged.scope,setup:"new"});if(outcome&&outcome.status==="blocked")setError(outcome.message);
  }catch(error){setError((error as Error).message);}finally{setBusy(false);}}
  const paper=search.papers.find(item=>item.id===inspected);
  const inspectedIndex=visible.findIndex(item=>item.id===inspected);
  function inspectAdjacent(direction:-1|1){
    if(inspectedIndex<0||direction===-1&&inspectedIndex===0||direction===1&&inspectedIndex===visible.length-1)return;
    const anchor=inspectorNavigationRef.current;
    if(anchor&&!navigationAnchor.current)navigationAnchor.current={top:anchor.getBoundingClientRect().top};
    const ids=visible.map(item=>item.id);
    setInspected(current=>adjacentVisiblePaper(current,ids,direction));
  }
  useLayoutEffect(()=>{
    const anchor=navigationAnchor.current;navigationAnchor.current=null;
    if(!anchor||!inspectorNavigationRef.current||typeof window==="undefined")return;
    const delta=inspectorNavigationRef.current.getBoundingClientRect().top-anchor.top;
    if(delta&&typeof window.scrollBy==="function")window.scrollBy({top:delta,left:0,behavior:"instant"});
  },[inspected]);
  function revealPaper(id:string){
    if(!visible.some(item=>item.id===id)){setFilter("");setFilterNotice("Local filter cleared to show the requested paper.");}
    setInspected(id);setPaperReveal(previous=>({id,sequence:(previous?.sequence??0)+1}));
  }
  function inspectPaper(id:string){setInspected(id);setInspectorRequest(previous=>previous+1);}
  useLayoutEffect(()=>{if(inspectorRequest)inspectorRef.current?.scrollIntoView({behavior:"instant",block:"start"});},[inspectorRequest]);
  return <><section><h2 ref={resultHeading} tabIndex={-1} className="search-result-heading" data-result-id={search.id}>Search preview</h2><p role="status">{search.papers.length?`${search.papers.length} papers loaded. Select up to ${maxPreparedSources}, then Prepare & compare.`:"No papers matched this query."}</p>{!search.papers.length&&<div className="actions"><a href="#research-question-query">Edit query</a><a href="#research-question-query">Review filters</a></div>}<p className="counts">{search.total_reported} provider-reported matches · {search.fetched_count} fetched · {search.papers.length} distinct records · {visible.length} visible · {selected.length} selected · {preparation?.selected_paper_ids.length??0} prepared</p>
    <p className="meta">{search.mode.replaceAll("_"," ")} · {search.provider} · <Time value={search.searched_at}/></p>
    <Notice>Exploratory preview only. A selected paper is selected for exploration, not formally included in a review.</Notice>
    {search.warnings.map((warning,index)=><Notice key={index}>{warning}</Notice>)}{search.errors.map((failure,index)=><Failure key={index} message={failure.message}/>)}
    <details><summary>Exact search provenance</summary><dl><dt>Query</dt><dd className="preserve">{search.query}</dd><dt>Provider translation</dt><dd>{search.query_translation||"Not supplied"}</dd><dt>Sort</dt><dd>{search.sort}</dd><dt>Publication dates</dt><dd>{search.date_from&&search.date_to?`${search.date_from} through ${search.date_to}`:"Unrestricted"}</dd><dt>Requested preview bound</dt><dd>{search.requested_max_results??"Not recorded for this historical capture"}</dd><dt>Actual fetched records</dt><dd>{search.fetched_count}</dd><dt>Configuration snapshot</dt><dd>{search.configuration_profile?JSON.stringify(search.configuration_profile):"Not recorded for this historical capture"}</dd><dt>Truncated</dt><dd>{String(search.truncated)}</dd><dt>Ordered identifiers</dt><dd>{search.ordered_identifiers.join(", ")}</dd><dt>Search ID</dt><dd>{search.id}</dd></dl></details>
  </section>
  <section><h2>Explore this saved search</h2><label>Filter papers and map points<input type="search" value={filter} onChange={event=>{setFilter(event.target.value);setFilterNotice("");}} placeholder="Title, abstract or author"/></label><p className="muted">Filtering only changes visibility. Saved map coordinates, source preparation and evidence stay unchanged.</p>{filterNotice&&<p role="status" className="muted">{filterNotice}</p>}</section>
  <ExplorationPanels revealPaper={paperReveal} map={<MapExplorer workspaceId={workspace.id} search={search} capability={capabilities.map} requestedMap={requestedMap} visibleIds={new Set(visible.map(item=>item.id))} selectedIds={new Set(selected)} selectionLimit={maxPreparedSources} inspectedId={inspected} hoveredId={hovered} onInspect={revealPaper} onHover={setHovered} onChooseMap={id=>void navigate({page:"discover",workspace:workspace.id,search:search.id,map:id})}/>}
    inspector={paper&&<aside ref={inspectorRef} id="paper-inspector" className="paper-inspector" aria-label="Paper inspector"><ExplorationHeading title="Paper inspector" level={3} selectedIds={selected} maxSources={maxPreparedSources} visibleIds={new Set(visible.map(item=>item.id))}/><Citation paper={paper}/><p className="preserve">{paper.abstract||"No abstract supplied; title-only metadata."}</p><label className="check"><input type="checkbox" checked={selected.includes(paper.id)} disabled={!selection.ready||(!selected.includes(paper.id)&&selected.length>=maxPreparedSources)} onChange={()=>toggle(paper.id)}/>Select this paper for exploration</label>
      <div ref={inspectorNavigationRef} className="paper-inspector-navigation" aria-label="Paper inspector navigation">
        <button type="button" aria-label="Previous paper" disabled={inspectedIndex<=0} onClick={()=>inspectAdjacent(-1)}>← Previous</button>
        <span className="meta">{inspectedIndex<0?"Outside the current filter":`${inspectedIndex+1} of ${visible.length} visible`}</span>
        <button type="button" aria-label="Next paper" disabled={inspectedIndex<0||inspectedIndex>=visible.length-1} onClick={()=>inspectAdjacent(1)}>Next →</button>
      </div>
      <p className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">{paper.title}. {inspectedIndex<0?"Outside the current filter.":`Paper ${inspectedIndex+1} of ${visible.length}.`}</p>
      {inspectedIndex<0&&<p className="muted">This inspected paper is outside the current filter. Clear the filter or inspect a visible paper to continue sequence navigation. Your selection is unchanged.</p>}
    </aside>}
    papers={<section><ExplorationHeading title="Papers & source selection" selectedIds={selected} maxSources={maxPreparedSources} visibleIds={new Set(visible.map(item=>item.id))} sticky/><DraftStatus draft={selection}/>
    {!search.papers.length?<Notice>No records matched this preview. Edit the query or dates, then explicitly search again.</Notice>:!visible.length?<p>No records match this local filter.</p>:visible.map(item=><article id={"paper-selection-"+encodeURIComponent(item.id)} data-paper-id={item.id} tabIndex={-1} aria-label={"Paper: "+item.title} className={["paper",inspected===item.id?"selected":"",hovered===item.id?"hovered":""].join(" ")} key={item.id} onMouseEnter={()=>setHovered(item.id)} onMouseLeave={()=>setHovered(null)} onFocus={()=>setHovered(item.id)} onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node|null))setHovered(null);}}>
      <label className="check selection-label"><input type="checkbox" checked={selected.includes(item.id)} disabled={!selection.ready||(!selected.includes(item.id)&&selected.length>=maxPreparedSources)} onChange={()=>toggle(item.id)}/>Select for exploration</label><Citation paper={item}/>
      <button type="button" aria-pressed={inspected===item.id} onClick={()=>inspectPaper(item.id)}>Inspect paper</button></article>)}
  </section>}/>
  {search.papers.length>0&&<section><h2>Prepare selected sources</h2><p>Select up to {maxPreparedSources} papers. Preparation checks identity and permissions; unavailable full text may use an explicitly labeled abstract fallback.</p><p className="muted">A comparison board can use up to 30 prepared papers and {capabilities.boards.max_cells} cells. Optional AI suggestions keep their separate bounded selection and call budgets.</p><Failure message={error}/>
    {!capabilities.preparation_jobs_ready&&<Notice>Persisted preparation jobs are not available in this checkpoint. Up to {maxSynchronousSources} sources can be prepared now; a larger selection is retained until the preparation execution and storage checks pass.</Notice>}
    {changed&&workspace.current_preparation_id&&<Notice>Selection changed; current passages still use the previous prepared sources.</Notice>}
    {capabilities.preparation_jobs_ready?<PreparationJobs workspace={workspace} search={search} selectedPaperIds={selected} selectionReady={selection.ready} maxSources={maxPreparedSources} flushSelection={selection.save} refresh={refresh} onPublished={publishedPreparation} navigate={navigate} question={search.research_question||workspace.question}/>:<div className="actions"><button className="primary" disabled={!selection.ready||selected.length===0||selected.length>maxPreparedSources||preparationGated&&!reusable||busy} onClick={()=>void prepare()}>{busy?"Preparing sources…":reusable?`Continue to comparison (${selected.length})`:`Prepare & compare (${selected.length})`}</button>{preparation&&<button disabled={!selection.ready||selected.length===0||selected.length>maxPreparedSources||preparationGated||busy} onClick={()=>void prepare(true)}>Explicitly refresh sources</button>}</div>}
    {preparation&&<><p className="meta">PREPARATION {preparation.id} · SOURCE REVISION {preparation.source_revision}</p>{preparation.sources.map(source=><article className="source" key={source.id}><h3>{search.papers.find(item=>item.id===source.paper_id)?.title??source.paper_id}</h3><SourceMetadata source={source}/></article>)}
      <button onClick={()=>void navigate({page:"evidence",workspace:workspace.id})}>Optional passage search</button></>}
  </section>}</>;
}
