"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,requestId,acknowledgeRequest,type Schema} from "../lib/api";
import {flushDrafts,navigationBarrier} from "../lib/drafts";
import {emptyCell,type useBoardDraft} from "../lib/board-drafts";
import {canonical} from "../lib/helpers";
import {Failure,Notice,Time} from "./ui";
import {SettingsLink} from "../lib/settings-navigation";
import type {GenerationConsent} from "../lib/runtime-settings";
import GenerationReview from "./generation-review";

type View=Schema<"BoardView">;
type Proposal=Schema<"CellProposal">;
type Draft=ReturnType<typeof useBoardDraft>;
type RuntimeProposalCapability=Schema<"ProposalCapability">&{settings_revision?:number|null};
const encoded=encodeURIComponent;

export function ProposalControls({endpoint,view,changed}:{endpoint:string;view:View;changed:()=>void}) {
  const [activated,setActivated]=useState(false);
  const [capability,setCapability]=useState<RuntimeProposalCapability|null>(null);
  const [papers,setPapers]=useState(view.definition.paper_ids.slice(0,3));
  const [fields,setFields]=useState(view.definition.fields.slice(0,3).map(field=>field.id));
  const [runs,setRuns]=useState<Schema<"ProposalListing">["runs"]>([]);
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  const [pendingGeneration,setPendingGeneration]=useState<{consent:GenerationConsent;payload:{expected_revision_id:string;paper_ids:string[];field_ids:string[];settings_revision:number;request_id:string};operation:string}|null>(null);
  const [newAttemptRequired,setNewAttemptRequired]=useState(false);
  const alive=useRef(true),generation=useRef(0);
  const load=useCallback(async()=>{
    const current=++generation.current;
    const [capability,listing]=await Promise.all([
      api<RuntimeProposalCapability>(endpoint+"/proposal-capabilities"),
      api<Schema<"ProposalListing">>(endpoint+"/proposals?revision_id="+encoded(view.definition.revision_id)+"&limit=1")
    ]);
    if(alive.current&&current===generation.current){setCapability(capability);setRuns(listing.runs);}
  },[endpoint,view.definition.revision_id]);
  useEffect(()=>{alive.current=true;if(activated)void load().catch(error=>{if(alive.current)setError(error.message);});return()=>{alive.current=false;generation.current++;};},[load,activated]);
  async function generate(fresh=false){
    setBusy(true);setError("");
    try{
      await flushDrafts();
      if(!alive.current)return;
      const operation=endpoint+":proposals",payload={expected_revision_id:view.definition.revision_id,paper_ids:papers,field_ids:fields,...(capability?.settings_revision!=null?{settings_revision:capability.settings_revision}:{})},request_id=await requestId(operation,payload,fresh);
      setNewAttemptRequired(false);
      if(capability?.settings_revision!=null){const prepared={...payload,settings_revision:capability.settings_revision,request_id};const consent=await api<GenerationConsent>(endpoint+"/prepare-generation","POST",prepared);if(alive.current)setPendingGeneration({consent,payload:prepared,operation});return;}
      await executeGeneration({...payload,request_id},operation);
    }catch(error){if(alive.current)setError((error as Error).message);}finally{if(alive.current)setBusy(false);}
  }
  async function executeGeneration(payload:Record<string,unknown>,operation:string){let run:Schema<"ProposalRun">;try{run=await api<Schema<"ProposalRun">>(endpoint+"/proposal-runs","POST",payload);}catch(error){if(alive.current)setNewAttemptRequired(true);throw error;}if(run.state!=="running")acknowledgeRequest(operation);if(!alive.current)return;if(run.state==="failed")setError(run.failure_message??"The proposal run failed. No suggestions were published.");await load();changed();}
  async function authorizeGeneration(){const pending=pendingGeneration;if(!pending)return;setPendingGeneration(null);setBusy(true);setError("");try{await flushDrafts();await executeGeneration({...pending.payload,consent_id:pending.consent.consent_id},pending.operation);}catch(error){if(alive.current)setError((error as Error).message);}finally{if(alive.current)setBusy(false);}}
  function toggle(values:string[],id:string,checked:boolean){return checked?[...values,id]:values.filter(value=>value!==id);}
  const cells=papers.length*fields.length;
  return <section className="proposal-controls"><details onToggle={event=>{if(event.currentTarget.open)setActivated(true);}}><summary>Optional AI suggestions</summary>
    <p>Propose values from bounded retrieved context, then inspect and review each cell. Generation does not submit values, declare inspection or change human support. Editing selected cells while generation runs can reject publication.</p>
    {String(view.definition.retrieval_profile?.profile_id??"").startsWith("hybrid_")&&<Notice>For every selected report and field, open its cell and choose Find relevant passages first. Proposal preparation reuses the latest saved candidates from this exact definition. It starts no hybrid encoder or reranker work; the existing generation budget stays unchanged.</Notice>}
    <SettingsLink section="ai">Configure optional cell proposals</SettingsLink>
    <Failure message={error}/>
    {pendingGeneration&&<GenerationReview key={pendingGeneration.consent.consent_id} consent={pendingGeneration.consent} busy={busy} onAuthorize={authorizeGeneration} onCancel={()=>setPendingGeneration(null)}/>}
    {newAttemptRequired&&<aside className="notice"><p>The previous AI attempt failed or its result is unknown. Refresh saved proposal status first. It may already have incurred provider charges; no automatic retry is made.</p><button type="button" disabled={busy||!capability?.enabled||view.freshness!=="current"} onClick={()=>generate(true)}>Prepare a new proposal attempt · possible additional charges</button><p className="muted">A new request still needs a separate data/cost authorization for session-configured AI.</p></aside>}
    {!capability?<p role="status">Checking generation configuration…</p>:<>
      <p className="meta">{capability.enabled?"EXPLICIT GENERATION AVAILABLE":"GENERATION DISABLED"} · {capability.reason}</p>
      {capability.model_profile&&<details><summary>Configured model and limits</summary><pre>{JSON.stringify(capability,null,2)}</pre></details>}
      <fieldset disabled={busy||!capability.enabled||view.freshness!=="current"}>
        <legend>Choose reports and fields for this definition</legend>
        <div className="board-workspace-columns"><div>{view.definition.papers.map(paper=><label className="check" key={paper.id}><input type="checkbox" checked={papers.includes(paper.id)} disabled={!papers.includes(paper.id)&&papers.length>=capability.max_papers} onChange={event=>{setPendingGeneration(null);setPapers(values=>toggle(values,paper.id,event.target.checked));}}/>{paper.title}</label>)}</div>
          <div>{view.definition.fields.map(field=><label className="check" key={field.id}><input type="checkbox" checked={fields.includes(field.id)} onChange={event=>{setPendingGeneration(null);setFields(values=>toggle(values,field.id,event.target.checked));}}/>{field.label}</label>)}</div></div>
        <p className="meta">{papers.length} reports × {fields.length} fields = {cells} cells · at most {capability.max_cells} cells / {capability.max_calls} calls · {capability.max_runtime_seconds} seconds · no automatic retries</p>
        <button className="primary" disabled={!cells||cells>capability.max_cells||newAttemptRequired} onClick={()=>generate()}>{busy?"Generating proposals…":"Generate proposals for selected cells"}</button>
      </fieldset>
    </>}
    <button disabled={busy} onClick={()=>void load().then(changed).catch(error=>setError(error.message))}>Refresh proposal status</button>
    <p className="muted">A failed or interrupted run is never automatically repeated. Refresh reads saved status. A new generation requires another explicit action. Proposed text may be incorrect even when its quotation is exact.</p>
    {runs.map(run=><article className="history-item" key={run.id}><p className="meta">{run.state.toUpperCase()} · <Time value={run.created_at}/> · {run.id}</p>{run.failure_message&&<p>{run.failure_message}</p>}<details><summary>Call and usage receipt</summary><pre>{JSON.stringify(run,null,2)}</pre></details></article>)}
    <a className="button" download href={`/api/v1/${endpoint}/proposal-audit?revision_id=${encoded(view.definition.revision_id)}`}>Download separate proposal audit JSON</a>
  </details></section>;
}

export function CellProposals({endpoint,view,paperId,fieldId,draft,editable,refresh,inspect,adopted,busyChanged}:{endpoint:string;view:View;paperId:string;fieldId:string;draft:Draft;editable:boolean;refresh:number;inspect:(proposal:Proposal,reference:Schema<"BoardReference">)=>Promise<void>;adopted:()=>Promise<void>;busyChanged?:(busy:boolean)=>void}) {
  const [activated,setActivated]=useState(false);
  const [listing,setListing]=useState<Schema<"ProposalListing">|null>(null),[error,setError]=useState("");
  const [busy,setBusy]=useState(false),[offset,setOffset]=useState(0);
  const alive=useRef(true),generation=useRef(0);
  const load=useCallback(async()=>{
    const current=++generation.current;
    const value=await api<Schema<"ProposalListing">>(endpoint+"/proposals?"+new URLSearchParams({revision_id:view.definition.revision_id,paper_id:paperId,field_id:fieldId,offset:String(offset),limit:"5"}));
    if(alive.current&&current===generation.current)setListing(value);
  },[endpoint,view.definition.revision_id,paperId,fieldId,offset]);
  useEffect(()=>{alive.current=true;setError("");if(activated)void load().catch(error=>{if(alive.current)setError(error.message);});return()=>{alive.current=false;generation.current++;};},[load,refresh,activated]);
  async function act(operation:()=>Promise<void>){setBusy(true);busyChanged?.(true);setError("");try{await operation();}catch(error){if(alive.current)setError((error as Error).message);}finally{if(alive.current){setBusy(false);busyChanged?.(false);}}}
  const empty=canonical(draft.data)===canonical(emptyCell());
  async function adopt(proposal:Proposal,value:string|null,reason:string,missing:string){await act(()=>navigationBarrier(async()=>{
    await draft.save();const snapshot=draft.snapshot();
    if(canonical(snapshot.data)!==canonical(emptyCell()))throw new Error("Your draft already contains edits. They were preserved; edit the manual draft directly.");
    const payload={expected_revision_id:view.definition.revision_id,draft_version:snapshot.version,expected_cell_head_id:snapshot.expectedHead,value,reason,missing_information:missing};
    const operation=endpoint+":adopt:"+proposal.id;
    await api<Schema<"BoardCellDraft">>(endpoint+"/proposals/"+encoded(proposal.id)+"/adopt","POST",{...payload,request_id:await requestId(operation,payload)});
    acknowledgeRequest(operation);await draft.reload();await adopted();if(alive.current)await load();
  }));}
  async function dismiss(proposal:Proposal,reason:string){await act(async()=>{
    const payload={expected_revision_id:view.definition.revision_id,reason},operation=endpoint+":dismiss:"+proposal.id;
    await api<Proposal>(endpoint+"/proposals/"+encoded(proposal.id)+"/dismiss","POST",{...payload,request_id:await requestId(operation,payload)});
    acknowledgeRequest(operation);if(alive.current)await load();
  });}
  return <section className="cell-proposals" aria-label="AI suggestions for this cell"><details onToggle={event=>{if(event.currentTarget.open)setActivated(true);}}><summary>Optional AI suggestions for this cell</summary><Failure message={error}/>
    {!listing?<p role="status">Loading saved suggestions…</p>:<>{!listing.items.length?<p className="muted">No saved AI suggestions for this cell. The manual workflow remains available.</p>:listing.items.map(proposal=><ProposalCard key={proposal.id} endpoint={endpoint} proposal={proposal} readOnly={view.freshness!=="current"} busy={busy} canAdopt={editable&&empty&&!["error","conflict"].includes(draft.state)} inspect={reference=>act(()=>inspect(proposal,reference))} adopt={adopt} dismiss={dismiss}/>)}
      <p className="meta">{listing.total?offset+1:0}–{offset+listing.items.length} of {listing.total} saved suggestions</p><div className="actions">{offset>0&&<button disabled={busy} onClick={()=>setOffset(Math.max(0,offset-5))}>Newer suggestions</button>}{offset+listing.items.length<listing.total&&<button disabled={busy} onClick={()=>setOffset(offset+5)}>Earlier suggestions</button>}</div>
    </>}
  </details></section>;
}

function ProposalCard({endpoint,proposal,readOnly,busy,canAdopt,inspect,adopt,dismiss}:{endpoint:string;proposal:Proposal;readOnly:boolean;busy:boolean;canAdopt:boolean;inspect:(reference:Schema<"BoardReference">)=>Promise<void>;adopt:(proposal:Proposal,value:string|null,reason:string,missing:string)=>Promise<void>;dismiss:(proposal:Proposal,reason:string)=>Promise<void>}) {
  const [value,setValue]=useState(proposal.value??""),[reason,setReason]=useState(proposal.reason),[missing,setMissing]=useState(proposal.missing_information);
  const [packet,setPacket]=useState<Schema<"ProposalPacket">|Schema<"HybridProposalPacket">|null>(null),[contextError,setContextError]=useState(""),[loadingContext,setLoadingContext]=useState(false);
  const mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  async function loadContext(){setLoadingContext(true);setContextError("");try{
    const run=await api<Schema<"ProposalRun">>(endpoint+"/proposal-runs/"+encoded(proposal.run_id));
    if(mounted.current)setPacket(run.packets.find(packet=>packet.paper_id===proposal.paper_id)??null);
  }catch(error){if(mounted.current)setContextError((error as Error).message);}finally{if(mounted.current)setLoadingContext(false);}}
  const pending=proposal.status==="pending";
  return <article className="proposal-card"><p className="eyebrow">AI suggestion — needs review</p><p className="meta">{proposal.status.toUpperCase()} · HUMAN SUPPORT UNASSESSED · <Time value={proposal.created_at}/></p>
    <p className="muted">Retrieved context only. Exact quotations do not establish support. Null means insufficient retrieved evidence, not absence from the full paper. Editing here is temporary until you use it in a draft.</p>
    <label>Proposed value · editable<textarea rows={3} maxLength={10000} disabled={!pending||readOnly||busy} value={value} onChange={event=>setValue(event.target.value)}/></label>
    <label>Proposal reason · editable<textarea rows={2} maxLength={2000} disabled={!pending||readOnly||busy} value={reason} onChange={event=>setReason(event.target.value)}/></label>
    <label>Proposal missing information · editable<textarea rows={2} maxLength={10000} disabled={!pending||readOnly||busy} value={missing} onChange={event=>setMissing(event.target.value)}/></label>
    {proposal.references.map((reference,index)=><div className="board-reference" key={reference.id}><blockquote>{reference.quote}</blockquote><p className="meta">EXACT QUOTE CHECKED · {reference.start}–{reference.end} · {reference.block_id}</p><button disabled={busy} onClick={()=>inspect(reference)}>Inspect suggestion reference {index+1}</button></div>)}
    {!proposal.references.length&&<p className="muted">No proposed supporting reference.</p>}
    <button disabled={loadingContext} onClick={()=>loadContext()}>Inspect generation context and coverage</button><Failure message={contextError}/>
    {packet&&<details open><summary>Retained input packet · {packet.source_type} · incomplete retrieved context</summary><p className="meta">{packet.evidence_characters} evidence code points · {packet.omitted_evidence} candidate excerpts omitted by packet limits</p>
      {packet.fields.map(field=><p className="meta" key={field.field_id}>{field.label}: {field.evidence_ids.length} supplied excerpts · {"indexed_windows" in field?`${field.candidate_count} hybrid candidates / ${field.indexed_windows} indexed windows · component association is not support`:`${field.matched_blocks} matched / ${field.indexed_blocks} indexed blocks · ${field.omitted_matched_blocks} further matches omitted`} · {field.omitted_evidence} packet omissions</p>)}
      <details><summary>Exact packet and excerpt coverage metadata</summary><pre>{JSON.stringify(packet,null,2)}</pre></details>
    </details>}
    {pending&&!readOnly&&<><div className="actions"><button disabled={busy||!canAdopt||!reason.trim()||(!value.trim()&&!missing.trim())} onClick={()=>adopt(proposal,value.trim()?value:null,reason,missing)}>Use in draft</button><button disabled={busy} onClick={()=>dismiss(proposal,reason)}>Dismiss</button></div>{!canAdopt&&<p className="muted">Use in draft requires an editable, empty draft. Existing values and edits are preserved. You can inspect the suggestion and edit your manual draft directly.</p>}</>}
    {proposal.status==="adopted"&&<Notice>Used in a draft. This does not mean the value was submitted, inspected or human-supported.</Notice>}
    <details><summary>Original suggestion and provenance</summary><pre>{JSON.stringify(proposal,null,2)}</pre></details>
  </article>;
}
