"use client";
import {useEffect,useLayoutEffect,useRef,useState} from "react";
import {api,requestId,workspacePath,type Schema} from "../lib/api";
import {DraftStatus,useDraft} from "../lib/drafts";
import {Citation,Failure,Notice,SourceMetadata,Time} from "./ui";
import MapExplorer from "./map-explorer";
import ExplorationPanels from "./exploration-panels";
import type {Navigate} from "./workspace-app";

type Props={workspace:Schema<"WorkspaceSummary">;capabilities:Schema<"Capabilities">;requestedSearch?:string;requestedMap?:string;refresh:()=>Promise<void>;navigate:Navigate};
export default function Discover({workspace,capabilities,requestedSearch,requestedMap,refresh,navigate}:Props) {
  const offline=workspace.mode==="saved_example";
  const bundledQuery=String(capabilities.saved_example.query??"");
  const bundleId=String(capabilities.saved_example.bundle_id??capabilities.saved_example.searched_at??"historical-example");
  const draft=useDraft(workspace.id,"discover",{question:workspace.question||String(capabilities.saved_example.question??""),query:offline?String(capabilities.saved_example.query??""):"",sort:"relevance",max_results:30,use_dates:false,date_from:"",date_to:""});
  const latest=workspace.searches.at(-1);
  const searchId=requestedSearch??latest?.id;
  const [search,setSearch]=useState<Schema<"SearchPreview">|null>(null);
  const [busy,setBusy]=useState("");const [error,setError]=useState("");
  const [proposal,setProposal]=useState<{question:string;originalQuery:string;value:Schema<"QuerySuggestion">}|null>(null);
  const proposalGeneration=useRef(0);
  const currentProposal=proposal?.question===draft.data.question&&proposal.originalQuery===draft.data.query?proposal:null;
  const displayedQuery=offline?bundledQuery:draft.data.query;
  useEffect(()=>{setSearch(null);if(searchId)api<Schema<"SearchPreview">>(workspacePath(workspace.id)+"/searches/"+encodeURIComponent(searchId)+"/papers").then(setSearch).catch(error=>setError(error.message));},[workspace.id,searchId]);
  function invalidateProposal(){proposalGeneration.current++;setProposal(null);}
  async function suggest(){setBusy("suggest");setError("");setProposal(null);const generation=++proposalGeneration.current,question=draft.data.question,originalQuery=draft.data.query;try{const value=await api<Schema<"QuerySuggestion">>(workspacePath(workspace.id)+"/query-suggestions","POST",{question});if(proposalGeneration.current===generation)setProposal({question,originalQuery,value});}catch(error){setError((error as Error).message);}finally{setBusy("");}}
  function applyProposal(){if(!currentProposal?.value.query.trim())return;draft.setData(previous=>previous.question===currentProposal.question&&previous.query===currentProposal.originalQuery?{...previous,query:currentProposal.value.query}:previous);invalidateProposal();}
  async function discover(fresh=false){setBusy("search");setError("");try{
    await draft.save();const payload={query:displayedQuery,research_question:draft.data.question||null,sort:offline?"relevance":draft.data.sort,max_results:offline?30:Number(draft.data.max_results),date_from:!offline&&draft.data.use_dates?draft.data.date_from:null,date_to:!offline&&draft.data.use_dates?draft.data.date_to:null};
    const fingerprint=offline?{...payload,saved_example_bundle:bundleId}:payload;
    const result=await api<Schema<"SearchPreview">>(workspacePath(workspace.id)+"/searches","POST",{...payload,request_id:await requestId(workspace.id+":search",fingerprint,fresh)});
    setSearch(result);await refresh();await navigate({page:"discover",workspace:workspace.id,search:result.id});
  }catch(error){setError((error as Error).message);}finally{setBusy("");}}
  return <><h1>Discover & explore</h1><p>Search a bounded preview, then explicitly choose sources for passage retrieval.</p>
    <section><h2>Research question & query</h2><DraftStatus draft={draft}/><Failure message={error}/>
      <form onSubmit={event=>{event.preventDefault();void discover();}}>
        <label>Research question<textarea disabled={!draft.ready} rows={3} value={draft.data.question} maxLength={10000} onChange={event=>{invalidateProposal();draft.setData({...draft.data,question:event.target.value});}}/></label>
        {!offline&&<button type="button" disabled={!draft.ready||!!busy||!draft.data.question.trim()} onClick={()=>void suggest()}>{busy==="suggest"?"Proposing…":"Propose editable query"}</button>}
        {!offline&&currentProposal&&<aside role="region" aria-label="Proposed query"><h3>Proposed query</h3><p>{currentProposal.value.explanation}</p><label>Proposed PubMed query<textarea readOnly rows={6} value={currentProposal.value.query}/></label><div className="actions"><button type="button" disabled={!currentProposal.value.query.trim()} onClick={applyProposal}>Use proposed query</button><button type="button" onClick={invalidateProposal}>Dismiss proposal</button></div><p className="muted">Your current query stays unchanged until you use this proposal. No search has run.</p></aside>}
        <label>{offline?"Recorded saved-example query":"PubMed query"}<textarea rows={6} readOnly={offline} disabled={!draft.ready} value={displayedQuery} maxLength={20000} onChange={event=>{invalidateProposal();draft.setData({...draft.data,query:event.target.value});}}/></label>
        {offline?<Notice>The recorded query, date and sort belong to the bundled Europe PMC capture. Open saved example adds its {Number(capabilities.saved_example.paper_count??capabilities.saved_example.fetched_count??30)} papers and saved semantic map. Your question and earlier search history are retained; no live search or model call is needed.</Notice>:<>
          <p className="muted">Propose a compact keyword search from your question, or paste a complete strategy. Review the kept concepts and grouping before applying. Long Boolean strategies are supported, up to 20,000 characters. Search uses the query shown here.</p>
          <div className="control-row"><label>Sort<select value={draft.data.sort} onChange={event=>draft.setData({...draft.data,sort:event.target.value})}><option value="relevance">Relevance</option><option value="pub_date">Publication date</option></select></label><label>Maximum records<input type="number" min={1} max={50} value={draft.data.max_results} onChange={event=>draft.setData({...draft.data,max_results:Number(event.target.value)})}/></label></div>
          <label className="check"><input type="checkbox" checked={draft.data.use_dates} onChange={event=>draft.setData({...draft.data,use_dates:event.target.checked})}/> Restrict publication dates</label>
          {draft.data.use_dates&&<div className="control-row"><label>From<input type="date" required value={draft.data.date_from} onChange={event=>draft.setData({...draft.data,date_from:event.target.value})}/></label><label>Through<input type="date" required min={draft.data.date_from} value={draft.data.date_to} onChange={event=>draft.setData({...draft.data,date_to:event.target.value})}/></label></div>}
        </>}
        <div className="actions"><button className="primary" disabled={!draft.ready||!!busy||!displayedQuery.trim()}>{busy==="search"?offline?"Opening example…":"Searching…":offline?"Open saved example":"Search PubMed preview"}</button>{search&&<button type="button" disabled={!!busy} onClick={()=>void discover(true)}>{offline?"Open a new saved-example capture":"Explicitly refresh search"}</button>}</div>
      </form>
    </section>
    {!!workspace.searches.length&&<label>Saved search preview<select value={searchId??""} onChange={event=>void navigate({page:"discover",workspace:workspace.id,search:event.target.value})}>{[...workspace.searches].reverse().map(item=><option key={item.id} value={item.id}>{item.query.slice(0,90)} · {new Date(item.searched_at).toLocaleString()}</option>)}</select></label>}
    {offline&&search&&search.fetched_count<Number(capabilities.saved_example.paper_count??0)&&<Notice>You are viewing an earlier {search.fetched_count}-paper example. Click Open saved example to add the current {Number(capabilities.saved_example.paper_count)}-paper collection and its semantic map. This earlier capture stays in history.</Notice>}
    {search&&<PaperExplorer key={search.id} workspace={workspace} search={search} capabilities={capabilities} requestedMap={requestedMap} refresh={refresh} navigate={navigate}/>}
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
  const [preparation,setPreparation]=useState<Schema<"PreparationView">|null>(null);
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  useEffect(()=>{setPreparation(null);if(preparedHere)api<Schema<"PreparationView">>(workspacePath(workspace.id)+"/source-preparations/"+encodeURIComponent(preparedHere.id)).then(setPreparation).catch(error=>setError(error.message));},[workspace.id,preparedHere?.id]);
  const selected=selection.data.selected_paper_ids as string[];
  const changed=JSON.stringify([...selected].sort())!==JSON.stringify([...(preparedHere?.selected_paper_ids??[])].sort());
  const visible=search.papers.filter(paper=>(paper.title+" "+paper.abstract+" "+paper.authors.join(" ")).toLowerCase().includes(filter.toLowerCase()));
  function toggle(id:string){selection.setData(previous=>{
    const current=previous.selected_paper_ids as string[];
    if(current.includes(id))return {...previous,selected_paper_ids:current.filter(value=>value!==id)};
    return current.length<10?{...previous,selected_paper_ids:[...current,id]}:previous;
  });}
  async function prepare(fresh=false){setBusy(true);setError("");try{
    await selection.save();const payload={search_id:search.id,paper_ids:selected};
    const result=await api<Schema<"PreparationView">>(workspacePath(workspace.id)+"/source-preparations","POST",{...payload,request_id:await requestId(workspace.id+":prepare",payload,fresh)});
    setPreparation(result);await refresh();
  }catch(error){setError((error as Error).message);}finally{setBusy(false);}}
  const paper=search.papers.find(item=>item.id===inspected);
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
    inspector={paper&&<aside ref={inspectorRef} id="paper-inspector" className="paper-inspector" aria-label="Paper inspector"><h3>Paper inspector</h3><Citation paper={paper}/><p className="preserve">{paper.abstract||"No abstract supplied; title-only metadata."}</p><label className="check"><input type="checkbox" checked={selected.includes(paper.id)} disabled={!selection.ready||(!selected.includes(paper.id)&&selected.length>=10)} onChange={()=>toggle(paper.id)}/>Select this paper for exploration</label></aside>}
    papers={<section><h2>Papers & source selection</h2><DraftStatus draft={selection}/>
    {!search.papers.length?<Notice>No records matched this preview. Edit the query or dates, then explicitly search again.</Notice>:!visible.length?<p>No records match this local filter.</p>:visible.map(item=><article id={"paper-selection-"+encodeURIComponent(item.id)} data-paper-id={item.id} tabIndex={-1} aria-label={"Paper: "+item.title} className={["paper",inspected===item.id?"selected":"",hovered===item.id?"hovered":""].join(" ")} key={item.id} onMouseEnter={()=>setHovered(item.id)} onMouseLeave={()=>setHovered(null)} onFocus={()=>setHovered(item.id)} onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node|null))setHovered(null);}}>
      <label className="check selection-label"><input type="checkbox" checked={selected.includes(item.id)} disabled={!selection.ready||(!selected.includes(item.id)&&selected.length>=10)} onChange={()=>toggle(item.id)}/>Select for exploration</label><Citation paper={item}/>
      <button type="button" aria-pressed={inspected===item.id} onClick={()=>inspectPaper(item.id)}>Inspect paper</button></article>)}
  </section>}/>
  <section><h2>Prepare selected sources</h2><p>At most 10 papers. Preparation checks identity and permissions; unavailable full text may use an explicitly labeled abstract fallback.</p><Failure message={error}/>
    {changed&&workspace.current_preparation_id&&<Notice>Selection changed; current passages still use the previous prepared sources.</Notice>}
    <div className="actions"><button className="primary" disabled={!selection.ready||selected.length===0||busy} onClick={()=>void prepare()}>{busy?"Preparing sources…":"Prepare selected sources"}</button>{preparation&&<button disabled={busy} onClick={()=>void prepare(true)}>Explicitly refresh sources</button>}</div>
    {preparation&&<><p className="meta">PREPARATION {preparation.id} · SOURCE REVISION {preparation.source_revision}</p>{preparation.sources.map(source=><article className="source" key={source.id}><h3>{search.papers.find(item=>item.id===source.paper_id)?.title??source.paper_id}</h3><SourceMetadata source={source}/></article>)}
      <button className="primary" onClick={()=>void navigate({page:"evidence",workspace:workspace.id})}>Continue to passage search</button></>}
  </section></>;
}
