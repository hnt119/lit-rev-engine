"use client";
import {useEffect,useState,type ReactNode} from "react";
import {flushDrafts} from "../lib/drafts";

type Admission={mode:"local"|"hosted";admitted:boolean;expires_at?:string|null};
export default function AdmissionGate({children}:{children:ReactNode}){
  const [state,setState]=useState<Admission|null>(null),[code,setCode]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const [renew,setRenew]=useState(false);
  async function status(){
    const response=await fetch("/api/v1/admission/status",{credentials:"same-origin",cache:"no-store"});
    if(!response.ok)throw new Error("The hosted workspace is unavailable. Retry when the service is ready.");
    const value=await response.json() as Admission;
    if(value.mode!=="hosted"||typeof value.admitted!=="boolean")throw new Error("The hosted admission boundary is unavailable.");
    setState(value);
  }
  useEffect(()=>{void status().catch(failure=>setError(failure.message));},[]);
  async function login(event:React.FormEvent){
    event.preventDefault();setBusy(true);setError("");
    try{
      const response=await fetch("/api/v1/admission/login",{method:"POST",credentials:"same-origin",cache:"no-store",headers:{"Content-Type":"application/json"},body:JSON.stringify({code})});
      setCode("");
      if(!response.ok)throw new Error(response.status===429?"Too many admission attempts. Wait before trying again.":"Admission was not granted. Check your invitation or retry later.");
      await status();setRenew(false);
    }catch(failure){setError((failure as Error).message);}finally{setBusy(false);}
  }
  async function endAdmission(){
    setBusy(true);setError("");
    try{
      await flushDrafts();
      const response=await fetch("/api/v1/admission/logout",{method:"POST",credentials:"same-origin",cache:"no-store",headers:{"Content-Type":"application/json"},body:"{}"});
      if(!response.ok)throw new Error("Admission could not be ended. Your work remains open.");
      setState({mode:"hosted",admitted:false});setCode("");setRenew(false);
    }catch(failure){setError((failure as Error).message);setRenew(true);}finally{setBusy(false);}
  }
  const admissionForm=<form onSubmit={event=>void login(event)}><label>Invitation code<input type="password" name="invitation" autoComplete="off" maxLength={256} value={code} onChange={event=>setCode(event.target.value)} disabled={busy||!state}/></label><button className="primary" disabled={busy||!state||!code}>{busy?"Checking invitation…":state?.admitted?"Renew beta access":"Open research workspace"}</button></form>;
  if(state?.admitted)return <><aside className="notice" aria-label="Hosted beta access"><p className="meta">INVITE-ONLY BETA · SAME-BROWSER ACCESS</p><p>Admission does not grant access to another researcher’s work. Keep this browser cookie to reopen your work; named accounts, cross-device access and cookie recovery are unavailable. Export your work regularly. If admission expires, renew here before retrying a save.</p><div className="actions"><button disabled={busy} onClick={()=>{setRenew(value=>!value);setError("");}}>Renew beta access</button><button disabled={busy} onClick={()=>void endAdmission()}>End beta admission</button></div>{renew&&admissionForm}<p role="status" aria-live="polite">{error}</p></aside>{children}</>;
  return <main className="app-shell landing"><p className="eyebrow">LITERATURE REVIEW ENGINE · HOSTED BETA</p><h1>Follow the evidence.</h1><p>This private beta requires an invitation. Each browser keeps its own workspace access.</p>
    {admissionForm}
    <p role="status" aria-live="polite">{!state&&!error?"Checking hosted access…":error}</p>{error&&!state&&<button disabled={busy} onClick={()=>{setError("");void status().catch(failure=>setError(failure.message));}}>Retry connection</button>}
    <p className="meta">No named accounts or cross-device recovery. Losing the workspace cookie loses access. An invitation is admission only.</p></main>;
}
