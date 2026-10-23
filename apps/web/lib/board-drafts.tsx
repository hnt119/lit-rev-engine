"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,APIError,type Schema} from "./api";
import {registerDraftFlusher,registerDraftRecovery,registerUnloadGuard} from "./drafts";

export type CellData=Schema<"BoardCellData">;
type Record=Schema<"BoardCellDraft">;
type Cached={data:CellData;version:number;expected:string|null;dirty:boolean;edit:number;failure:Error|null};
const memory=new Map<string,Cached>();
export function emptyCell():CellData {return {value:null,references:[],inspected_ranges:[],semantic_assessment:"unassessed",scope_result:"not_assessed",missing_information:"",reason:"",producer:"manual"};}
/** Board-specific CAS never shares assessment head names or storage scopes. */
export function useBoardDraft(endpoint:string,revision:string,head:string|null,readOnly=false) {
  const key=endpoint+"?revision_id="+encodeURIComponent(revision);
  const previous=memory.get(key);
  const current=useRef<Cached>(previous??{data:emptyCell(),version:0,expected:null,dirty:false,edit:0,failure:null});
  const alive=useRef(true),flight=useRef<Promise<void>|null>(null);
  useEffect(()=>readOnly?undefined:registerUnloadGuard(()=>current.current.dirty||!!current.current.failure||!!flight.current),[readOnly]);
  const [data,setValue]=useState(current.current.data),[version,setVersion]=useState(current.current.version);
  const [ready,setReady]=useState(false),[state,setState]=useState("loading"),[error,setError]=useState("");
  const remember=useCallback(()=>memory.set(key,{...current.current}),[key]);
  const fail=useCallback((failure:Error)=>{current.current.failure=failure;remember();if(alive.current){setError(failure.message);setState(failure instanceof APIError&&failure.status===409?"conflict":"error");}},[remember]);
  const adopt=useCallback((record:Record)=>{
    current.current={data:record.data,version:record.version,expected:record.expected_cell_head_id,dirty:false,edit:current.current.edit+1,failure:null};remember();
    if(alive.current){setValue(record.data);setVersion(record.version);setReady(true);setState("saved");setError("");}
  },[remember]);
  useEffect(()=>{
    alive.current=true;
    api<Record>(key).then(record=>{
      if(!alive.current)return;
      if(current.current.dirty){
        if(record.version!==current.current.version)fail(new APIError(409,"board_draft_conflict","A newer cell draft exists. Your edits are retained; explicitly rebase them before saving."));
        else if(current.current.failure)fail(current.current.failure);
        else setState("unsaved");
      }else adopt(record);
      if(!readOnly&&record.version>0&&record.expected_cell_head_id!==head)fail(new APIError(409,"board_cell_head_changed","This draft belongs to an older cell head. Your edits remain available. Explicitly revise or rebase on the latest saved cell."));
      setReady(true);
    }).catch(failure=>fail(failure));
    return()=>{alive.current=false;};
  },[key,adopt,fail,readOnly]);
  const save=useCallback(async()=>{
    if(readOnly)return;
    if(flight.current)return flight.current;
    if(current.current.failure)throw current.current.failure;
    if(!current.current.dirty)return;
    const task=(async()=>{try{
      while(current.current.dirty){
        const start={...current.current};if(alive.current){setState("saving");setError("");}
        const record=await api<Record>(endpoint,"PUT",{expected_revision_id:revision,version:start.version,expected_cell_head_id:start.expected,data:start.data});
        current.current.version=record.version;
        if(current.current.edit===start.edit)current.current.dirty=false;
        remember();if(alive.current){setVersion(record.version);setState(current.current.dirty?"unsaved":"saved");}
      }
    }catch(failure){fail(failure as Error);throw failure;}finally{flight.current=null;}})();flight.current=task;await task;
  },[endpoint,revision,readOnly,remember,fail]);
  useEffect(()=>readOnly?undefined:registerDraftFlusher(save),[save,readOnly]);
  useEffect(()=>{if(!ready||state!=="unsaved"||readOnly)return;const timer=setTimeout(()=>void save().catch(()=>{}),550);return()=>clearTimeout(timer);},[data,version,ready,state,readOnly,save]);
  const setData=useCallback((next:CellData|((old:CellData)=>CellData))=>{
    const value=typeof next==="function"?next(current.current.data):next;
    current.current={...current.current,data:value,dirty:true,edit:current.current.edit+1};remember();setValue(value);if(!current.current.failure){setState("unsaved");setError("");}
  },[remember]);
  const retryOrThrow=useCallback(async()=>{
    try{const record=await api<Record>(key);
      if(!ready&&!current.current.dirty){adopt(record);if(!readOnly&&record.version>0&&record.expected_cell_head_id!==head)throw new APIError(409,"board_cell_head_changed","This draft belongs to an older cell head. Explicitly revise or rebase while retaining these restored edits.");return;}
      if(record.version!==current.current.version||record.expected_cell_head_id!==current.current.expected)throw new APIError(409,"board_draft_conflict","The server draft or saved cell changed. Explicitly rebase retained edits; retry never overwrites another draft.");
      current.current.failure=null;remember();setError("");setReady(true);setState(current.current.dirty?"unsaved":"saved");await save();
    }catch(failure){fail(failure as Error);throw failure;}
  },[key,save,remember,fail,ready,readOnly,head,adopt]);
  const retry=useCallback(async()=>{await retryOrThrow().catch(()=>{});},[retryOrThrow]);
  /** Only an explicit UI revision/rebase action may change the expected cell head. */
  const rebase=useCallback(async(next:CellData,newHead:string|null)=>{
    const record=await api<Record>(key);
    current.current.version=record.version;current.current.expected=newHead;current.current.failure=null;setVersion(record.version);setReady(true);setData(next);setError("");setState("unsaved");
  },[key,setData]);
  const reload=useCallback(async()=>{adopt(await api<Record>(key));},[key,adopt]);
  const restore=useCallback(async()=>{
    const record=await api<Record>(key);
    if(record.version>0&&record.expected_cell_head_id!==head)throw new APIError(409,"board_cell_head_changed","This saved draft belongs to an older cell head. Explicitly revise or rebase it before leaving.");
    adopt(record);
  },[key,head,adopt]);
  useEffect(()=>readOnly?undefined:registerDraftRecovery({retry:retryOrThrow,restore}),[readOnly,retryOrThrow,restore]);
  return {data,setData,ready,state,error,version,save,retry,rebase,reload,snapshot:()=>({version:current.current.version,expectedHead:current.current.expected,data:current.current.data}),expectedHead:current.current.expected};
}
