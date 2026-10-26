"use client";
import {useState,useRef,useLayoutEffect} from "react";
import {Failure} from "./ui";
function textareaValue(raw:string){return raw.replace(/\r\n?/g,"\n");}
function rawOffset(raw:string,domOffset:number){
  let position=0,displayed=0;
  while(position<raw.length&&displayed<domOffset){position+=raw[position]==="\r"&&raw[position+1]==="\n"?2:1;displayed++;}
  return position;
}

/** Native textareas normalize newlines; keep untouched source text byte-exact. */
export function applyRawQueryEdit(raw:string,changedDisplay:string){
  const previous=textareaValue(raw);if(previous===changedDisplay)return raw;
  let start=0,suffix=0;
  while(start<previous.length&&start<changedDisplay.length&&previous[start]===changedDisplay[start])start++;
  while(suffix<previous.length-start&&suffix<changedDisplay.length-start&&previous[previous.length-1-suffix]===changedDisplay[changedDisplay.length-1-suffix])suffix++;
  return raw.slice(0,rawOffset(raw,start))+changedDisplay.slice(start,changedDisplay.length-suffix)+raw.slice(rawOffset(raw,previous.length-suffix));
}

export function pasteRawQuery(raw:string,text:string,start:number,end:number){
  return raw.slice(0,rawOffset(raw,start))+text+raw.slice(rawOffset(raw,end));
}

/** Editing/pasting only changes local state; this field never diagnoses or executes. */
export function RawStrategyEditor({value,onChange,disabled=false,label="Specialist PubMed strategy",maxLength=20000}:{value:string;onChange:(value:string)=>void;disabled?:boolean;label?:string;maxLength?:number}){
  const control=useRef<HTMLTextAreaElement>(null),caret=useRef<number|null>(null);const [error,setError]=useState("");
  useLayoutEffect(()=>{if(caret.current!==null){control.current?.setSelectionRange(caret.current,caret.current);caret.current=null;}},[value]);
  return <><label>{label}<textarea ref={control} rows={7} value={value} disabled={disabled} maxLength={maxLength} spellCheck={false} onChange={event=>{setError("");onChange(applyRawQueryEdit(value,event.target.value));}} onPaste={event=>{
    const text=event.clipboardData.getData("text/plain"),start=event.currentTarget.selectionStart,end=event.currentTarget.selectionEnd,next=pasteRawQuery(value,text,start,end);event.preventDefault();
    if(Array.from(next).length>maxLength){setError(`The pasted strategy exceeds ${maxLength.toLocaleString()} characters. The existing strategy is retained; shorten the input explicitly.`);return;}
    setError("");caret.current=start+textareaValue(text).length;onChange(next);
  }}/></label><Failure message={error}/><p className="muted">The stored strategy is sent unchanged. Concept planning, heuristic suggestions and query diagnostics do not rewrite it.</p></>;
}
