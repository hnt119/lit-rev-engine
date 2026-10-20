"use client";
import {useMemo,useRef,useState} from "react";
import {boundedZoom,mapPositions,visiblePoints,type Coordinate} from "../lib/map-view";
import type {Schema} from "../lib/api";

export default function SemanticMap({coordinates,papers,visibleIds,selectedIds,inspectedId,hoveredId,onInspect,onHover}:{coordinates:Record<string,Coordinate>;papers:Schema<"Paper">[];visibleIds:Set<string>;selectedIds:Set<string>;inspectedId:string|null;hoveredId:string|null;onInspect:(id:string)=>void;onHover:(id:string|null)=>void}) {
  const positions=useMemo(()=>mapPositions(coordinates),[coordinates]);
  const points=visiblePoints(positions,visibleIds);
  const [zoom,setZoom]=useState(1);const [pan,setPan]=useState({x:0,y:0});
  const drag=useRef<{x:number;y:number;panX:number;panY:number}|null>(null);
  const hovered=papers.find(p=>p.id===hoveredId);
  const repeated=new Set(Object.values(coordinates).map(value=>JSON.stringify(value))).size<positions.length;
  function move(x:number,y:number){setPan(previous=>({x:previous.x+x,y:previous.y+y}));}
  return <div className="semantic-map">
    <div className="map-controls" aria-label="Map view controls"><button type="button" aria-label="Zoom map in" onClick={()=>setZoom(value=>boundedZoom(value*1.3))}>Zoom in +</button><button type="button" aria-label="Zoom map out" onClick={()=>setZoom(value=>boundedZoom(value/1.3))}>Zoom out −</button><button type="button" onClick={()=>{setPan({x:0,y:0});setZoom(1);}}>Reset map view</button><span className="meta">{Math.round(zoom*100)}%</span></div>
    <svg viewBox="0 0 1000 580" className="map-svg" aria-label="Saved semantic map; use the paper list or focus a point to inspect" role="group"
      onPointerDown={event=>{if((event.target as Element).getAttribute("data-map-point"))return;event.currentTarget.setPointerCapture(event.pointerId);drag.current={x:event.clientX,y:event.clientY,panX:pan.x,panY:pan.y};}}
      onPointerMove={event=>{if(!drag.current)return;const size=event.currentTarget.getBoundingClientRect();setPan({x:drag.current.panX+(event.clientX-drag.current.x)*1000/size.width,y:drag.current.panY+(event.clientY-drag.current.y)*580/size.height});}}
      onPointerUp={event=>{drag.current=null;if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);}}
      onPointerCancel={()=>{drag.current=null;}}>
      <title>Saved paper relationships</title><desc>Points use saved coordinates from one search preview. Filled markers are selected for exploration. Click or press Enter on a point to inspect its paper. Use the paper list as a complete keyboard alternative.</desc>
      <g transform={`translate(${500+pan.x},${290+pan.y}) scale(${zoom}) translate(-500,-290)`}>
        {points.map(point=>{const paper=papers.find(p=>p.id===point.id);if(!paper)return null;return <circle key={point.id} data-map-point={point.id} cx={point.x} cy={point.y} r={hoveredId===point.id||inspectedId===point.id?11:8} role="button" tabIndex={0} aria-label={`Inspect ${paper.title}${!paper.abstract.trim()?"; title-only representation":""}${selectedIds.has(point.id)?"; selected for exploration":""}`} aria-pressed={inspectedId===point.id}
          className={[selectedIds.has(point.id)?"selected":"",hoveredId===point.id?"hovered":"",inspectedId===point.id?"inspected":""].join(" ")}
          onPointerDown={event=>event.stopPropagation()} onClick={()=>onInspect(point.id)} onKeyDown={event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();onInspect(point.id);}}} onMouseEnter={()=>onHover(point.id)} onMouseLeave={()=>onHover(null)} onFocus={()=>onHover(point.id)} onBlur={()=>onHover(null)}><title>{paper.title}{paper.year?` (${paper.year})`:""}</title></circle>;})}
      </g>
      {!points.length&&<text x="500" y="290" textAnchor="middle">No embedded papers match the current filter.</text>}
    </svg>
    {!points.length&&<p className="muted">No embedded papers match this filter. Change or clear the filter to show saved points again.</p>}
    <div className="map-controls pan-controls" aria-label="Pan map with buttons"><span className="meta">PAN</span><button type="button" aria-label="Pan map left" onClick={()=>move(-70,0)}>←</button><button type="button" aria-label="Pan map right" onClick={()=>move(70,0)}>→</button><button type="button" aria-label="Pan map up" onClick={()=>move(0,-70)}>↑</button><button type="button" aria-label="Pan map down" onClick={()=>move(0,70)}>↓</button></div>
    <p className="muted">Click a point to inspect. Drag the background or use the pan buttons. Filled markers indicate source-selection drafts, not formal review inclusion. All actions are also available in the paper list.</p>
    {repeated&&<p className="notice">Some papers share identical saved coordinates. They overlap without added jitter; inspect each from the list.</p>}
    <p className="map-hover" aria-live="polite">{hovered?<><strong>{hovered.title}</strong>{hovered.year?` · ${hovered.year}`:""}{!hovered.abstract.trim()?" · title-only representation":""}<br/><span className="meta">{hovered.authors.join(", ")}</span></>:"Hover or focus a point or paper to highlight the linked record."}</p>
  </div>;
}
