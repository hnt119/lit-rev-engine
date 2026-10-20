"use client";
import {useId,useState} from "react";

/** CSS switches visibility on small screens; both children stay mounted. */
export default function ExplorationPanels({map,papers,inspector}:{map:React.ReactNode;papers:React.ReactNode;inspector:React.ReactNode}) {
  const [active,setActive]=useState<"map"|"papers">("map");
  const id=useId();
  return <>
    <div className="exploration-tabs" role="group" aria-label="Mobile exploration view">
      <button type="button" aria-pressed={active==="map"} aria-controls={id+"-map"} onClick={()=>setActive("map")}>Map</button>
      <button type="button" aria-pressed={active==="papers"} aria-controls={id+"-papers"} onClick={()=>setActive("papers")}>Papers</button>
    </div>
    <div id={id+"-map"} className="exploration-panel" data-exploration-panel="map" data-active={active==="map"}>{map}</div>
    {inspector}
    <div id={id+"-papers"} className="exploration-panel" data-exploration-panel="papers" data-active={active==="papers"}>{papers}</div>
  </>;
}
