"use client";
import {useEffect,useRef,useState} from "react";
import {api,APIError,type Schema} from "../lib/api";
import {flushDrafts} from "../lib/drafts";
import {readRuntimeSettings,type RuntimeSettings} from "../lib/runtime-settings";
import {readDesktopOnboarding,saveDesktopOnboarding,loadOnboardingExample,type DesktopOnboarding,type SetupGuideStep} from "../lib/desktop-onboarding";
import ResearchSettings from "./research-settings";
import {Failure,Notice} from "./ui";

const labels:Record<SetupGuideStep,string>={welcome:"Welcome",sources:"Research sources",retrieval:"Evidence retrieval",ai:"AI assistance",ready:"Observed setup summary"};
const nextStep={sources:"retrieval",retrieval:"ai",ai:"ready"} as const;
type PackObservation={label:string;state:string;installed:boolean;dependencies?:{state:string};runtime?:{device?:string;encoder_executed?:boolean;reranker_executed?:boolean}|null};

function connectionLabel(status:RuntimeSettings["status"]["pubmed"],enabled:boolean) {
  if(!enabled)return "Disabled";
  if(status.state.toLowerCase()==="failed")return "Failed";
  return status.tested_at&&status.state==="Last test succeeded"?"Ready":"Setup required";
}
function packObservation(pack:PackObservation,selectedDevice:string|null) {
  if(["failed","runtime_failed","corrupt_or_missing","interrupted"].includes(pack.state))return {state:"Failed",detail:"The last operation did not establish a usable runtime. Retry explicitly in Evidence retrieval."};
  if(!pack.installed)return {state:"Setup required",detail:"Optional model files are not installed. Core does not need them."};
  if(pack.dependencies?.state!=="available")return {state:"Setup required",detail:"Model files are installed; the required optional libraries are not established."};
  if(pack.state==="runtime_passed"&&pack.runtime?.encoder_executed&&pack.runtime?.reranker_executed){
    if(selectedDevice&&pack.runtime.device===selectedDevice)return {state:"Runtime checked",detail:`Encoder and reranker execution was recorded on ${selectedDevice.toUpperCase()}. This does not establish scientific quality.`};
    return {state:"Installed",detail:`Historical runtime check${pack.runtime.device?" on "+pack.runtime.device.toUpperCase():""}; execution for ${selectedDevice?"the selected "+selectedDevice.toUpperCase():"the current selected device"} is not established.`};
  }
  return {state:"Installed",detail:"Model files and libraries are present; current runtime execution is not established."};
}

/** Metadata/recorded-status reads only; never checks a provider or model runtime. */
export function ObservedSetupSummary() {
  const [settings,setSettings]=useState<RuntimeSettings|null>(null),[packs,setPacks]=useState<PackObservation[]|null>(null),[connection,setConnection]=useState<boolean|null>(null),[issues,setIssues]=useState<string[]>([]),[attempt,setAttempt]=useState(0);
  useEffect(()=>{let active=true;setIssues([]);setSettings(null);setPacks(null);setConnection(null);
    Promise.allSettled([readRuntimeSettings(),api<{packs:PackObservation[]}>("settings/retrieval"),api<Schema<"Capabilities">>("capabilities")]).then(results=>{
      if(!active)return;
      const [configuration,retrieval,capabilities]=results;
      if(configuration.status==="fulfilled")setSettings(configuration.value);
      if(retrieval.status==="fulfilled")setPacks(retrieval.value.packs);
      setConnection(capabilities.status==="fulfilled");
      setIssues([...(configuration.status==="rejected"?["Settings status could not be read."]:[]),...(retrieval.status==="rejected"?["Optional pack status could not be read."]:[]),...(capabilities.status==="rejected"?["The latest capability status could not be read."]:[])]);
    });return()=>{active=false;};
  },[attempt]);
  return <section aria-label="Observed setup status"><h2>Core research does not need a model</h2>
    {connection===true?<p role="status"><strong>Ready for manual work:</strong> local capabilities responded. You can continue without optional models. Choose Core explicitly for a new task if a selected optional profile is unavailable; existing boards keep their pinned profile.</p>:<p role="status">{connection===null?"Reading local connection status…":"Connection status unavailable. Core does not depend on optional setup; return to your workspace to retry the connection."}</p>}
    <p className="notice">Finishing this welcome flow records setup progress. It does not certify an optional provider, model, source index or scientific result.</p>
    {!!issues.length&&<><Notice>{issues.join(" ")} No optional action was retried.</Notice><button onClick={()=>setAttempt(value=>value+1)}>Read setup status again</button></>}
    <h3>Research sources</h3>{settings?<p role="status"><strong>{connectionLabel(settings.status.pubmed,settings.preferences.pubmed.enabled)}:</strong> {settings.preferences.pubmed.enabled?settings.status.pubmed.tested_at?settings.status.pubmed.message:"Connection not checked. A saved contact is not a successful provider test.":"PubMed is optional; use imports or the saved example without it."}</p>:<p role="status">Source connection status not yet available.</p>}
    <h3>Evidence retrieval</h3><p>Core lexical requires no neural download. Runtime execution and source indexing are separate.</p>{packs?.map((pack,index)=>{const observed=packObservation(pack,settings?(settings.preferences.retrieval?.device??"cpu"):null);return <p key={index} role="status"><strong>{pack.label} · {observed.state}:</strong> {observed.detail} <strong>Sources need indexing before first neural retrieval;</strong> existing index status is checked in the originating task. Setup did not create or refit an index.</p>;})}{!packs&&<p role="status">Optional model-pack status not yet available.</p>}
    <h3>AI assistance</h3>{settings?<><p role="status"><strong>{connectionLabel(settings.status.ai,settings.preferences.ai.provider!=="none")}:</strong> {settings.preferences.ai.provider==="none"?"No generation selected.":settings.status.ai.tested_at?settings.status.ai.message:"Model compatibility has not been checked. Entered settings or a present key do not establish a working model."}</p><p className="muted">Generation still requires its own explicit data/cost consent.</p></>:<p role="status">Generation status not yet available. Manual work needs no LLM.</p>}
    <p className="muted">No provider connection, model download, runtime execution, indexing or preparation was started by this summary.</p>
  </section>;
}

type Props={returnLabel?:string;progress:DesktopOnboarding;step:SetupGuideStep;capabilities:Schema<"Capabilities">;onProgress:(value:DesktopOnboarding)=>void;onStep:(step:SetupGuideStep)=>Promise<void>;onReturn:()=>Promise<void>;onExample:(workspace:Schema<"WorkspaceSummary">,search:Schema<"SearchPreview">)=>Promise<void>};
export default function DesktopSetup({progress,step,capabilities,onProgress,onStep,onReturn,onExample,returnLabel="Open workspaces"}:Props) {
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[conflict,setConflict]=useState(false);
  const heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{heading.current?.focus({preventScroll:true});heading.current?.scrollIntoView({block:"start",behavior:"instant"});},[step]);
  async function perform(action:()=>Promise<void>){if(busy)return;setBusy(true);setError("");try{await flushDrafts();await action();}catch(failure){setError((failure as Error).message);setConflict(failure instanceof APIError&&failure.status===409);}finally{setBusy(false);}}
  async function advance(destination:SetupGuideStep,complete=false){await perform(async()=>{const saved=await saveDesktopOnboarding(progress,destination,complete||progress.completed);onProgress(saved);await onStep(destination);});}
  async function inspectProgress(){setBusy(true);setError("");try{const latest=await readDesktopOnboarding();onProgress(latest);setConflict(false);}catch(failure){setError((failure as Error).message);}finally{setBusy(false);}}
  async function example(){await perform(async()=>{const result=await loadOnboardingExample(capabilities,progress);onProgress(result.progress);await onExample(result.workspace,result.search);});}
  async function finish(){await perform(async()=>{const saved=await saveDesktopOnboarding(progress,"ready",true);onProgress(saved);await onReturn();});}
  async function leave(){await perform(onReturn);}
  const optional=step==="sources"||step==="retrieval"||step==="ai";
  return <div className="desktop-setup" aria-label="Desktop welcome and setup"><p className="eyebrow">LOCAL DESKTOP · OPTIONAL SETUP</p><h1 ref={heading} tabIndex={-1}>{step==="welcome"?"Welcome to Literature Review Engine":labels[step]}</h1>
    <p className="intro">Start with a source-linked comparison. Core manual research works without an AI key or model download.</p>
    <nav className="setup-step-navigation" aria-label="Setup steps">{(Object.keys(labels) as SetupGuideStep[]).map(value=><button key={value} disabled={busy||conflict} aria-current={step===value?"step":undefined} onClick={()=>void advance(value)}>{labels[value]}</button>)}</nav>
    <Failure message={error}/>{conflict&&<Notice>Setup progress changed in another window. Your research and unsaved settings remain here. Inspect the latest progress before continuing. <button disabled={busy} onClick={()=>void inspectProgress()}>Inspect latest setup progress</button></Notice>}
    {step==="welcome"&&<section><h2>How would you like to start?</h2><div className="setup-choices"><div><h3>Try the saved example</h3><p>Open thirty saved public papers and their saved map in a separate example workspace. Nothing is prepared or reviewed automatically; no live search, model or provider call runs.</p><button className="primary" disabled={busy||conflict} onClick={()=>void example()}>{busy?"Opening…":"Try the saved example"}</button></div><div><h3>Set up my research workspace</h3><p>Review paper connections, optional retrieval and optional AI one step at a time. Save only the settings you choose; every optional step can wait.</p><button disabled={busy||conflict} onClick={()=>void advance("sources")}>Set up my research workspace</button></div></div></section>}
    {optional&&<ResearchSettings key={step} section={step} onReturn={leave} guided={{section:step,pending:busy||conflict,continueLabel:"Continue to "+labels[nextStep[step]].toLowerCase(),onContinue:()=>advance(nextStep[step]),onSkip:()=>advance(nextStep[step])}}/>}
    {step==="ready"&&<><ObservedSetupSummary/><p className="muted">{returnLabel==="Open workspaces"?"Next, create a research workspace or reopen an existing one. No personal workspace is created by saving setup.":"Return to the exact research task you left. Its drafts and source bindings are retained."}</p><div className="actions"><button className="primary" disabled={busy||conflict} onClick={()=>void finish()}>{returnLabel}</button></div></>}
    {!optional&&<div className="actions"><button disabled={busy} onClick={()=>void leave()}>Back to research</button></div>}
  </div>;
}
