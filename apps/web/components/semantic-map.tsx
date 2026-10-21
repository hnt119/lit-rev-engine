"use client";
import {startTransition,useEffect,useMemo,useRef,useState,type PointerEvent as ReactPointerEvent} from "react";
import {boundedZoom,mapPositions,visiblePoints,type Coordinate} from "../lib/map-view";
import {nearestPaperHit,PAN_THRESHOLD_PX,screenDeltaToMap,type ScreenMatrix} from "../lib/map-interactions";
import type {Schema} from "../lib/api";

type Gesture={pointerId:number;x:number;y:number;panX:number;panY:number;matrix:ScreenMatrix;mode:"paper"|"canvas"|"pan";paperId:string|null;moved:boolean};

export default function SemanticMap({coordinates,papers,visibleIds,selectedIds,inspectedId,hoveredId,onInspect,onHover}:{coordinates:Record<string,Coordinate>;papers:Schema<"Paper">[];visibleIds:Set<string>;selectedIds:Set<string>;inspectedId:string|null;hoveredId:string|null;onInspect:(id:string)=>void;onHover:(id:string|null)=>void}) {
  const positions=useMemo(()=>mapPositions(coordinates),[coordinates]);
  const papersById=useMemo(()=>new Map(papers.map(paper=>[paper.id,paper])),[papers]);
  const points=useMemo(()=>visiblePoints(positions,visibleIds).filter(point=>papersById.has(point.id)),[positions,visibleIds,papersById]);
  const [zoom,setZoom]=useState(1);const [pan,setPan]=useState({x:0,y:0});
  const pointLayer=useRef<SVGGElement>(null);
  const gesture=useRef<Gesture|null>(null);
  const [isPanning,setIsPanning]=useState(false);
  const [pointerHitId,setPointerHitId]=useState<string|null>(null);
  const [pointHoverId,setPointHoverId]=useState<string|null>(null);
  const localHighlight=useRef<string|null>(null);
  const highlightedId=pointHoverId??hoveredId;
  const hovered=highlightedId?papersById.get(highlightedId):undefined;
  const [lastHoveredId,setLastHoveredId]=useState<string|null>(hoveredId);
  // Keep metadata available when keyboard focus leaves a point to scroll it.
  useEffect(()=>{if(hovered)setLastHoveredId(hovered.id);},[hovered]);
  const hoverDetails=hovered??(lastHoveredId?papersById.get(lastHoveredId):undefined);
  const repeated=useMemo(()=>new Set(Object.values(coordinates).map(value=>JSON.stringify(value))).size<positions.length,[coordinates,positions.length]);
  function highlight(id:string|null){
    if(localHighlight.current===id){if(id===null&&hoveredId!==null)onHover(null);return;}
    localHighlight.current=id;
    setPointHoverId(id);
    if(id){
      // Show the local preview first; highlighting the linked list is secondary.
      setLastHoveredId(id);
      startTransition(()=>onHover(id));
    }else{
      // Clear the shared highlight urgently so a pending enter cannot reappear.
      onHover(null);
    }
  }
  function paperAt(clientX:number,clientY:number){
    const matrix=pointLayer.current?.getScreenCTM();
    if(!matrix)return null;
    // getScreenCTM includes SVG letterboxing, responsive CSS sizing, and the
    // current pan/zoom. All overlap decisions use screen distance, not targets.
    return nearestPaperHit(points,{x:clientX,y:clientY},matrix,undefined,point=>{
      const emphasized=highlightedId===point.id||inspectedId===point.id;
      return (emphasized?11:8)+(emphasized?1.5:1);
    });
  }
  function pointerPreview(clientX:number,clientY:number){
    const id=paperAt(clientX,clientY);setPointerHitId(id);highlight(id);return id;
  }
  function releaseGesture(event:ReactPointerEvent<SVGSVGElement>,clearPreview=false){
    if(gesture.current?.pointerId!==event.pointerId)return;
    gesture.current=null;setIsPanning(false);
    if(clearPreview){setPointerHitId(null);highlight(null);}
    if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
  }
  function pointerDown(event:ReactPointerEvent<SVGSVGElement>){
    if(event.button!==0||event.isPrimary===false||gesture.current)return;
    const matrix=event.currentTarget.getScreenCTM();
    if(!matrix)return;
    const paperId=pointerPreview(event.clientX,event.clientY);
    gesture.current={pointerId:event.pointerId,x:event.clientX,y:event.clientY,panX:pan.x,panY:pan.y,matrix,mode:paperId?"paper":"canvas",paperId,moved:false};
    event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);
  }
  function pointerMove(event:ReactPointerEvent<SVGSVGElement>){
    const active=gesture.current;
    if(active){
      if(active.pointerId!==event.pointerId)return;
      const dx=event.clientX-active.x,dy=event.clientY-active.y;
      if(dx*dx+dy*dy>PAN_THRESHOLD_PX**2)active.moved=true;
      // A gesture belongs to the paper or canvas from its initial press. A
      // slipped paper press can never turn into a map drag.
      if(active.mode!=="paper"&&active.moved){
        const delta=screenDeltaToMap(active.matrix,dx,dy);
        if(delta){active.mode="pan";setIsPanning(true);setPan({x:active.panX+delta.x,y:active.panY+delta.y});}
        setPointerHitId(null);highlight(null);
      }else pointerPreview(event.clientX,event.clientY);
    }else if(event.isPrimary!==false)pointerPreview(event.clientX,event.clientY);
  }
  function pointerUp(event:ReactPointerEvent<SVGSVGElement>){
    const active=gesture.current;
    if(!active||active.pointerId!==event.pointerId)return;
    const dx=event.clientX-active.x,dy=event.clientY-active.y;
    const releasedPaper=pointerPreview(event.clientX,event.clientY);
    const activate=active.mode==="paper"&&!active.moved&&dx*dx+dy*dy<=PAN_THRESHOLD_PX**2&&releasedPaper===active.paperId;
    releaseGesture(event);
    if(activate&&releasedPaper)onInspect(releasedPaper);
    if(event.pointerType==="touch"){setPointerHitId(null);highlight(null);}
  }
  function move(x:number,y:number){setPan(previous=>({x:previous.x+x,y:previous.y+y}));}
  return <div className="semantic-map">
    <div className="map-controls" aria-label="Map view controls"><button type="button" aria-label="Zoom map in" onClick={()=>setZoom(value=>boundedZoom(value*1.3))}>Zoom in +</button><button type="button" aria-label="Zoom map out" onClick={()=>setZoom(value=>boundedZoom(value/1.3))}>Zoom out −</button><button type="button" onClick={()=>{setPan({x:0,y:0});setZoom(1);}}>Reset map view</button><span className="meta">{Math.round(zoom*100)}%</span></div>
    <p className="map-hover" role="region" aria-label="Most recently highlighted paper metadata" tabIndex={0} aria-live="polite" aria-atomic="true">{hoverDetails?<><strong>{hoverDetails.title}</strong>{hoverDetails.year?` · ${hoverDetails.year}`:""}{!hoverDetails.abstract.trim()?" · title-only representation":""}<br/><span className="meta">{hoverDetails.authors.join(", ")}</span></>:"Hover or focus a point or paper to preview its title, year and authors."}</p>
    <svg viewBox="0 0 1000 580" className="map-svg" aria-label="Saved semantic map; use the paper list or focus a point to inspect" role="group" data-interaction={isPanning?"pan":pointerHitId?"paper":"canvas"}
      onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp}
      onPointerLeave={()=>{if(!gesture.current){setPointerHitId(null);highlight(null);}}}
      onPointerCancel={event=>releaseGesture(event,true)}
      onLostPointerCapture={event=>releaseGesture(event,true)}
      onClick={event=>{
        // Pointer gestures activate on release above. Preserve assistive
        // click activation without allowing the browser click to double-fire.
        if(event.detail!==0||(event.nativeEvent as PointerEvent|undefined)?.pointerType)return;
        const id=(event.target as Element).getAttribute("data-map-point");
        if(id&&points.some(point=>point.id===id))onInspect(id);
      }}>
      <title>Saved paper relationships</title><desc>Points use saved coordinates from one search preview. Filled markers are selected for exploration. Click or press Enter on a point to find its paper in the selection list. Use the paper list as a complete keyboard alternative.</desc>
      <g ref={pointLayer} transform={`translate(${500+pan.x},${290+pan.y}) scale(${zoom}) translate(-500,-290)`}>
        {points.map(point=>{const paper=papersById.get(point.id);if(!paper)return null;return <circle key={point.id} data-map-point={point.id} cx={point.x} cy={point.y} r={highlightedId===point.id||inspectedId===point.id?11:8} role="button" tabIndex={0} aria-label={`Show in paper selection: ${paper.title}${!paper.abstract.trim()?"; title-only representation":""}${selectedIds.has(point.id)?"; selected for exploration":""}`} aria-pressed={inspectedId===point.id}
          className={[selectedIds.has(point.id)?"selected":"",highlightedId===point.id?"hovered":"",inspectedId===point.id?"inspected":""].join(" ")}
          onKeyDown={event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();onInspect(point.id);}}} onFocus={()=>highlight(point.id)} onBlur={()=>highlight(null)}/>;})}
      </g>
      {!points.length&&<text x="500" y="290" textAnchor="middle">No embedded papers match the current filter.</text>}
    </svg>
    {!points.length&&<p className="muted">No embedded papers match this filter. Change or clear the filter to show saved points again.</p>}
    <div className="map-controls pan-controls" aria-label="Pan map with buttons"><span className="meta">PAN</span><button type="button" aria-label="Pan map left" onClick={()=>move(-70,0)}>←</button><button type="button" aria-label="Pan map right" onClick={()=>move(70,0)}>→</button><button type="button" aria-label="Pan map up" onClick={()=>move(0,-70)}>↑</button><button type="button" aria-label="Pan map down" onClick={()=>move(0,70)}>↓</button></div>
    <p className="muted">Click a point to find its paper in the selection list. Drag the background or use the pan buttons. Filled markers indicate source-selection drafts, not formal review inclusion. All actions are also available in the paper list.</p>
    {repeated&&<p className="notice">Some papers share identical saved coordinates. They overlap without added jitter; inspect each from the list.</p>}
  </div>;
}
