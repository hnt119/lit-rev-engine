"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,APIError,workspacePath,type Schema} from "./api";

type Cached={data:Record<string,unknown>;version:number;dirty:boolean;expected:string|null;failure?:Error|null};
const memory=new Map<string,Cached>();
const flushers=new Set<()=>Promise<void>>();
/** Other typed draft scopes share navigation flushing without assessment fields. */
export function registerDraftFlusher(flush:()=>Promise<void>) {
  flushers.add(flush);
  return ()=>{flushers.delete(flush);};
}
const navigationBarriers=new Set<Promise<void>>();
/** An acknowledged assessment and its new draft baseline finish before leaving. */
export async function navigationBarrier(operation:()=>Promise<void>) {
  const task=operation();navigationBarriers.add(task);
  try{await task;}finally{navigationBarriers.delete(task);}
}
export async function flushDrafts(){
  await Promise.all([...navigationBarriers]);
  await Promise.all([...flushers].map(flush=>flush()));
}

/** Server CAS is authoritative. The memory cache retains failed edits during navigation only. */
export function useDraft<T extends Record<string,unknown>>(workspace:string,scope:string,initial:T,expectedHead:string|null=null) {
  const key=workspace+"/"+scope;
  const saved=memory.get(key);
  const [data,setValue]=useState<T>((saved?.data??initial) as T);
  const [version,setVersion]=useState(saved?.version??0);
  const [ready,setReady]=useState(false);
  const [state,setState]=useState<"loading"|"saved"|"unsaved"|"saving"|"error"|"conflict">("loading");
  const [error,setError]=useState("");
  const current=useRef({data:(saved?.data??initial) as T,version:saved?.version??0,dirty:saved?.dirty??false,expected:saved?saved.expected:expectedHead,revision:0,failure:saved?.failure??null as Error|null});
  const inFlight=useRef<Promise<void>|null>(null);
  const alive=useRef(true);
  const endpoint=workspacePath(workspace)+"/drafts/"+encodeURIComponent(scope);
  const remember=useCallback(()=>memory.set(key,{...current.current}),[key]);
  useEffect(()=>{
    alive.current=true;
    api<Schema<"DraftRecord">>(endpoint).then(record=>{
      if(!alive.current)return;
      if(!current.current.dirty) {
        const restored=Object.keys(record.data).length?{...initial,...record.data}:initial;
        current.current={...current.current,data:restored as T,version:record.version,expected:record.version===0?expectedHead:record.expected_assessment_head};
        setValue(restored as T);setVersion(record.version);
        if(record.version!==0&&record.expected_assessment_head!==expectedHead){
          current.current.failure=new APIError(409,"stale_draft_head","This draft belongs to an older assessment head. Explicitly revise the latest saved assessment before saving it.");
          setState("conflict");setError(current.current.failure.message);
        }else setState("saved");
      } else if(current.current.version!==record.version){current.current.failure=new APIError(409,"draft_conflict","A newer draft exists. Your edits are retained; review before retrying.");setState("conflict");setError(current.current.failure.message);}
      else if(current.current.failure){setState(current.current.failure instanceof APIError&&current.current.failure.status===409?"conflict":"error");setError(current.current.failure.message);}
      else setState("unsaved");
      remember();setReady(true);
    }).catch(error=>{if(alive.current){setError(error.message);setState("error");}});
    return()=>{alive.current=false;};
    // This hook is remounted with a stable key for each server draft scope.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[endpoint]);
  const save=useCallback(async()=>{
    if(inFlight.current)return inFlight.current;
    if(current.current.failure)throw current.current.failure;
    if(!current.current.dirty)return;
    const task=(async()=>{
      try {
        while(current.current.dirty){
          const start={...current.current};
          if(alive.current){setState("saving");setError("");}
          const record=await api<Schema<"DraftRecord">>(endpoint,"PUT",{version:start.version,data:start.data,expected_assessment_head:start.expected});
          current.current.version=record.version;
          if(current.current.revision===start.revision)current.current.dirty=false;
          remember();
          if(alive.current){setVersion(record.version);setState(current.current.dirty?"unsaved":"saved");}
        }
      } catch(error) {
        current.current.failure=error as Error;remember();if(alive.current){setError((error as Error).message);setState(error instanceof APIError&&error.status===409?"conflict":"error");}
        throw error;
      } finally {inFlight.current=null;}
    })();inFlight.current=task;await task;
  },[endpoint,remember]);
  useEffect(()=>{flushers.add(save);return()=>{flushers.delete(save);};},[save]);
  useEffect(()=>{
    if(!ready||state!=="unsaved")return;
    const timer=setTimeout(()=>void save().catch(()=>{}),550);return()=>clearTimeout(timer);
  },[data,ready,state,version,save]);
  const setData=useCallback((next:T|((previous:T)=>T))=>{
    const value=typeof next==="function"?next(current.current.data):next;
    current.current={...current.current,data:value,dirty:true,revision:current.current.revision+1};
    remember();setValue(value);if(!current.current.failure){setState("unsaved");setError("");}
  },[remember]);
  const retry=useCallback(async()=>{
    try {
      const record=await api<Schema<"DraftRecord">>(endpoint);
      if(record.expected_assessment_head!==current.current.expected && record.version!==0)
        throw new Error("The saved assessment head changed. Open the latest assessment and explicitly revise it; your edits remain here.");
      current.current.version=record.version;current.current.failure=null;setVersion(record.version);
      if(!ready&&!current.current.dirty){
        const restored=Object.keys(record.data).length?{...initial,...record.data}:initial;
        current.current.data=restored as T;setValue(restored as T);remember();setState("saved");setError("");
      }
      setReady(true);await save();
    }catch(error){setError((error as Error).message);setState("conflict");}
  },[endpoint,save,ready,initial,remember]);
  const replace=useCallback((next:T,head:string|null)=>{
    current.current.expected=head;current.current.failure=null;setData(next);
  },[setData]);
  return {data,setData,ready,state,error,save,retry,replace,version};
}

export function DraftStatus({draft}:{draft:{state:string,error:string,retry:()=>Promise<void>}}) {
  return <div className="draft-status" role="status" aria-live="polite">
    <span>Draft: {draft.state}</span>{draft.error&&<span> · {draft.error}</span>}
    {(draft.state==="error"||draft.state==="conflict")&&<button type="button" onClick={()=>void draft.retry()}>Retry keeping my edits</button>}
  </div>;
}
