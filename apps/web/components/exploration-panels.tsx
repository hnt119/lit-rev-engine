"use client";
import {useId,useLayoutEffect,useRef,useState} from "react";

/** CSS switches visibility on small screens; both children stay mounted. */
export default function ExplorationPanels({map,papers,inspector,revealPaper}:{map:React.ReactNode;papers:React.ReactNode;inspector:React.ReactNode;revealPaper?:{id:string;sequence:number}}) {
  const [active,setActive]=useState<"map"|"papers">("map");
  const [mapRevealRequest,setMapRevealRequest]=useState(0);
  const mapPanel=useRef<HTMLDivElement>(null);
  const paperPanel=useRef<HTMLDivElement>(null);
  const revealedRequest=useRef<typeof revealPaper>(undefined);
  const id=useId();
  useLayoutEffect(()=>{if(revealPaper)setActive("papers");},[revealPaper]);
  useLayoutEffect(()=>{
    if(mapRevealRequest&&active==="map"&&mapPanel.current&&window.matchMedia("(max-width: 900px)").matches)mapPanel.current.scrollIntoView({behavior:"instant",block:"start"});
  },[mapRevealRequest,active]);
  useLayoutEffect(()=>{
    if(!revealPaper||active!=="papers"||revealedRequest.current===revealPaper)return;
    const panel=paperPanel.current;
    const row=Array.from(panel?.querySelectorAll<HTMLElement>("[data-paper-id]")??[]).find(item=>item.dataset.paperId===revealPaper.id);
    if(!panel||!row)return;
    revealedRequest.current=revealPaper;
    row.focus({preventScroll:true});
    if(window.matchMedia("(max-width: 900px)").matches)row.scrollIntoView({behavior:"instant",block:"start"});
    else panel.scrollTo({top:Math.max(0,panel.scrollTop+row.getBoundingClientRect().top-panel.getBoundingClientRect().top-panel.clientTop-(panel.querySelector<HTMLElement>(".exploration-heading-sticky")?.getBoundingClientRect().height??0)-16),behavior:"instant"});
  },[revealPaper,active]);
  return <>
    <div className="exploration-tabs" role="group" aria-label="Mobile exploration view">
      <button type="button" aria-pressed={active==="map"} aria-controls={id+"-map"} onClick={()=>{setActive("map");setMapRevealRequest(previous=>previous+1);}}>Map</button>
      <button type="button" aria-pressed={active==="papers"} aria-controls={id+"-papers"} onClick={()=>setActive("papers")}>Papers</button>
    </div>
    <div className="exploration-layout">
      <div ref={mapPanel} id={id+"-map"} className="exploration-panel" data-exploration-panel="map" data-active={active==="map"} role="region" aria-label="Semantic map panel" tabIndex={0}>{map}</div>
      <div ref={paperPanel} id={id+"-papers"} className="exploration-panel" data-exploration-panel="papers" data-active={active==="papers"} role="region" aria-label="Paper selection panel" tabIndex={0}>{papers}</div>
      {inspector&&<div className="exploration-inspector">{inspector}</div>}
    </div>
  </>;
}
