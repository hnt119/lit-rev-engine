"use client";
import {useEffect,useLayoutEffect,useRef,useState} from "react";
import {api,requestId,workspacePath,type Schema} from "../lib/api";
import {DraftStatus,flushDrafts,useDraft} from "../lib/drafts";
import {Citation,Failure,Notice,SourceMetadata,Time} from "./ui";
import MapExplorer from "./map-explorer";
import ExplorationPanels from "./exploration-panels";
import {adjacentVisiblePaper,preparedSourceLimit,toggleSelectedPaper} from "../lib/paper-selection";
import PreparationJobs from "./preparation-jobs";
import ImportPapers from "./import-papers";
import CollectionExplorer,{CollectionPicker} from "./collection-explorer";
import type {Navigate} from "./workspace-app";
import SearchPlanner,{RawStrategyEditor} from "./search-planner";

type Props={workspace:Schema<"WorkspaceSummary">;capabilities:Schema<"Capabilities">;requestedSearch?:string;requestedMap?:string;requestedCollection?:string;requestedPlan?:string;requestedPlanRevision?:string;refresh:()=>Promise<void>;navigate:Navigate};
export default function Discover({workspace,capabilities,requestedSearch,requestedMap,requestedCollection,requestedPlan,requestedPlanRevision,refresh,navigate}:Props) {
  const offline=workspace.mode==="saved_example",structured=capabilities.search_plans_ready===true;
  const bundledQuery=String(capabilities.saved_example.query??"");
  const bundleId=String(capabilities.saved_example.bundle_id??capabilities.saved_example.searched_at??"historical-example");
  const draft=useDraft(workspace.id,"discover",{question:workspace.question||String(capabilities.saved_example.question??""),query:offline?String(capabilities.saved_example.query??""):"",sort:"relevance",max_results:30,use_dates:false,date_from:"",date_to:""});
  const latest=workspace.searches.at(-1);
  const searchId=requestedCollection?undefined:requestedSearch??latest?.id;
  const [pane,setPane]=useState<"search"|"import"|"browse">("search");
  useEffect(()=>setPane("search"),[requestedCollection,requestedSearch]);
  const [search,setSearch]=useState<Schema<"SearchPreview">|null>(null);
  const [busy,setBusy]=useState("");const [error,setError]=useState("");
  const [proposal,setProposal]=useState<{question:string;originalQuery:string;value:Schema<"QuerySuggestion">}|null>(null);
  const proposalGeneration=useRef(0);
  const currentProposal=proposal?.question===draft.data.question&&proposal.originalQuery===draft.data.query?proposal:null;
  const displayedQuery=offline?bundledQuery:draft.data.query;
  useEffect(()=>{let disposed=false;setSearch(null);if(searchId)api<Schema<"SearchPreview">>(workspacePath(workspace.id)+"/searches/"+encodeURIComponent(searchId)+"/papers").then(value=>{if(!disposed)setSearch(value);}).catch(error=>{if(!disposed)setError(error.message);});return()=>{disposed=true;};},[workspace.id,searchId]);
  function invalidateProposal(){proposalGeneration.current++;setProposal(null);}
  async function suggest(){setBusy("suggest");setError("");setProposal(null);const generation=++proposalGeneration.current,question=draft.data.question,originalQuery=draft.data.query;try{const value=await api<Schema<"QuerySuggestion">>(workspacePath(workspace.id)+"/query-suggestions","POST",{question});if(proposalGeneration.current===generation)setProposal({question,originalQuery,value});}catch(error){setError((error as Error).message);}finally{setBusy("");}}
  function applyProposal(){if(!currentProposal?.value.query.trim())return;draft.setData(previous=>previous.question===currentProposal.question&&previous.query===currentProposal.originalQuery?{...previous,query:currentProposal.value.query}:previous);invalidateProposal();}
  async function discover(fresh=false){setBusy("search");setError("");try{
    await draft.save();const payload={query:displayedQuery,research_question:draft.data.question||null,sort:offline?"relevance":draft.data.sort,max_results:offline?30:Number(draft.data.max_results),date_from:!offline&&draft.data.use_dates?draft.data.date_from:null,date_to:!offline&&draft.data.use_dates?draft.data.date_to:null};
    const fingerprint=offline?{...payload,saved_example_bundle:bundleId}:payload;
    const result=await api<Schema<"SearchPreview">>(workspacePath(workspace.id)+"/searches","POST",{...payload,request_id:await requestId(workspace.id+":search",fingerprint,fresh)});
    setSearch(result);await refresh();await navigate({page:"discover",workspace:workspace.id,search:result.id});
  }catch(error){setError((error as Error).message);}finally{setBusy("");}}
  async function chooseCollection(value:Schema<"CollectionSummary">){await refresh();setPane("search");await navigate(value.origin.kind==="search"?{page:"discover",workspace:workspace.id,search:value.origin.search_id}:{page:"discover",workspace:workspace.id,collection:value.id});}
  async function openPane(value:typeof pane){try{await flushDrafts();setError("");setPane(value);}catch(error){setError((error as Error).message);}}
  const planner=structured&&draft.ready&&<SearchPlanner key={workspace.id+":planner"} workspace={workspace} initialQuestion={draft.data.question} requestedPlan={requestedPlan} requestedRevision={requestedPlanRevision} onOpen={async(planId,revisionId)=>navigate({page:"discover",workspace:workspace.id,...(searchId?{search:searchId}:{}),...(requestedMap?{map:requestedMap}:{}),...(planId?{plan:planId}:{}),...(revisionId?{planRevision:revisionId}:{})})} onExecuted={async result=>{setSearch(result);await refresh();await navigate({page:"discover",workspace:workspace.id,search:result.id,...(requestedPlan?{plan:requestedPlan}:{})});}}/>;
  return <><h1>Discover & explore</h1><p>Search a bounded preview, then explicitly choose sources for passage retrieval.</p><Failure message={error}/>
    {(requestedCollection||pane!=="search")&&<div className="actions"><button type="button" onClick={()=>requestedCollection?navigate({page:"discover",workspace:workspace.id}):openPane("search")}>Search papers</button><button type="button" disabled={!(capabilities.limits.max_import_bytes>0)} onClick={()=>openPane("import")}>Import papers</button><button type="button" onClick={()=>openPane("browse")}>Browse collections</button></div>}
    {pane==="import"&&<ImportPapers key={workspace.id+":imports"} workspaceId={workspace.id} maxBytes={capabilities.limits.max_import_bytes??0} maxRows={capabilities.limits.max_import_rows??0} maxResolutionRows={capabilities.limits.max_import_resolution_rows??0} onCommitted={chooseCollection}/>}
    {pane==="browse"&&<CollectionPicker workspaceId={workspace.id} onChoose={chooseCollection}/>}
    {pane==="search"&&requestedCollection&&<CollectionExplorer key={requestedCollection} workspace={workspace} collectionId={requestedCollection} capabilities={capabilities} requestedMap={requestedMap} refresh={refresh} navigate={navigate}/>}
    {pane==="search"&&!requestedCollection&&<>{!offline&&planner}{structured&&!offline&&<div className="actions"><button type="button" disabled={!(capabilities.limits.max_import_bytes>0)} onClick={()=>openPane("import")}>Import papers</button><button type="button" onClick={()=>openPane("browse")}>Browse collections</button></div>}{(!structured||offline)&&<section><h2>Research question & query</h2><DraftStatus draft={draft}/>
      <form onSubmit={event=>{event.preventDefault();void discover();}}>
        <label>Research question<textarea disabled={!draft.ready} rows={3} value={draft.data.question} maxLength={10000} onChange={event=>{invalidateProposal();draft.setData({...draft.data,question:event.target.value});}}/></label>
        {!offline&&<><p className="meta">HEURISTIC KEYWORD FALLBACK · EDITABLE RULE-BASED SUGGESTION</p><button type="button" disabled={!draft.ready||!!busy||!draft.data.question.trim()} onClick={()=>void suggest()}>{busy==="suggest"?"Proposing…":"Propose editable query"}</button></>}
        {!offline&&currentProposal&&<aside role="region" aria-label="Proposed query"><h3>Proposed query</h3><p>{currentProposal.value.explanation}</p><label>Proposed PubMed query<textarea readOnly rows={6} value={currentProposal.value.query}/></label><div className="actions"><button type="button" disabled={!currentProposal.value.query.trim()} onClick={applyProposal}>Use proposed query</button><button type="button" onClick={invalidateProposal}>Dismiss proposal</button></div><p className="muted">Your current query stays unchanged until you use this proposal. No search has run.</p></aside>}
        {offline?<label>Recorded saved-example query<textarea rows={6} readOnly disabled={!draft.ready} value={displayedQuery} maxLength={20000}/></label>:<RawStrategyEditor label="PubMed query" value={displayedQuery} disabled={!draft.ready} onChange={value=>{invalidateProposal();draft.setData({...draft.data,query:value});}}/>}
        {offline?<Notice>The recorded query, date and sort belong to the bundled Europe PMC capture. Open saved example adds its {Number(capabilities.saved_example.paper_count??capabilities.saved_example.fetched_count??30)} papers and saved semantic map. Your question and earlier search history are retained; no live search or model call is needed.</Notice>:<>
          <p className="muted">Propose a compact keyword search from your question, or paste a complete strategy. Review the kept concepts and grouping before applying. Long Boolean strategies are supported, up to 20,000 characters. Search uses the query shown here.</p>
          <div className="control-row"><label>Sort<select value={draft.data.sort} onChange={event=>draft.setData({...draft.data,sort:event.target.value})}><option value="relevance">Relevance</option><option value="pub_date">Publication date</option></select></label><label>Maximum records<input type="number" min={1} max={50} value={draft.data.max_results} onChange={event=>draft.setData({...draft.data,max_results:Number(event.target.value)})}/></label></div>
          <label className="check"><input type="checkbox" checked={draft.data.use_dates} onChange={event=>draft.setData({...draft.data,use_dates:event.target.checked})}/> Restrict publication dates</label>
          {draft.data.use_dates&&<div className="control-row"><label>From<input type="date" required value={draft.data.date_from} onChange={event=>draft.setData({...draft.data,date_from:event.target.value})}/></label><label>Through<input type="date" required min={draft.data.date_from} value={draft.data.date_to} onChange={event=>draft.setData({...draft.data,date_to:event.target.value})}/></label></div>}
        </>}
        <div className="actions"><button className="primary" disabled={!draft.ready||!!busy||!displayedQuery.trim()}>{busy==="search"?offline?"Opening example…":"Searching…":offline?"Open saved example":"Search PubMed preview"}</button>{search&&<button type="button" disabled={!!busy} onClick={()=>void discover(true)}>{offline?"Open a new saved-example capture":"Explicitly refresh search"}</button>}<button type="button" disabled={!!busy||!(capabilities.limits.max_import_bytes>0)} onClick={()=>openPane("import")}>Import papers</button><button type="button" disabled={!!busy} onClick={()=>openPane("browse")}>Browse collections</button></div>
      </form>
    </section>}{offline&&structured&&<details open={requestedPlan?true:undefined}><summary>Plan a separate research search · manual editing available offline</summary>{planner}</details>}
    {!!workspace.searches.length&&<label>Saved search preview<select value={searchId??""} onChange={event=>void navigate({page:"discover",workspace:workspace.id,search:event.target.value,...(requestedPlan?{plan:requestedPlan}:{}),...(requestedPlanRevision?{planRevision:requestedPlanRevision}:{})})}>{[...workspace.searches].reverse().map(item=><option key={item.id} value={item.id}>{item.query.slice(0,90)} · {new Date(item.searched_at).toLocaleString()}</option>)}</select></label>}
    {offline&&search&&search.fetched_count<Number(capabilities.saved_example.paper_count??0)&&<Notice>You are viewing an earlier {search.fetched_count}-paper example. Click Open saved example to add the current {Number(capabilities.saved_example.paper_count)}-paper collection and its semantic map. This earlier capture stays in history.</Notice>}
    {search&&<PaperExplorer key={search.id} workspace={workspace} search={search} capabilities={capabilities} requestedMap={requestedMap} refresh={refresh} navigate={navigate}/>}
    </>}
  </>;
}

function PaperExplorer({workspace,search,capabilities,requestedMap,refresh,navigate}:{workspace:Schema<"WorkspaceSummary">;search:Schema<"SearchPreview">;capabilities:Schema<"Capabilities">;requestedMap?:string;refresh:()=>Promise<void>;navigate:Navigate}) {
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
  async function prepare(fresh=false){if(preparationGated||selected.length===0||selected.length>maxPreparedSources)return;setBusy(true);setError("");try{
    await selection.save();const payload={search_id:search.id,paper_ids:selected};
    const result=await api<Schema<"PreparationView">>(workspacePath(workspace.id)+"/source-preparations","POST",{...payload,request_id:await requestId(workspace.id+":prepare",payload,fresh)});
    publishedPreparation(result);await refresh();
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
  return <><section><h2>Search preview</h2><p className="counts">{search.total_reported} provider-reported matches · {search.fetched_count} fetched · {search.papers.length} distinct records · {visible.length} visible · {selected.length} selected · {preparation?.selected_paper_ids.length??0} prepared</p>
    <p className="meta">{search.mode.replaceAll("_"," ")} · {search.provider} · <Time value={search.searched_at}/></p>
    <Notice>Exploratory preview only. A selected paper is selected for exploration, not formally included in a review.</Notice>
    {search.warnings.map((warning,index)=><Notice key={index}>{warning}</Notice>)}{search.errors.map((failure,index)=><Failure key={index} message={failure.message}/>)}
    <details><summary>Exact search provenance</summary><dl><dt>Query</dt><dd className="preserve">{search.query}</dd><dt>Provider translation</dt><dd>{search.query_translation||"Not supplied"}</dd><dt>Sort</dt><dd>{search.sort}</dd><dt>Publication dates</dt><dd>{search.date_from&&search.date_to?`${search.date_from} through ${search.date_to}`:"Unrestricted"}</dd><dt>Truncated</dt><dd>{String(search.truncated)}</dd><dt>Ordered identifiers</dt><dd>{search.ordered_identifiers.join(", ")}</dd><dt>Search ID</dt><dd>{search.id}</dd></dl></details>
  </section>
  <section><h2>Explore this saved search</h2><label>Filter papers and map points<input type="search" value={filter} onChange={event=>{setFilter(event.target.value);setFilterNotice("");}} placeholder="Title, abstract or author"/></label><p className="muted">Filtering only changes visibility. Saved map coordinates, source preparation and evidence stay unchanged.</p>{filterNotice&&<p role="status" className="muted">{filterNotice}</p>}</section>
  <ExplorationPanels revealPaper={paperReveal} map={<MapExplorer workspaceId={workspace.id} search={search} capability={capabilities.map} requestedMap={requestedMap} visibleIds={new Set(visible.map(item=>item.id))} selectedIds={new Set(selected)} inspectedId={inspected} hoveredId={hovered} onInspect={revealPaper} onHover={setHovered} onChooseMap={id=>void navigate({page:"discover",workspace:workspace.id,search:search.id,map:id})}/>}
    inspector={paper&&<aside ref={inspectorRef} id="paper-inspector" className="paper-inspector" aria-label="Paper inspector"><h3>Paper inspector</h3><Citation paper={paper}/><p className="preserve">{paper.abstract||"No abstract supplied; title-only metadata."}</p><label className="check"><input type="checkbox" checked={selected.includes(paper.id)} disabled={!selection.ready||(!selected.includes(paper.id)&&selected.length>=maxPreparedSources)} onChange={()=>toggle(paper.id)}/>Select this paper for exploration</label>
      <div ref={inspectorNavigationRef} className="paper-inspector-navigation" aria-label="Paper inspector navigation">
        <button type="button" aria-label="Previous paper" disabled={inspectedIndex<=0} onClick={()=>inspectAdjacent(-1)}>← Previous</button>
        <span className="meta">{inspectedIndex<0?"Outside the current filter":`${inspectedIndex+1} of ${visible.length}`}</span>
        <button type="button" aria-label="Next paper" disabled={inspectedIndex<0||inspectedIndex>=visible.length-1} onClick={()=>inspectAdjacent(1)}>Next →</button>
      </div>
      <p className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">{paper.title}. {inspectedIndex<0?"Outside the current filter.":`Paper ${inspectedIndex+1} of ${visible.length}.`}</p>
      {inspectedIndex<0&&<p className="muted">This inspected paper is outside the current filter. Clear the filter or inspect a visible paper to continue sequence navigation. Your selection is unchanged.</p>}
    </aside>}
    papers={<section><h2>Papers & source selection</h2><DraftStatus draft={selection}/>
    {!search.papers.length?<Notice>No records matched this preview. Edit the query or dates, then explicitly search again.</Notice>:!visible.length?<p>No records match this local filter.</p>:visible.map(item=><article id={"paper-selection-"+encodeURIComponent(item.id)} data-paper-id={item.id} tabIndex={-1} aria-label={"Paper: "+item.title} className={["paper",inspected===item.id?"selected":"",hovered===item.id?"hovered":""].join(" ")} key={item.id} onMouseEnter={()=>setHovered(item.id)} onMouseLeave={()=>setHovered(null)} onFocus={()=>setHovered(item.id)} onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node|null))setHovered(null);}}>
      <label className="check selection-label"><input type="checkbox" checked={selected.includes(item.id)} disabled={!selection.ready||(!selected.includes(item.id)&&selected.length>=maxPreparedSources)} onChange={()=>toggle(item.id)}/>Select for exploration</label><Citation paper={item}/>
      <button type="button" aria-pressed={inspected===item.id} onClick={()=>inspectPaper(item.id)}>Inspect paper</button></article>)}
  </section>}/>
  <section><h2>Prepare selected sources</h2><p>Select up to {maxPreparedSources} papers. Preparation checks identity and permissions; unavailable full text may use an explicitly labeled abstract fallback.</p><p className="muted">A comparison board still uses at most 10 prepared papers and {capabilities.boards.max_cells} cells. Optional AI suggestions keep their separate bounded selection and call budgets.</p><Failure message={error}/>
    {!capabilities.preparation_jobs_ready&&<Notice>Persisted preparation jobs are not available in this checkpoint. Up to {maxSynchronousSources} sources can be prepared now; a larger selection is retained until the preparation execution and storage checks pass.</Notice>}
    {changed&&workspace.current_preparation_id&&<Notice>Selection changed; current passages still use the previous prepared sources.</Notice>}
    {capabilities.preparation_jobs_ready?<PreparationJobs workspace={workspace} search={search} selectedPaperIds={selected} selectionReady={selection.ready} maxSources={maxPreparedSources} flushSelection={selection.save} refresh={refresh} onPublished={publishedPreparation}/>:<div className="actions"><button className="primary" disabled={!selection.ready||selected.length===0||selected.length>maxPreparedSources||preparationGated||busy} onClick={()=>void prepare()}>{busy?"Preparing sources…":"Prepare selected sources"}</button>{preparation&&<button disabled={!selection.ready||selected.length===0||selected.length>maxPreparedSources||preparationGated||busy} onClick={()=>void prepare(true)}>Explicitly refresh sources</button>}</div>}
    {preparation&&<><p className="meta">PREPARATION {preparation.id} · SOURCE REVISION {preparation.source_revision}</p>{preparation.sources.map(source=><article className="source" key={source.id}><h3>{search.papers.find(item=>item.id===source.paper_id)?.title??source.paper_id}</h3><SourceMetadata source={source}/></article>)}
      <button className="primary" onClick={()=>void navigate({page:"evidence",workspace:workspace.id})}>Continue to passage search</button></>}
  </section></>;
}
