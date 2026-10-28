"use client";
import {useEffect,useLayoutEffect,useRef,useState} from "react";
import {api,requestId,acknowledgeRequest,workspacePath,type Schema} from "../lib/api";
import {canonical} from "../lib/helpers";
import {DraftStatus,useDraft,registerUnloadGuard} from "../lib/drafts";
import {investigationMatches} from "../lib/investigations";
import {IntentPlanEditor} from "./search-planner";
import {ExternalLink,Failure,Notice,Time} from "./ui";

type View=Schema<"InvestigationView">;
type Origin=View["origin"];
type Plan=Schema<"SearchPlanView">["revision"]["draft"];
type Candidate=Schema<"CompiledSearchCandidate">;
export type InvestigationContext={board_id:string;expected_board_revision_id:string;paper_id:string;field_id:string;expected_cell_head_id:string|null;expected_draft_version:number;local_draft:Schema<"BoardCellData">|null};
const words=(value:string)=>value.replaceAll("_"," ");
const unsavedReasons=new Map<string,string>(); // Memory only; no private text in browser storage.

/** The original editor stays mounted. This panel only mutates investigation records. */
export default function InvestigationNavigator({workspaceId,context,canCreate,onReturn}:{workspaceId:string;context:InvestigationContext;canCreate:boolean;onReturn:(origin?:Origin)=>Promise<void>}){
  const base=workspacePath(workspaceId)+"/investigations";
  const [listing,setListing]=useState<Origin[]|null>(null),[view,setView]=useState<View|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const alive=useRef(true),pending=useRef(false),heading=useRef<HTMLHeadingElement>(null);
  const reasonKey=canonical([workspaceId,context.board_id,context.expected_board_revision_id,context.paper_id,context.field_id]);
  const [reason,setReason]=useState(()=>unsavedReasons.get(reasonKey)??"");
  const reasonRef=useRef(reason);reasonRef.current=reason;
  useEffect(()=>registerUnloadGuard(()=>!!reasonRef.current.trim()),[]);
  function changeReason(value:string){setReason(value);unsavedReasons.set(reasonKey,value);}
  useLayoutEffect(()=>{heading.current?.focus({preventScroll:true});heading.current?.scrollIntoView({block:"start",behavior:"instant"});},[]);
  useEffect(()=>{alive.current=true;const query=new URLSearchParams({board_id:context.board_id,paper_id:context.paper_id,field_id:context.field_id});
    void api<Schema<"InvestigationListing">>(base+"?"+query).then(result=>{if(alive.current)setListing(result.investigations);}).catch(error=>{if(alive.current)setError(error.message);});
    return()=>{alive.current=false;};
  },[base,context.board_id,context.paper_id,context.field_id]);
  function validate(next:View){if(!investigationMatches(next,workspaceId,context.board_id,context.paper_id,context.field_id))throw new Error("The investigation does not belong to this original workspace and cell. Your comparison remains unchanged.");return next;}
  async function action(work:()=>Promise<void>){if(pending.current)return;pending.current=true;setBusy(true);setError("");try{await work();}catch(error){if(alive.current)setError((error as Error).message);}finally{pending.current=false;if(alive.current)setBusy(false);}}
  async function create(){return action(async()=>{if(!canCreate||!reason.trim())return;const payload={...context,reason},scope=base+":create:"+context.paper_id+":"+context.field_id;
    const result=validate(await api<View>(base,"POST",{...payload,request_id:await requestId(scope,payload)}));
    if(result.origin.board.revision_id!==context.expected_board_revision_id)throw new Error("The captured investigation returned a different board revision.");
    acknowledgeRequest(scope);if(!alive.current)return;changeReason("");setView(result);setListing(previous=>[result.origin,...(previous??[]).filter(item=>item.id!==result.origin.id)]);
  });}
  async function open(id:string){return action(async()=>{const result=validate(await api<View>(base+"/"+encodeURIComponent(id)));if(alive.current)setView(result);});}
  return <section className="investigation-navigator" aria-label="Evidence Gap Navigator"><div className="actions">{!view&&<button disabled={busy} onClick={()=>void action(async()=>{await onReturn();})}>Return to original cell</button>}</div>
    <h2 ref={heading} tabIndex={-1}>Investigate related literature</h2><p>An unresolved cell is a reason to investigate, not proof of a research gap. A new paper cannot supply missing facts about this original paper.</p><Failure message={error}/>
    {!view?<><h3>Investigation draft</h3><p>The exact original comparison, cell, draft and retained source identities are captured when you create the investigation. Your reason is kept in its history.</p><p className="meta">Reason is unsaved until you create the investigation draft.</p><label>Reason for investigating<textarea rows={3} maxLength={10000} value={reason} disabled={busy} onChange={event=>changeReason(event.target.value)}/></label>
      {!canCreate&&<Notice>This cell is resolved, its definition is historical, or its draft needs attention. Existing investigations remain readable. Reopen the current comparison to start a new investigation.</Notice>}
      <button className="primary" disabled={busy||!canCreate||!reason.trim()} onClick={()=>void create()}>Create investigation draft</button>
      <h3>Saved investigations for this cell</h3>{listing===null?<p role="status">Loading investigation history…</p>:!listing.length?<p className="muted">No investigation has been saved for this cell.</p>:listing.map(item=><article className="history-item" key={item.id}><p>{item.reason}</p><p className="meta"><Time value={item.created_at}/> · Original definition {item.board.revision_id===context.expected_board_revision_id?"currently displayed":"historical"}</p><button disabled={busy} onClick={()=>void open(item.id)}>Reopen investigation</button></article>)}</>:
      <InvestigationEditor key={view.origin.id} initial={view} onReturn={onReturn} onList={()=>setView(null)} validate={validate}/>
    }
  </section>;
}

function InvestigationEditor({initial,onReturn,onList,validate}:{initial:View;onReturn:(origin?:Origin)=>Promise<void>;onList:()=>void;validate:(view:View)=>View}){
  const [view,setView]=useState(initial),[busy,setBusy]=useState(""),[error,setError]=useState(""),[latest,setLatest]=useState<View|null>(null),[audit,setAudit]=useState<Schema<"InvestigationExport">|null>(null);
  const base=workspacePath(view.origin.workspace_id)+"/investigations/"+encodeURIComponent(view.origin.id),alive=useRef(true),pending=useRef(false);
  const durable=useDraft(view.origin.workspace_id,"search-plan-editor:"+view.origin.plan_id,{plan_id:view.origin.plan_id,draft:initial.plan.revision.draft,base_revision_id:initial.plan.revision.revision_id});
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const draft=durable.data.draft,revision=view.plan.revision,dirty=canonical(draft)!==canonical(revision.draft),stale=durable.data.base_revision_id!==revision.revision_id;
  const disabled=!!busy||!durable.ready||durable.state==="conflict"||durable.state==="error";
  async function action(kind:string,work:()=>Promise<void>){if(pending.current)return;pending.current=true;setBusy(kind);setError("");try{await work();}catch(error){
    if(kind==="execute"||kind==="diagnose"){try{const retained=validate(await api<View>(base));if(retained.plan.revision.revision_id===revision.revision_id)install(retained);else if(alive.current)setLatest(retained);}catch{/* An unavailable read never triggers another provider attempt. */}}
    if(alive.current)setError((error as Error).message);
  }finally{pending.current=false;if(alive.current)setBusy("");}}
  function install(next:View){validate(next);if(next.origin.id!==view.origin.id)throw new Error("The response belongs to a different investigation.");if(alive.current){setView(next);setAudit(null);}}
  async function mutate(kind:string,payload:unknown,method="POST",fresh=false){
    const scope=base+":"+kind,result=await api<View>(base+"/"+kind,method,{...payload as object,request_id:await requestId(scope,payload,fresh)});
    validate(result);if(result.origin.id!==view.origin.id)throw new Error("The response belongs to a different investigation.");return result;
  }
  function edit(update:(previous:Plan)=>Plan){durable.setData(previous=>({...previous,draft:update(previous.draft)}));}
  async function save(){return action("save",async()=>{if(stale)throw new Error("Inspect the latest saved plan and explicitly keep your edits against it before saving.");await durable.save();const next=await mutate("plan",{draft,expected_revision_id:revision.revision_id},"PUT");install(next);acknowledgeRequest(base+":plan");durable.setData({plan_id:view.origin.plan_id,draft:next.plan.revision.draft,base_revision_id:next.plan.revision.revision_id});await durable.save();});}
  async function candidateAction(kind:"approve"|"diagnose"|"execute",candidate:Candidate,body:object,fresh=false){return action(kind,async()=>{
    if(dirty||stale)throw new Error("Save and review the current exact query before approving or sending it to PubMed.");
    const payload={expected_revision_id:revision.revision_id,candidate_id:candidate.id,candidate_sha256:candidate.candidate_sha256,...body};
    const next=await mutate(kind,payload,"POST",fresh);if(next.plan.revision.revision_id!==revision.revision_id)throw new Error("The plan changed while this request was running. Inspect its latest saved revision; your local edits are retained.");
    if(kind==="approve"&&!next.plan.approvals.some(item=>item.plan_id===revision.plan_id&&item.revision_id===revision.revision_id&&item.candidate_id===candidate.id&&item.candidate_sha256===candidate.candidate_sha256))throw new Error("The approval does not bind this exact query revision.");
    if(kind==="diagnose"&&!next.plan.diagnostics.some(item=>item.revision_id===revision.revision_id&&item.candidate_id===candidate.id&&item.candidate_sha256===candidate.candidate_sha256&&item.receipt.query===candidate.query&&item.receipt.date_from===candidate.date_from&&item.receipt.date_to===candidate.date_to&&item.receipt.sort===candidate.sort))throw new Error("The diagnostic does not bind this exact query and filters.");
    if(kind==="execute"&&!next.executions.some(run=>run.execution.revision_id===revision.revision_id&&run.execution.candidate_id===candidate.id&&run.execution.candidate_sha256===candidate.candidate_sha256&&run.execution.approval_id===(body as {approval_id:string}).approval_id&&run.execution.search_id===run.search.id&&run.search.query===candidate.query&&run.search.date_from===candidate.date_from&&run.search.date_to===candidate.date_to&&run.search.sort===candidate.sort))throw new Error("The saved execution does not bind this exact approved query and filters.");
    install(next);acknowledgeRequest(base+":"+kind);
  });}
  async function decision(candidate:View["executions"][number]["candidates"][number],value:"unassessed"|"shortlist"|"dismiss"){return action("decision",async()=>{install(await mutate("decisions",{candidate_id:candidate.id,expected_version:candidate.decision_version,decision:value,note:""}));acknowledgeRequest(base+":decisions");});}
  async function leave(callback:()=>void|Promise<void>){return action("return",async()=>{await durable.save();await callback();});}
  const field=view.origin.board.fields.find(item=>item.id===view.origin.field_id),paper=view.origin.board.papers.find(item=>item.id===view.origin.paper_id);
  return <><p className="eyebrow">INVESTIGATION · SAVED LOCALLY</p><h3>{field?.label} · {paper?.title}</h3><p>{view.origin.reason}</p><p className="muted">Field question: {field?.subquestion}</p><div className="actions"><button disabled={!!busy} onClick={()=>void leave(()=>onReturn(view.origin))}>Return to original cell</button><button disabled={!!busy} onClick={()=>void leave(onList)}>All investigations for this cell</button></div>
    <details><summary>Captured original cell and source identities</summary><p>Saved cell and saved draft are retained separately from the editor snapshot captured at creation. “Not found in inspected material” does not establish whole-paper absence.</p><pre tabIndex={0}>{JSON.stringify(view.origin,null,2)}</pre></details>
    <Failure message={error}/><DraftStatus draft={durable}/>{error&&<p className="muted">Your plan edits remain here. A failed or interrupted request is never automatically repeated.</p>}
    <h3>Edit the follow-up search plan</h3><p>Existing approved concepts may prefill this plan. The field question provides context; it is not automatically added as a scientific restriction. No model generates terms.</p>
    <IntentPlanEditor draft={draft} onEdit={edit} limits={view.capabilities.limits} disabled={disabled}/>
    <div className="actions"><button className="primary" disabled={disabled||!dirty||stale} onClick={()=>void save()}>{busy==="save"?"Saving and compiling…":"Save revised investigation plan"}</button><button disabled={!!busy} onClick={()=>void action("inspect",async()=>{const next=validate(await api<View>(base));if(alive.current)setLatest(next);})}>Inspect latest investigation</button></div>
    {(dirty||stale)&&<Notice>Your edited plan needs a new saved revision and approval. Previous approval cannot execute these edits.</Notice>}
    {latest&&<aside aria-label="Latest investigation inspection"><h3>Latest saved plan · revision {latest.plan.revision.revision}</h3><pre tabIndex={0}>{JSON.stringify(latest.plan.revision,null,2)}</pre><div className="actions"><button disabled={!!busy} onClick={()=>{install(latest);durable.setData({plan_id:view.origin.plan_id,draft,base_revision_id:latest.plan.revision.revision_id});setLatest(null);}}>Keep my edits against this inspected revision</button><button disabled={!!busy} onClick={()=>{install(latest);durable.setData({plan_id:view.origin.plan_id,draft:latest.plan.revision.draft,base_revision_id:latest.plan.revision.revision_id});setLatest(null);}}>Use this saved plan instead</button></div></aside>}
    <h3>Review the exact executable query</h3><p className="meta">SAVED PLAN REVISION {revision.revision}</p>{revision.compiled.issues.map((issue,index)=><p key={index} className={issue.severity==="error"?"notice error":"muted"}>{issue.message}</p>)}
    {revision.compiled.candidates.map(candidate=><QueryReview key={revision.revision_id+":"+candidate.candidate_sha256} candidate={candidate} view={view} disabled={disabled||dirty||stale} onAction={(kind,body,fresh)=>candidateAction(kind,candidate,body,fresh)} onEdit={()=>edit(previous=>({...previous,input_mode:"manual_strategy",manual_strategy:candidate.query}))}/>)}
    <h3>Candidate records · manual decisions</h3><p>Search matches and retrieval scores do not establish relevance, eligibility or support. Shortlisted candidates stay in this investigation; they are not added to the comparison or prepared as sources.</p>
    {!view.executions.length?<p className="muted">No saved provider execution yet.</p>:view.executions.map(run=><section key={run.execution.id} aria-label="Saved investigation results"><p className="meta">{run.candidates.length} candidate records · <Time value={run.search.searched_at}/></p><details><summary>Exact executed query and receipt</summary><pre tabIndex={0}>{JSON.stringify({execution:run.execution,query:run.search.query,translation:run.search.query_translation},null,2)}</pre></details>
      {run.candidates.map(candidate=><article className="history-item" key={candidate.id}><h4>{candidate.paper.title}</h4><p className="meta">{candidate.paper.authors.join(", ")} · {candidate.paper.year??"Year unavailable"} · PMID {candidate.paper.pmid??"unavailable"}</p>{candidate.paper.url&&<ExternalLink href={candidate.paper.url}>Open candidate record</ExternalLink>}<details><summary>Candidate abstract</summary><p className="preserve">{candidate.paper.abstract||"No abstract returned."}</p></details><p role="status">Decision: {words(candidate.decision)} · version {candidate.decision_version}</p><div className="actions">{([['shortlist','Shortlist'],['dismiss','Dismiss'],['unassessed','Leave unassessed']] as const).map(([value,label])=><button key={value} disabled={!!busy||candidate.decision_version>0&&candidate.decision===value} aria-pressed={candidate.decision===value} onClick={()=>void decision(candidate,value)}>{label}</button>)}</div></article>)}
    </section>)}
    <details><summary>Append-only investigation history</summary><p>Plan revision identities, current-revision approvals, saved executions and manual decisions remain distinct. The audit export contains every retained plan revision and receipt.</p><pre tabIndex={0}>{JSON.stringify({revisions:view.plan.revisions,approvals:view.plan.approvals,decisions:view.decisions,failures:view.failures},null,2)}</pre></details>
    <h3>Export investigation audit</h3><p className="muted">This private export contains the original cell snapshot, source identities, query approvals, executions and candidate decisions.</p><button disabled={!!busy} onClick={()=>void action("export",async()=>{const value=await api<Schema<"InvestigationExport">>(base+"/export");if(alive.current)setAudit(value);})}>Prepare readable audit export</button>
    {audit&&<><div className="actions"><Download text={audit.markdown_text} name={view.origin.id+"-investigation.md"} type="text/markdown">Download readable audit</Download><Download text={audit.json_text} name={view.origin.id+"-investigation.json"} type="application/json">Download audit JSON</Download></div><details open><summary>Readable audit preview</summary><pre tabIndex={0}>{audit.markdown_text}</pre></details></>}
  </>;
}

function QueryReview({candidate,view,disabled,onAction,onEdit}:{candidate:Candidate;view:View;disabled:boolean;onAction:(kind:"approve"|"diagnose"|"execute",body:object,fresh?:boolean)=>Promise<void>;onEdit:()=>void}){
  const [reviewed,setReviewed]=useState(false),[deferred,setDeferred]=useState<string[]>([]),[split,setSplit]=useState(false),[unparsed,setUnparsed]=useState(false),[maximum,setMaximum]=useState(10);
  const revision=view.plan.revision,capability=view.capabilities,required=[...candidate.deferred_required_ids,...candidate.deferred_excluded_ids];
  const approval=view.plan.approvals.find(item=>item.plan_id===revision.plan_id&&item.revision_id===revision.revision_id&&item.candidate_id===candidate.id&&item.candidate_sha256===candidate.candidate_sha256);
  const accepted=reviewed&&required.every(id=>deferred.includes(id))&&(!candidate.requires_split_approval||split)&&(!candidate.unparsed_constraints.length||unparsed),ready=candidate.status==="ready_for_approval";
  const canRetry=(kind:string)=>view.failures.some(item=>item.operation.startsWith(kind)&&item.status==="failed")&&!view.failures.some(item=>item.operation.startsWith(kind)&&item.status==="pending");
  const diagnostics=view.plan.diagnostics.filter(item=>item.candidate_id===candidate.id&&item.candidate_sha256===candidate.candidate_sha256);
  return <article className="retained-block" aria-label={candidate.label}><h4>{candidate.label}</h4><label>Exact executable PubMed query<textarea readOnly rows={5} value={candidate.query}/></label><p className="meta">Publication dates {candidate.date_from??"unrestricted"} to {candidate.date_to??"unrestricted"} · Sort {words(candidate.sort)}</p><button disabled={disabled} onClick={onEdit}>Edit this exact query</button>
    {candidate.issues.map((issue,index)=><p className={issue.severity==="error"?"notice error":"muted"} key={index}>{issue.message}</p>)}
    {candidate.deferred_constraints.map((message,index)=><p key={index}>{message}</p>)}
    {required.map(id=><label className="check" key={id}><input type="checkbox" disabled={disabled} checked={deferred.includes(id)} onChange={event=>setDeferred(previous=>event.target.checked?[...previous,id]:previous.filter(value=>value!==id))}/>Acknowledge deferred constraint: {view.plan.revision.draft.concepts.find(item=>item.id===id)?.label??id}</label>)}
    {candidate.requires_split_approval&&<label className="check"><input type="checkbox" disabled={disabled} checked={split} onChange={event=>setSplit(event.target.checked)}/>Approve this separate subquestion</label>}
    {!!candidate.unparsed_constraints.length&&<><p>{candidate.unparsed_constraints.join(" ")}</p><label className="check"><input type="checkbox" disabled={disabled} checked={unparsed} onChange={event=>setUnparsed(event.target.checked)}/>Acknowledge that this specialist strategy is unparsed</label></>}
    <label className="check"><input type="checkbox" checked={reviewed} disabled={disabled} onChange={event=>setReviewed(event.target.checked)}/>I reviewed this exact query, dates, sort and stated constraints</label><button disabled={disabled||!ready||!accepted} onClick={()=>onAction("approve",{acknowledged_deferred_concept_ids:deferred,accept_subquestion_split:split,acknowledge_unparsed_strategy:unparsed})}>Approve exact investigation query</button>
    {approval&&<p role="status">Approval saved for this exact query revision.</p>}
    {!capability.execution_enabled&&<Notice>{capability.execution_reason}</Notice>}{!capability.diagnostics_enabled&&<p className="muted">{capability.diagnostics_reason}</p>}
    <p className="muted">These actions send the displayed query and filters to PubMed. Diagnosis is not a relevance assessment.</p><button disabled={disabled||!ready||!approval||!capability.diagnostics_enabled} onClick={()=>onAction("diagnose",{seeds:[],preview_search_id:null})}>Check PubMed matches</button>
    {canRetry("diagnose")&&<button disabled={disabled||!approval||!capability.diagnostics_enabled} onClick={()=>onAction("diagnose",{seeds:[],preview_search_id:null},true)}>Start a new PubMed diagnostic attempt</button>}
    {diagnostics.map(item=><div className="history-item" key={item.receipt.id}><p>Diagnostic: {words(item.receipt.status)} · provider-reported count {item.receipt.reported_count??"unavailable"}</p><p className="preserve">{item.receipt.query_translation??"No provider translation returned."}</p>{item.receipt.messages.map((message,index)=><p key={index}>{message.message}</p>)}<Failure message={item.receipt.error?.message??""}/></div>)}
    <div className="control-row"><label>Maximum candidate records<input type="number" min={1} max={capability.limits.max_discovery_records} disabled={disabled} value={maximum} onChange={event=>setMaximum(Number(event.target.value))}/></label><button className="primary" disabled={disabled||!ready||!approval||!capability.execution_enabled||!Number.isSafeInteger(maximum)||maximum<1||maximum>capability.limits.max_discovery_records} onClick={()=>onAction("execute",{approval_id:approval!.id,max_results:maximum})}>Run approved PubMed search</button>{canRetry("execute")&&<button disabled={disabled||!ready||!approval||!capability.execution_enabled||!Number.isSafeInteger(maximum)||maximum<1||maximum>capability.limits.max_discovery_records} onClick={()=>onAction("execute",{approval_id:approval!.id,max_results:maximum},true)}>Start a new PubMed search attempt</button>}</div>
  </article>;
}

function Download({text,name,type,children}:{text:string;name:string;type:string;children:string}){
  const [url,setUrl]=useState("");useEffect(()=>{const next=URL.createObjectURL(new Blob([text],{type:type+";charset=utf-8"}));setUrl(next);return()=>URL.revokeObjectURL(next);},[text,type]);
  return <a className="button" download={name} href={url||undefined}>{children}</a>;
}
