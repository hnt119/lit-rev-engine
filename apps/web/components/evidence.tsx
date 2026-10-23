"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,requestId,workspacePath,type Schema} from "../lib/api";
import {DraftStatus,navigationBarrier,useDraft} from "../lib/drafts";
import {highlightParts} from "../lib/helpers";
import {matchesPaperOrigin} from "../lib/paper-origin";
import {Citation,Failure,Notice,SourceMetadata,Time} from "./ui";
import type {Navigate} from "./workspace-app";

export default function Evidence({workspace,requestedRun,refresh,navigate,maxPassages=30}:{workspace:Schema<"WorkspaceSummary">;requestedRun?:string;maxPassages?:number;refresh:()=>Promise<void>;navigate:Navigate}) {
  const question=useDraft(workspace.id,"evidence",{question:workspace.question,top_k:5});
  const runId=requestedRun??workspace.current_run_id;
  const [view,setView]=useState<Schema<"RunView">|null>(null);
  const [bibliography,setBibliography]=useState<Schema<"RunPapers">|null>(null);
  const readGeneration=useRef(0);
  const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const load=useCallback(async()=>{
    const token=++readGeneration.current;setView(previous=>previous?.run.id===runId?previous:null);setBibliography(previous=>previous?.run_id===runId?previous:null);
    if(!runId)return;
    try{
      const base=workspacePath(workspace.id)+"/runs/"+encodeURIComponent(runId),[result,papers]=await Promise.all([api<Schema<"RunView">>(base),api<Schema<"RunPapers">>(base+"/papers")]);
      if(token!==readGeneration.current)return;
      if(result.run.id!==runId||papers.run_id!==runId||!matchesPaperOrigin(papers.origin,result.run))throw new Error("The bibliography does not match this retained evidence run.");
      setView(result);setBibliography(papers);setError("");
    }catch(error){if(token===readGeneration.current){setError((error as Error).message);throw error;}}
  },[workspace.id,runId]);
  useEffect(()=>{void load().catch(()=>{});return()=>{readGeneration.current++;};},[load]);
  const validLimit=Number.isSafeInteger(question.data.top_k)&&question.data.top_k>=5&&question.data.top_k<=maxPassages;
  async function retrieve(fresh=false){setBusy(true);setError("");try{
    if(!validLimit)throw new Error(`Choose a whole number from 5 to ${maxPassages} for the next passage search.`);
    await question.save();const payload={question:question.data.question,top_k:question.data.top_k,expected_preparation_id:workspace.current_preparation_id,expected_source_revision:workspace.source_revision};
    const result=await api<Schema<"RunView">["run"]>(workspacePath(workspace.id)+"/evidence-runs","POST",{...payload,request_id:await requestId(workspace.id+":retrieve",payload,fresh)});
    await refresh();await navigate({page:"evidence",workspace:workspace.id,run:result.id});
  }catch(error){setError((error as Error).message);}finally{setBusy(false);}}
  return <><h1>Passage search</h1><p>Retrieve exact source passages, inspect their context, and record your own judgments.</p><Failure message={error}/>
    {!workspace.current_preparation_id?<Notice>Prepare selected sources in Discover & explore before retrieving passages. <button onClick={()=>void navigate({page:"discover",workspace:workspace.id})}>Choose sources</button></Notice>:<section><h2>Passage search</h2><DraftStatus draft={question}/><form onSubmit={event=>{event.preventDefault();void retrieve();}}><label>Evidence question<textarea rows={3} maxLength={10000} disabled={!question.ready} value={question.data.question} onChange={event=>question.setData(previous=>({...previous,question:event.target.value}))}/></label><div className="control-row"><label>Maximum passages for next search<input type="number" min={5} max={maxPassages} step={1} value={question.data.top_k} disabled={!question.ready||busy} onChange={event=>question.setData(previous=>({...previous,top_k:Number(event.target.value)}))}/></label><div className="actions" aria-label="Passage count presets">{[5,10,20,30].filter(count=>count<=maxPassages).map(count=><button key={count} type="button" disabled={!question.ready||busy} aria-pressed={question.data.top_k===count} onClick={()=>question.setData(previous=>({...previous,top_k:count}))}>{count}</button>)}</div></div>{!validLimit&&<p role="status" className="notice">Choose a whole number from 5 to {maxPassages}.</p>}<p className="meta">LEXICAL BM25 + CONTEXT BLOCKS · REQUEST UP TO {question.data.top_k} PASSAGES · SOURCE REVISION {workspace.source_revision}</p><p className="muted">Fewer matches return fewer passages. This limit changes the next run; saved runs, board candidates and AI context budgets keep their original limits.</p><div className="actions"><button className="primary" disabled={!question.ready||busy||!validLimit||!question.data.question.trim()}>{busy?"Retrieving…":"Retrieve passages"}</button>{workspace.current_run_id&&<button type="button" disabled={busy||!validLimit} onClick={()=>void retrieve(true)}>Explicitly refresh passages</button>}</div></form></section>}
    {view&&bibliography&&view.run.id===runId&&bibliography.run_id===runId&&<EvidenceReview key={view.run.id} workspace={workspace} view={{...view,current:view.current&&view.run.id===workspace.current_run_id}} papers={bibliography.papers} reload={load} refresh={refresh}/>}
  </>;
}

type Judgment=Schema<"PassageJudgment">;
type Bundle=Schema<"BundleJudgment">;
type FormDraft={passages:Judgment[];bundle:Bundle;feedback:string;supersedes_id:string|null;editing:boolean};
function initialForm(run:Schema<"RunView">["run"],head:Schema<"Assessment">|null):FormDraft {
  return {passages:head?.passages??run.passages.map(p=>({passage_id:p.id,decision:"unreviewed",notes:""})),bundle:head?.bundle??{status:"not_assessed",reason:"",missing_information:"",supporting_passage_ids:[],contradiction:false},feedback:head?.feedback??"",supersedes_id:head?.id??null,editing:!head};
}
function EvidenceReview({workspace,view,papers,reload,refresh}:{workspace:Schema<"WorkspaceSummary">;view:Schema<"RunView">;papers:Schema<"BoardPaper">[];reload:()=>Promise<void>;refresh:()=>Promise<void>}) {
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
      <article className="passage" aria-label={`Passage ${passage.rank}`}><p className="eyebrow">PASSAGE {passage.rank} · {passage.source_type.replaceAll("_"," ")}</p>{paper&&<Citation paper={paper}/>}<blockquote>{passage.anchor.quote}</blockquote><p className="meta">{JSON.stringify(passage.locator)} · VERSION {passage.source_version}</p><button type="button" onClick={()=>{setInspected(passage.id);setTimeout(()=>document.getElementById("source-context")?.scrollIntoView({behavior:"instant",block:"start"}),0);}}>Inspect source for passage {passage.rank} ↓</button></article>
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
