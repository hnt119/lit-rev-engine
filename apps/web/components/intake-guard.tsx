"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {registerDraftFlusher,registerDraftRecovery,registerUnloadGuard} from "../lib/drafts";
import {Notice} from "./ui";

/** Transient inputs must be acknowledged or explicitly reset before unmounting. */
export function useIntakeGuard({dirty,pending,restore,message}:{dirty:()=>boolean;pending?:()=>boolean;restore:()=>void;message:string}){
  const current=useRef({dirty,pending,restore,message});current.current={dirty,pending,restore,message};
  const [error,setError]=useState("");
  const changed=dirty(),running=!!pending?.();
  useEffect(()=>{if(!changed&&!running)setError("");},[changed,running]);
  useEffect(()=>{if(changed||running)return registerUnloadGuard(()=>current.current.dirty()||!!current.current.pending?.());},[changed,running]);
  const check=useCallback(async()=>{
    const value=current.current;
    const message=value.pending?.()?"An intake operation is still running. Wait for its result before leaving or resetting inputs.":value.dirty()?value.message:"";
    if(message){setError(message);throw new Error(message);}setError("");
  },[]);
  const restoreInputs=useCallback(async()=>{
    if(current.current.pending?.())throw new Error("Wait for the intake operation to finish before resetting its inputs.");
    current.current.restore();
    // A confirmed reset is effective before React commits its state updates.
    current.current={...current.current,dirty:()=>false};setError("");
  },[]);
  useEffect(()=>registerDraftFlusher(check),[check]);
  useEffect(()=>registerDraftRecovery({retry:check,restore:restoreInputs}),[check,restoreInputs]);
  async function confirmRestore(){if(window.confirm("Discard the unfinished local intake changes described here? Saved imports and collections remain retained."))await restoreInputs();}
  return {error,confirmRestore,pending:running};
}
export function IntakeGuardNotice({guard}:{guard:ReturnType<typeof useIntakeGuard>}){
  return guard.error?<Notice>{guard.error}<div className="actions"><button type="button" disabled={guard.pending} onClick={guard.confirmRestore}>Discard unfinished intake changes…</button></div></Notice>:null;
}
