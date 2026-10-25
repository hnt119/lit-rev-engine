"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,requestId,workspacePath,type Schema} from "../lib/api";
import {DraftStatus,navigationBarrier,useDraft} from "../lib/drafts";
import {highlightParts} from "../lib/helpers";
import {matchesPaperOrigin} from "../lib/paper-origin";
import {comparisonPassageParams,comparisonPassageScope,matchesComparisonPassageRun,matchesComparisonPassageSummary,type ComparisonPassageContext,type ComparisonPassageIdentity} from "../lib/comparison-passage";
import {Citation,Failure,Notice,SourceMetadata,Time} from "./ui";
import {HybridPassages} from "./hybrid-passages";
import {readRuntimeSettings} from "../lib/runtime-settings";
import type {LocationState,Navigate} from "./workspace-app";

type EvidenceProps={workspace:Schema<"WorkspaceSummary">;requestedRun?:string;maxPassages?:number;refresh:()=>Promise<void>;navigate:Navigate;comparison?:ComparisonPassageIdentity};
export default function Evidence(props:EvidenceProps) {
  return props.comparison?<ComparisonEvidence {...props} comparison={props.comparison}/>:<EvidenceSearch {...props}/>;
}
function comparisonDestination(workspace:string,context:ComparisonPassageIdentity,page:"compare"|"evidence",extra:Partial<LocationState>={}):LocationState {
  return {page,workspace,board:context.board_id,revision:context.board_revision_id,paper:context.paper_id??undefined,field:context.field_id??undefined,...extra};
}
function ComparisonEvidence(props:EvidenceProps&{comparison:ComparisonPassageIdentity}) {
  const [context,setContext]=useState<ComparisonPassageContext|null>(null),[error,setError]=useState("");
  const identity=JSON.stringify(props.comparison);
  useEffect(()=>{let active=true;setContext(null);setError("");
    void api<ComparisonPassageContext>(workspacePath(props.workspace.id)+"/boards/"+encodeURIComponent(props.comparison.board_id)+"/passage-search-context?"+comparisonPassageParams(props.comparison)).then(value=>{
      if(value.board_id!==props.comparison.board_id||value.board_revision_id!==props.comparison.board_revision_id||(value.paper_id??null)!==(props.comparison.paper_id??null)||(value.field_id??null)!==(props.comparison.field_id??null))throw new Error("The authorized passage context does not match the requested comparison and cell.");
      if(active)setContext(value);
    }).catch(error=>{if(active)setError(error.message);});
    return()=>{active=false;};
  },[props.workspace.id,identity]);
  if(!context)return <><h1>Passage search</h1><Failure message={error}/>{error?<Notice>This comparison context cannot be searched. Its exact source bindings were not replaced with current workspace sources.</Notice>:<p role="status">Checking the comparison’s retained source bindings…</p>}<button onClick={()=>void props.navigate(comparisonDestination(props.workspace.id,props.comparison,"compare",{returnTo:props.comparison.paper_id?"cell":"comparison"}))}>{props.comparison.paper_id?"Back to cell":"Back to comparison"}</button></>;
  return <EvidenceSearch key={comparisonPassageScope(context)} {...props} context={context}/>;
}

type SearchDraft={question:string;top_k:number;selected_run_id?:string|null};
function EvidenceSearch({workspace,requestedRun,refresh,navigate,maxPassages=30,context}:{workspace:Schema<"WorkspaceSummary">;requestedRun?:string;maxPassages?:number;refresh:()=>Promise<void>;navigate:Navigate;context?:ComparisonPassageContext}) {
  const scope=context?comparisonPassageScope(context):"evidence";
  const [retrievalProfile,setRetrievalProfile]=useState(""),[retrievalDevice,setRetrievalDevice]=useState<"cpu"|"mps">("cpu"),[retrievalConfigReady,setRetrievalConfigReady]=useState(false),[retrievalConfigError,setRetrievalConfigError]=useState("");
  useEffect(()=>{let active=true;setRetrievalConfigReady(false);setRetrievalConfigError("");
    const install=(profile:string,device:unknown)=>{if(!["legacy_block_prefix_v1","lexical_spans_v1","hybrid_qwen3_06b_rrf_rerank_v1","hybrid_medcpt_passage_rrf_rerank_v1"].includes(profile))throw new Error("Unsupported pinned retrieval profile.");if(active){setRetrievalProfile(profile);setRetrievalDevice(device==="mps"?"mps":"cpu");setRetrievalConfigReady(true);}};
    const load=context?api<Schema<"BoardView">>(workspacePath(workspace.id)+"/boards/"+encodeURIComponent(context.board_id)+"?revision_id="+encodeURIComponent(context.board_revision_id)).then(value=>install(String(value.definition.retrieval_profile.profile_id??"legacy_block_prefix_v1"),value.definition.retrieval_profile.device)):
      readRuntimeSettings().then(value=>install(value.preferences.retrieval?.profile_id??"legacy_block_prefix_v1",value.preferences.retrieval?.device??"cpu"));
    load.catch(error=>{if(active)setRetrievalConfigError("The retrieval configuration could not be read. No fallback was selected. "+(context?"Return to the comparison and review its profile.":"Choose the next profile explicitly below.")+" "+error.message);});
    return()=>{active=false;};
  },[workspace.id,context?.board_id,context?.board_revision_id]);
  const hybrid=retrievalProfile.startsWith("hybrid_");
  const question=useDraft<SearchDraft>(workspace.id,scope,{question:context?.question??workspace.question,top_k:5,...(context?{selected_run_id:null}:{})});
  const runId=requestedRun??(context?(question.ready?question.data.selected_run_id??undefined:undefined):workspace.current_run_id);
  const [view,setView]=useState<Schema<"RunView">|null>(null);
  const [bibliography,setBibliography]=useState<Schema<"RunPapers">|null>(null);
  const readGeneration=useRef(0);
  const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const destination=(extra:Partial<LocationState>={})=>context?comparisonDestination(workspace.id,context,"evidence",extra):{page:"evidence" as const,workspace:workspace.id,...extra};
  const load=useCallback(async()=>{
    const token=++readGeneration.current;setView(previous=>previous?.run.id===runId?previous:null);setBibliography(previous=>previous?.run_id===runId?previous:null);
    if(!runId)return;
    try{
      const base=workspacePath(workspace.id)+"/runs/"+encodeURIComponent(runId),[result,papers]=await Promise.all([api<Schema<"RunView">>(base),api<Schema<"RunPapers">>(base+"/papers")]);
      if(token!==readGeneration.current)return;
      if(result.run.id!==runId||papers.run_id!==runId||!matchesPaperOrigin(papers.origin,result.run))throw new Error("The bibliography does not match this retained evidence run.");
      if(context&&!matchesComparisonPassageRun(result.run,context))throw new Error("This saved run does not match this comparison, paper scope, field and exact source preparation. Choose a matching run or explicitly retrieve passages.");
      setView(result);setBibliography(papers);setError("");
    }catch(error){if(token===readGeneration.current){setView(null);setBibliography(null);setError((error as Error).message);throw error;}}
  },[workspace.id,runId,context]);
  useEffect(()=>{void load().catch(()=>{});return()=>{readGeneration.current++;};},[load]);
  useEffect(()=>{
    // Back/Forward may choose an older matching run. Retain that validated
    // selection in this scope without replacing the edited next-search query.
    if(context&&requestedRun&&question.ready&&view?.run.id===requestedRun&&question.data.selected_run_id!==requestedRun&&question.state!=="conflict"&&question.state!=="error")
      question.setData(previous=>({...previous,selected_run_id:requestedRun}));
  },[context,question.ready,question.state,question.data.selected_run_id,view?.run.id,requestedRun]);
  const validLimit=Number.isSafeInteger(question.data.top_k)&&question.data.top_k>=5&&question.data.top_k<=maxPassages;
  async function retrieve(fresh=false){setBusy(true);setError("");try{
    if(!retrievalConfigReady)throw new Error("Read or explicitly select the retrieval profile before a run.");
    if(!validLimit)throw new Error(`Choose a whole number from 5 to ${maxPassages} for the next passage search.`);
    let result:Schema<"RunView">["run"]|undefined;
    await navigationBarrier(async()=>{
      await question.save();const payload={question:question.data.question,top_k:question.data.top_k,expected_preparation_id:context?.preparation_id??workspace.current_preparation_id,expected_source_revision:context?.source_revision??workspace.source_revision,...(context?{board_context:{board_id:context.board_id,board_revision_id:context.board_revision_id,paper_id:context.paper_id??null,field_id:context.field_id??null}}:{})};
      result=await api<Schema<"RunView">["run"]>(workspacePath(workspace.id)+"/evidence-runs","POST",{...payload,request_id:await requestId(workspace.id+":"+scope+":retrieve",payload,fresh)});
      if(context){if(!matchesComparisonPassageRun(result,context))throw new Error("The retrieved run does not match this comparison source scope.");question.setData(previous=>({...previous,selected_run_id:result!.id}));await question.save();}
      await refresh();
    });
    await navigate(destination({run:result!.id}));
  }catch(error){setError((error as Error).message);}finally{setBusy(false);}}
  async function chooseRun(id:string){setBusy(true);setError("");try{question.setData(previous=>({...previous,selected_run_id:id||null}));await question.save();await navigate(destination({run:id||undefined}));}catch(error){setError((error as Error).message);}finally{setBusy(false);}}
  const matchingRuns=context?workspace.runs.filter(run=>matchesComparisonPassageSummary(run,context)):[];
  const canSearch=!!(context?.preparation_id??workspace.current_preparation_id);
  return <><h1>Passage search</h1><p>Retrieve exact source passages, inspect their context, and record your own judgments.</p>
    {context&&<section aria-label="Comparison passage search context"><p className="eyebrow">COMPARISON-LINKED PASSAGE SEARCH</p><h2>{context.board_question}</h2><p>{context.paper_id?"Paper scope: "+(context.papers.find(paper=>paper.id===context.paper_id)?.title??context.paper_id):`Paper scope: all ${context.paper_ids.length} reports in this comparison`}</p>{context.field_label&&<p>Field: {context.field_label}</p>}<p className="meta">BOARD REVISION {context.board_revision_id} · PREPARATION {context.preparation_id} · SOURCE REVISION {context.source_revision}</p><p className="muted">The query is prefilled only. Searching starts when you choose Retrieve passages. Results stay restricted to these retained papers and source bindings.</p><button onClick={()=>void navigate(comparisonDestination(workspace.id,context,"compare",{returnTo:context.paper_id?"cell":"comparison"}))}>{context.paper_id?"Back to cell":"Back to comparison"}</button></section>}
    <Failure message={error}/>
    <Failure message={retrievalConfigError}/><label>Evidence retrieval profile<select value={retrievalProfile} disabled={!!context||busy||!retrievalConfigReady&&!retrievalConfigError} onChange={event=>{setRetrievalProfile(event.target.value);setRetrievalConfigReady(true);setRetrievalConfigError("");}}><option value="" disabled>Reading retrieval configuration…</option><option value="legacy_block_prefix_v1">Core lexical — no model download</option>{context&&<option value="lexical_spans_v1">Core lexical spans — pinned board profile for cell candidates</option>}<option value="hybrid_qwen3_06b_rrf_rerank_v1">Qwen hybrid + reranking — experimental</option><option value="hybrid_medcpt_passage_rrf_rerank_v1">Biomedical hybrid + reranking — MedCPT passage adaptation · experimental</option></select></label>{context&&<p className="muted">This comparison definition pins its retrieval profile. Change it through an explicit board definition revision.</p>}
    {!canSearch?<Notice>Prepare selected sources in Discover & explore before retrieving passages. <button onClick={()=>void navigate({page:"discover",workspace:workspace.id})}>Choose sources</button></Notice>:<section><h2>Passage search</h2><DraftStatus draft={question}/><form onSubmit={event=>{event.preventDefault();if(!retrievalConfigReady)setError("Read or explicitly select the retrieval profile before a run.");else if(!hybrid)void retrieve();else setError("Use Retrieve hybrid passages below to run the selected profile after indexing these sources.");}}><label>Evidence question<textarea rows={3} maxLength={10000} disabled={!question.ready} value={question.data.question} onChange={event=>question.setData(previous=>({...previous,question:event.target.value}))}/></label><div className="control-row"><label>Maximum passages for next search<input type="number" min={5} max={maxPassages} step={1} value={question.data.top_k} disabled={!question.ready||busy} onChange={event=>question.setData(previous=>({...previous,top_k:Number(event.target.value)}))}/></label><div className="actions" aria-label="Passage count presets">{[5,10,20,30].filter(count=>count<=maxPassages).map(count=><button key={count} type="button" disabled={!question.ready||busy} aria-pressed={question.data.top_k===count} onClick={()=>question.setData(previous=>({...previous,top_k:count}))}>{count}</button>)}</div></div>{!validLimit&&<p role="status" className="notice">Choose a whole number from 5 to {maxPassages}.</p>}<p className="meta">{hybrid?"SELECTED HYBRID PROFILE · EXPLICIT INDEX REQUIRED":"LEXICAL BM25 + CONTEXT BLOCKS"} · REQUEST UP TO {question.data.top_k} PASSAGES · SOURCE REVISION {context?.source_revision??workspace.source_revision}</p><p className="muted">Fewer matches return fewer passages. This limit changes the next run; saved runs, board candidates and AI context budgets keep their original limits.</p><div className="actions" hidden={hybrid}><button className="primary" disabled={!retrievalConfigReady||!question.ready||busy||!validLimit||!question.data.question.trim()}>{busy?"Retrieving…":"Retrieve passages"}</button>{runId&&<button type="button" disabled={!retrievalConfigReady||busy||!validLimit} onClick={()=>void retrieve(true)}>Explicitly refresh passages</button>}</div></form>
      {hybrid&&<HybridPassages key={retrievalProfile+":"+(context?comparisonPassageScope(context):workspace.current_preparation_id)} workspace={workspace} context={context} profile={retrievalProfile} device={retrievalDevice} question={question.data.question} topK={question.data.top_k} ready={retrievalConfigReady&&question.ready&&validLimit} saveDraft={async()=>{await question.save();}} navigate={navigate}/>}
      {context&&!hybrid&&<label>Matching saved passage run<select disabled={!question.ready||busy} value={runId??""} onChange={event=>void chooseRun(event.target.value)}><option value="">No selected run</option>{runId&&!matchingRuns.some(run=>run.id===runId)&&<option value={runId}>Requested run · checking exact scope</option>}{matchingRuns.map(run=><option key={run.id} value={run.id}>{new Date(run.created_at).toLocaleString()} · {run.passage_count} passages</option>)}</select></label>}
    </section>}
    {view&&bibliography&&view.run.id===runId&&bibliography.run_id===runId&&<EvidenceReview key={view.run.id} workspace={workspace} view={{...view,current:view.current&&view.run.id===workspace.current_run_id}} papers={bibliography.papers} reload={load} refresh={refresh} returnPassage={context?.paper_id&&context.field_id?async passageId=>{await navigate(comparisonDestination(workspace.id,context,"compare",{run:view.run.id,passage:passageId,returnTo:"cell"}));}:undefined}/>}
  </>;
}

type Judgment=Schema<"PassageJudgment">;
type Bundle=Schema<"BundleJudgment">;
type FormDraft={passages:Judgment[];bundle:Bundle;feedback:string;supersedes_id:string|null;editing:boolean};
function initialForm(run:Schema<"RunView">["run"],head:Schema<"Assessment">|null):FormDraft {
  return {passages:head?.passages??run.passages.map(p=>({passage_id:p.id,decision:"unreviewed",notes:""})),bundle:head?.bundle??{status:"not_assessed",reason:"",missing_information:"",supporting_passage_ids:[],contradiction:false},feedback:head?.feedback??"",supersedes_id:head?.id??null,editing:!head};
}
function EvidenceReview({workspace,view,papers,reload,refresh,returnPassage}:{workspace:Schema<"WorkspaceSummary">;view:Schema<"RunView">;papers:Schema<"BoardPaper">[];reload:()=>Promise<void>;refresh:()=>Promise<void>;returnPassage?:(passageId:string)=>Promise<void>}) {
  const run=view.run;
  const draft=useDraft<FormDraft>(workspace.id,"assessment:"+run.id,initialForm(run,view.assessment_head),view.assessment_head?.id??null);
  const [inspected,setInspected]=useState<string|null>(null);const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const [history,setHistory]=useState(view.assessment_history);const [nextHistory,setNextHistory]=useState(view.next_assessment_offset);const [historyBusy,setHistoryBusy]=useState(false);
  const reasonControl=useRef<HTMLTextAreaElement>(null);const missingControl=useRef<HTMLTextAreaElement>(null);
  const assessed=draft.data.bundle.status!=="not_assessed";
  const needsMissing=["partial","insufficient"].includes(draft.data.bundle.status);
  const sufficient=draft.data.bundle.status==="sufficient";
  useEffect(()=>{
    reasonControl.current?.setCustomValidity(assessed&&!draft.data.bundle.reason.trim()?"Enter a reason for an assessed bundle.":"");
    missingControl.current?.setCustomValidity(needsMissing&&!draft.data.bundle.missing_information.trim()?"Describe the missing information for a partial or insufficient bundle.":sufficient&&draft.data.bundle.missing_information.trim()?"A sufficient bundle cannot declare missing information. Clear this field or choose another status.":"");
  },[assessed,needsMissing,sufficient,draft.data.bundle.reason,draft.data.bundle.missing_information]);
  useEffect(()=>{setHistory(view.assessment_history);setNextHistory(view.next_assessment_offset);},[view.assessment_history,view.next_assessment_offset]);
  async function moreHistory(){if(nextHistory===null)return;setHistoryBusy(true);try{const page=await api<Schema<"RunView">>(workspacePath(workspace.id)+"/runs/"+encodeURIComponent(run.id)+"?assessment_offset="+nextHistory+"&assessment_limit=20");setHistory(previous=>[...previous,...page.assessment_history]);setNextHistory(page.next_assessment_offset);}catch(error){setError((error as Error).message);}finally{setHistoryBusy(false);}}
  const editable=view.current&&draft.data.editing;
  function judgment(id:string):Judgment {return draft.data.passages.find(item=>item.passage_id===id)??{passage_id:id,decision:"unreviewed",notes:""};}
  function update(id:string,part:Partial<Judgment>){draft.setData(previous=>({...previous,passages:run.passages.map(p=>p.id===id?{...judgment(p.id),...part}:judgment(p.id))}));}
  function bundle(part:Partial<Bundle>){draft.setData(previous=>({...previous,bundle:{...previous.bundle,...part}}));}
  async function save(){setBusy(true);setError("");try{
    await navigationBarrier(async()=>{
      await draft.save();const payload={run_id:run.id,supersedes_id:draft.data.supersedes_id,passages:run.passages.map(p=>judgment(p.id)),bundle:draft.data.bundle,feedback:draft.data.feedback};
      const assessment=await api<Schema<"Assessment">>(workspacePath(workspace.id)+"/assessments","POST",{...payload,request_id:await requestId(workspace.id+":assessment:"+run.id,payload)});
      draft.replace(initialForm(run,assessment),assessment.id);
      // Do not leave an acknowledged immutable revision paired with an old-head draft.
      await draft.save();await reload();await refresh();
    });
  }catch(error){setError((error as Error).message);}finally{setBusy(false);}}
  return <><section><p className="eyebrow">{view.current?"CURRENT EVIDENCE":"HISTORICAL EVIDENCE · READ ONLY"}</p><h2>{run.question}</h2><p className="meta">{typeof run.parameters.top_k==="number"?`${run.parameters.top_k} requested · `:"Requested count not recorded in this historical run · "}{run.passages.length} returned · {run.matched_passages} matched · {run.indexed_passages} indexed · <Time value={run.created_at}/></p>
    {!view.current&&<Notice>This run uses its original preparation, source versions, and bibliography. It cannot be assessed as current.</Notice>}
    <details><summary>Retrieval method and source binding</summary><pre>{JSON.stringify({run_id:run.id,search_id:run.search_id,...("collection_ref" in run?{collection_ref:run.collection_ref,member_snapshot_sha256:run.member_snapshot_sha256}:{}),preparation_id:run.preparation_id,source_revision:run.source_revision,source_snapshot_sha256:run.source_snapshot_sha256,method:run.method,method_version:run.method_version,parameters:run.parameters},null,2)}</pre></details>
  </section>
  {!run.passages.length?<Notice>No relevant passages matched this question. The engine does not fill an empty result with unrelated source text.</Notice>:<>
    <div className="evidence-headings"><h2>Retrieved passages</h2><div><h2>Record your judgments</h2><DraftStatus draft={draft}/>{view.assessment_head&&(!draft.data.editing||draft.state==="conflict")&&view.current&&<button onClick={()=>draft.replace({...initialForm(run,view.assessment_head),editing:true},view.assessment_head!.id)}>Revise saved assessment</button>}</div></div>
    {run.passages.map(passage=>{const paper=papers.find(item=>item.id===passage.paper_id);const item=judgment(passage.id);return <div className="evidence-pair" key={passage.id}>
      <article className="passage" aria-label={`Passage ${passage.rank}`}><p className="eyebrow">PASSAGE {passage.rank} · {passage.source_type.replaceAll("_"," ")}</p>{paper&&<Citation paper={paper}/>}<blockquote>{passage.anchor.quote}</blockquote><p className="meta">{JSON.stringify(passage.locator)} · VERSION {passage.source_version}</p><button type="button" onClick={()=>{setInspected(passage.id);setTimeout(()=>document.getElementById("source-context")?.scrollIntoView({behavior:"instant",block:"start"}),0);}}>Inspect source for passage {passage.rank} ↓</button>{returnPassage&&<button type="button" onClick={()=>void returnPassage(passage.id)}>Open in comparison cell · passage {passage.rank}</button>}</article>
      <div className="judgment" aria-label={`Judgment for passage ${passage.rank}`}><h3>Passage {passage.rank}</h3><label>Decision · passage {passage.rank}<select disabled={!editable||!draft.ready} value={item.decision} onChange={event=>update(passage.id,{decision:event.target.value as Judgment["decision"]})}><option value="unreviewed">Unreviewed</option><option value="useful">Useful</option><option value="not_useful">Not useful</option><option value="uncertain">Uncertain</option></select></label><label>Notes · passage {passage.rank}<textarea rows={5} maxLength={20000} disabled={!editable||!draft.ready} value={item.notes} onChange={event=>update(passage.id,{notes:event.target.value})}/></label></div>
    </div>;})}
  </>}
  <section className="bundle"><h2>Retrieved bundle judgment</h2><p className="muted">This rates support in these retrieved passages, not whether the whole literature answers your question.</p><Failure message={error}/>
    <form onSubmit={event=>{event.preventDefault();void save();}}><fieldset disabled={!editable||!draft.ready||busy}>
      <label>Bundle status<select value={draft.data.bundle.status} onChange={event=>bundle({status:event.target.value as Bundle["status"]})}><option value="not_assessed">Not assessed</option><option value="sufficient">Sufficient</option><option value="partial">Partial</option><option value="insufficient">Insufficient</option><option value="uncertain">Uncertain</option></select></label>
      <label>Reason{assessed?" · required":" · optional while not assessed"}<textarea ref={reasonControl} required={assessed} rows={3} maxLength={20000} value={draft.data.bundle.reason} onChange={event=>bundle({reason:event.target.value})}/></label><label>Missing information{needsMissing?" · required":""}<textarea ref={missingControl} required={needsMissing} aria-describedby="missing-information-hint" rows={3} maxLength={20000} value={draft.data.bundle.missing_information} onChange={event=>bundle({missing_information:event.target.value})}/></label>
      <p id="missing-information-hint" className="muted">{needsMissing?"Partial and insufficient judgments require a description of what these passages are missing.":sufficient?"A sufficient judgment requires supporting passages and an empty missing-information field.":"Describe any gap in the retrieved passages. Unreviewed and not-assessed values remain neutral."}</p>
      <fieldset className="supports" aria-describedby="supporting-passages-hint"><legend>Supporting passages{sufficient?" · select at least one":""}</legend>{run.passages.map((passage,index)=><label className="check" key={passage.id}><input type="checkbox" required={sufficient&&index===0&&draft.data.bundle.supporting_passage_ids.length===0} checked={draft.data.bundle.supporting_passage_ids?.includes(passage.id)??false} onChange={event=>bundle({supporting_passage_ids:event.target.checked?[...(draft.data.bundle.supporting_passage_ids??[]),passage.id]:(draft.data.bundle.supporting_passage_ids??[]).filter(id=>id!==passage.id)})}/>Passage {passage.rank}</label>)}</fieldset><p id="supporting-passages-hint" className="muted">{sufficient?"Select any passage that supports the sufficient judgment. At least one is required.":"Identify supporting passages where applicable; no support is inferred automatically."}</p>
      <label className="check"><input type="checkbox" checked={draft.data.bundle.contradiction??false} onChange={event=>bundle({contradiction:event.target.checked})}/>Contradiction present in the retrieved evidence</label><label>Workflow feedback<textarea rows={2} maxLength={20000} value={draft.data.feedback} onChange={event=>draft.setData({...draft.data,feedback:event.target.value})}/></label>
      <button className="primary">{busy?"Saving…":draft.data.supersedes_id?"Save revised assessment":"Save assessment"}</button>
    </fieldset></form><p className="meta">SINGLE HUMAN · SELF-DECLARED · NOT INDEPENDENTLY VERIFIED</p>
    {!!history.length&&<details><summary>Immutable assessment history ({history.length} of {view.assessment_total})</summary>{history.map(assessment=><article key={assessment.id}><p>{assessment.bundle.status} · <Time value={assessment.created_at}/></p><p className="meta">{assessment.id} {assessment.supersedes_id&&`· supersedes ${assessment.supersedes_id}`}</p><p className="preserve">{assessment.bundle.reason}</p><details><summary>Complete original assessment record</summary><pre>{JSON.stringify(assessment,null,2)}</pre></details></article>)}{nextHistory!==null&&<button disabled={historyBusy} onClick={()=>void moreHistory()}>{historyBusy?"Loading…":"Load earlier assessments"}</button>}</details>}
  </section>
  <section id="source-context" className="source-context-section"><h2>Verifiable source context</h2><p>Inspecting context does not save a judgment or fetch another source.</p><label>Inspect passage<select value={inspected??""} onChange={event=>setInspected(event.target.value||null)}><option value="">Choose a passage</option>{run.passages.map(passage=><option key={passage.id} value={passage.id}>Passage {passage.rank} · {passage.source_type.replaceAll("_"," ")}</option>)}</select></label>
    {inspected&&<SourceInspector key={run.id+":"+inspected+":"+view.current} workspaceId={workspace.id} runId={run.id} passageId={inspected} archived={!view.current}/>}
  </section></>;
}

function SourceInspector({workspaceId,runId,passageId,archived}:{workspaceId:string;runId:string;passageId:string;archived:boolean}) {
  const [context,setContext]=useState<Schema<"ContextView">|null>(null);const [blocks,setBlocks]=useState<Schema<"Block">[]>([]);const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const endpoint=workspacePath(workspaceId)+"/runs/"+encodeURIComponent(runId)+"/passages/"+encodeURIComponent(passageId)+"/context";
  const load=useCallback(async(offset=0)=>{setBusy(true);setError("");try{const next=await api<Schema<"ContextView">>(endpoint+`?archived=${archived}&offset=${offset}&limit=5`);setContext(next);setBlocks(previous=>offset?[...previous,...next.blocks]:next.blocks);}catch(error){setError((error as Error).message);}finally{setBusy(false);}},[endpoint,archived]);
  useEffect(()=>{void load();},[load]);
  const parts=context?highlightParts(context.block.text,context.passage.anchor.start,context.passage.anchor.end):null;
  return <><Failure message={error}/>{error&&<button disabled={busy} onClick={()=>void load()}>Retry source context</button>}{!context?<p role="status">{busy?"Loading exact source context…":"Source context is not loaded."}</p>:<><p className="eyebrow">{context.archived?"ARCHIVED SOURCE BINDING":"CURRENT SOURCE BINDING"}</p><Citation paper={context.paper}/><p className="meta">{JSON.stringify(context.block.locator)} · HALF-OPEN UNICODE CODE-POINT OFFSETS {context.passage.anchor.start}–{context.passage.anchor.end}</p><div className="source-text">{parts![0]}<mark>{parts![1]}</mark>{parts![2]}</div><SourceMetadata source={context.source}/>
    <details><summary>Retained surrounding blocks · {blocks.length} of {context.total_blocks}</summary>{blocks.map(block=><div className="retained-block" key={block.id}><p className="meta">BLOCK {block.ordinal} · {JSON.stringify(block.locator)}</p><p className="preserve">{block.text}</p></div>)}{context.next_offset!==null&&<button disabled={busy} onClick={()=>void load(context.next_offset!)}>{busy?"Loading…":"Load next 5 blocks"}</button>}</details></>}</>;
}
