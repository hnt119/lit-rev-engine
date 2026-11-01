"use client";
import {useEffect,useRef,useState} from "react";
import {api} from "../lib/api";
import {Failure,Notice,Time} from "./ui";

export type MapSetup={
  schema_version:string;profile_id:string;model:string;revision:string;ready:boolean;reason:string;
  runtime:{state:string;versions:Record<string,string>;missing:string[];incompatible:string[];message:string;install_hint?:string};
  weights:{state:string;snapshot:string;missing:string[];message?:string;download_bytes?:number};
  configuration:{enabled:boolean;source:string;cache_dir:string};
  computation:{state:string;message:string;tested_at:string|null};
  download:{model:string;revision:string;source:string;destination:string;bytes:number;manifest_sha256:string;supported?:boolean;message?:string;license?:string};
};
const label=(value:string)=>value.replaceAll("_"," ");
export function SemanticMapSetup({revision,disabled,onBusy,onReturn}:{revision:number;disabled:boolean;onBusy:(value:boolean)=>void;onReturn?:()=>Promise<void>}){
  const [value,setValue]=useState<MapSetup|null>(null),[error,setError]=useState(""),[busy,setBusy]=useState(""),[review,setReview]=useState(false),[accepted,setAccepted]=useState(false);
  const alive=useRef(false),acting=useRef(false),read=useRef(0);
  useEffect(()=>{alive.current=true;const token=++read.current;setReview(false);setAccepted(false);api<MapSetup>("settings/maps").then(result=>{if(alive.current&&token===read.current){if(!result.runtime||!result.download)throw new Error("Semantic-map readiness is unavailable from this backend.");setValue(result);setError("");}}).catch(error=>{if(alive.current&&token===read.current)setError(error.message);});return()=>{alive.current=false;read.current++;};},[revision]);
  async function refresh(){const token=++read.current;try{const result=await api<MapSetup>("settings/maps");if(alive.current&&token===read.current){if(!result.runtime||!result.download)throw new Error("Semantic-map readiness is unavailable from this backend.");setValue(result);setError("");}}catch(error){if(alive.current&&token===read.current)setError((error as Error).message);}}
  async function action(kind:"verify"|"install"){
    if(acting.current||disabled||!value)return;acting.current=true;setBusy(kind);onBusy(true);setError("");read.current++;
    try{const result=await api<MapSetup>("settings/maps/"+kind,"POST",{expected_revision:revision,...(kind==="install"?{manifest_sha256:value.download.manifest_sha256,accept_download:true}:{})});if(alive.current){setValue(result);setReview(false);setAccepted(false);}}
    catch(error){if(alive.current){await refresh();if(alive.current)setError((error as Error).message);}}
    finally{acting.current=false;if(alive.current){setBusy("");onBusy(false);}}
  }
  const blocked=disabled||!!busy;
  return <div aria-label="Semantic-map setup"><Failure message={error}/>{disabled&&!busy&&<Notice>Save or discard your settings edits before checking, verifying or downloading. These actions use the saved configuration.</Notice>}
    {!value?<><p role="status">{error?"Readiness could not be read. Research and saved maps remain available.":"Reading local semantic-map prerequisites…"}</p><button type="button" disabled={blocked} onClick={()=>void refresh()}>Refresh map readiness</button></>:<>
      <dl className="map-setup-readiness">
        <dt>Mapping runtime</dt><dd>{label(value.runtime.state)} · {value.runtime.message}</dd>
        <dt>BGE model weights</dt><dd>{label(value.weights.state)}{value.weights.message&&` · ${value.weights.message}`}{value.weights.missing.length>0&&` · ${value.weights.missing.length} required file(s) missing`}</dd>
        <dt>Applied configuration</dt><dd>{value.configuration.enabled?"Enabled":"Disabled"} · {value.configuration.source==="settings"?"Saved session settings":value.configuration.source==="launch_configuration"?"Startup setting":value.configuration.source}</dd>
        <dt>Computation check</dt><dd role="status">{label(value.computation.state)} · {value.computation.message}{value.computation.tested_at&&<> · <Time value={value.computation.tested_at}/></>}</dd>
      </dl>
      <p role="status">{value.reason}</p>
      <p className="muted">Verify readiness explicitly runs BGE on a few built-in synthetic titles and checks the local projection. It sends no papers to a provider and creates no research map. Installed packages and cached weights alone do not prove computation works.</p>
      <div className="actions"><button type="button" disabled={blocked} onClick={()=>void refresh()}>Refresh map readiness</button><button type="button" disabled={blocked||!value.ready} onClick={()=>void action("verify")}>{busy==="verify"?"Verifying BGE and projection…":"Verify readiness · local BGE computation"}</button>{value.weights.missing.length>0&&<button type="button" disabled={blocked||value.download.supported===false} onClick={()=>{setReview(true);setAccepted(false);}}>Review BGE download</button>}</div>
      {value.computation.state==="succeeded"&&onReturn&&<p><button type="button" disabled={blocked} onClick={()=>void onReturn()}>Return to research</button> Your collection is retained; build its map with a separate explicit action.</p>}
      {value.download.supported===false&&<p className="notice">Complete the runtime setup described above before downloading through this application.</p>}
      {busy&&<p role="status">{busy==="install"?"Downloading and verifying the approved BGE files. Keep this section open; an interrupted attempt can be retried explicitly.":"Running the explicit local computation check. The first model load can take a little time."}</p>}
      {review&&<aside className="notice" aria-label="Review BGE download"><h3>Authorize the pinned BGE download</h3><p>Model: <strong>{value.download.model}</strong> · revision <code>{value.download.revision}</code></p><p>Source: <a href={value.download.source} target="_blank" rel="noreferrer">Official BGE files on Hugging Face</a></p><p>Destination: <code>{value.download.destination}</code></p><p>Download size: <strong>{value.download.bytes.toLocaleString()} bytes</strong>. Existing verified files can be reused. No Qwen files or research data are replaced.</p><label className="check"><input type="checkbox" checked={accepted} disabled={blocked} onChange={event=>setAccepted(event.target.checked)}/>I authorize downloading these pinned model files to the displayed local cache.</label><div className="actions"><button type="button" disabled={blocked||!accepted} onClick={()=>void action("install")}>Download approved BGE weights</button><button type="button" disabled={blocked} onClick={()=>{setReview(false);setAccepted(false);}}>Cancel without downloading</button></div></aside>}
      <details><summary>BGE model, cache and runtime details</summary><p>Profile: <code>{value.profile_id}</code> · <code>{value.model}</code> · <code>{value.revision}</code></p><p>Applied cache: <code>{value.configuration.cache_dir}</code></p><p>Pinned snapshot: <code>{value.weights.snapshot}</code></p>{value.runtime.missing.length>0&&<p>Missing runtime packages: {value.runtime.missing.join(", ")}.</p>}{value.runtime.incompatible.length>0&&<p>Incompatible runtime packages: {value.runtime.incompatible.join(", ")}.</p>}<pre>{JSON.stringify(value.runtime.versions,null,2)}</pre>{value.runtime.install_hint&&<p>{value.runtime.install_hint}</p>}<p>Maps use CPU BGE embeddings and the recorded projection, separately from Qwen passage retrieval. Saved coordinates reopen without these optional dependencies. A successful check establishes local execution, not scientific quality.</p></details>
    </>}
  </div>;
}
