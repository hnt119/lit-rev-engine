import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import SemanticMap from "../components/semantic-map.tsx";
import type {Coordinate} from "../lib/map-view.ts";
import {nearestPaperHit,PAPER_HIT_RADIUS_PX,PAN_THRESHOLD_PX,screenDeltaToMap} from "../lib/map-interactions.ts";
import type {Schema} from "../lib/api.ts";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const content=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:content(child)).join("");
type Matrix={a:number;b:number;c:number;d:number;e:number;f:number};
const transform=(matrix:Matrix,x:number,y:number)=>({x:matrix.a*x+matrix.c*y+matrix.e,y:matrix.b*x+matrix.d*y+matrix.f});
const coordinates:Record<string,Coordinate>={a:[0,0],b:[50,50],c:[100,0]};

/** Screen geometry is independent of SVG's aspect ratio: this fixture includes
 * responsive scaling and x/y letterbox offsets, then applies the real view transform.
 * Metadata is synthetic; these tests do not run embeddings or retrieval. */
async function fixture(saved:Record<string,Coordinate>=coordinates,rootMatrix:Matrix={a:.5,b:0,c:0,d:.5,e:120,f:85}){
  const papers:Schema<"Paper">[]=Object.keys(saved).map(id=>({id,title:`SOFTWARE HIT PAPER ${id}`,authors:["Synthetic author"],year:2026,abstract:"Synthetic event fixture.",pmid:null,pmcid:null,doi:null,url:""}));
  const inspected:string[]=[],highlighted:(string|null)[]=[],captureEvents:string[]=[],captured=new Set<number>();
  let renderer!:ReactTestRenderer;
  const svgNode={getScreenCTM:()=>rootMatrix,getBoundingClientRect:()=>({left:100,top:50,width:600,height:400,right:700,bottom:450}),
    setPointerCapture:(id:number)=>{captured.add(id);captureEvents.push(`set:${id}`);},
    hasPointerCapture:(id:number)=>captured.has(id),releasePointerCapture:(id:number)=>{captured.delete(id);captureEvents.push(`release:${id}`);},
  };
  function groupMatrix():Matrix {
    const value=renderer?.root.findByType("g").props.transform??"translate(500,290) scale(1) translate(-500,-290)";
    const match=/translate\(([-\d.]+),([-\d.]+)\) scale\(([-\d.]+)\)/.exec(value)!;
    const x=Number(match[1]),y=Number(match[2]),zoom=Number(match[3]);
    const tx=x-500*zoom,ty=y-290*zoom;
    return {a:rootMatrix.a*zoom,b:rootMatrix.b*zoom,c:rootMatrix.c*zoom,d:rootMatrix.d*zoom,e:rootMatrix.e+rootMatrix.a*tx+rootMatrix.c*ty,f:rootMatrix.f+rootMatrix.b*tx+rootMatrix.d*ty};
  }
  const groupNode={getScreenCTM:groupMatrix};
  await act(async()=>{renderer=create(<SemanticMap coordinates={saved} papers={papers} visibleIds={new Set(papers.map(paper=>paper.id))} selectedIds={new Set()} inspectedId={null} hoveredId={null} onInspect={id=>inspected.push(id)} onHover={id=>highlighted.push(id)}/>,{createNodeMock:element=>element.type==="svg"?svgNode:element.type==="g"?groupNode:null});});
  const svg=()=>renderer.root.findByType("svg"),view=()=>renderer.root.findByType("g").props.transform;
  const circle=(id:string)=>renderer.root.findByProps({"data-map-point":id});
  const target=(id?:string)=>({getAttribute:(key:string)=>key==="data-map-point"?(id??null):null,closest:()=>id?{getAttribute:(key:string)=>key==="data-map-point"?id:null}:null});
  const center=(id:string)=>{const marker=circle(id);return transform(groupMatrix(),marker.props.cx,marker.props.cy);};
  function event(position:{x:number;y:number},over?:string,extra:Record<string,unknown>={}){return {clientX:position.x,clientY:position.y,pointerId:1,pointerType:"mouse",button:0,isPrimary:true,detail:1,currentTarget:svgNode,target:target(over),preventDefault(){},stopPropagation(){},...extra};}
  async function pointer(handler:string,position:{x:number;y:number},over?:string,extra:Record<string,unknown>={}){await act(async()=>svg().props[handler](event(position,over,extra)));}
  return {renderer,svg,view,circle,center,event,pointer,svgNode,captured,captureEvents,inspected,highlighted,async close(){await act(async()=>renderer.unmount());}};
}

test("the invisible 14 CSS-pixel hit radius uses screen geometry and selects the nearest overlapping paper",()=>{
  assert.equal(PAPER_HIT_RADIUS_PX,14);assert.equal(PAN_THRESHOLD_PX,4);
  const points=[{id:"far",x:100,y:100},{id:"near",x:110,y:100}],matrix={a:.5,b:0,c:0,d:.5,e:103,f:71};
  assert.equal(nearestPaperHit(points,{x:157.9,y:121},matrix),"near","nearest wins even when the farther paper occurs earlier in paint order");
  assert.equal(nearestPaperHit([...points].reverse(),{x:157.9,y:121},matrix),"near");
  assert.equal(nearestPaperHit([{id:"only",x:100,y:100}],{x:166.9,y:121},matrix),"only");
  assert.equal(nearestPaperHit([{id:"only",x:100,y:100}],{x:167.1,y:121},matrix),null,"the radius is CSS pixels, not doubled or halved by SVG scale");
  assert.equal(nearestPaperHit([{id:"z",x:0,y:0},{id:"a",x:0,y:0}],{x:103,y:71},matrix),"a","identical-position ties are deterministic");
  assert.equal(nearestPaperHit(points,{x:Infinity,y:121},matrix),null);
  assert.deepEqual(screenDeltaToMap(matrix,10,15),{x:20,y:30});
  assert.deepEqual(screenDeltaToMap({a:0,b:2,c:-2,d:0,e:20,f:30},10,20),{x:10,y:-5},"panning inverts the full screen transform");
});

test("near-dot hover exposes the title immediately and paper presses never initiate panning",async()=>{
  const f=await fixture(),savedBefore=JSON.stringify(coordinates);
  try {
    const center=f.center("a"),outsideVisibleDot={x:center.x+13,y:center.y},original=f.view();
    assert.equal(f.circle("a").props.r,8,"visible idle dots retain their existing radius");
    await f.pointer("onPointerMove",outsideVisibleDot);
    assert.equal(f.svg().props["data-interaction"],"paper");
    assert.match(content(f.renderer.root.findByProps({"aria-label":"Most recently highlighted paper metadata"})),/SOFTWARE HIT PAPER a/);
    assert.equal(f.circle("a").props.className.split(" ").includes("hovered"),true);
    assert.equal(f.circle("a").props.r,11,"highlight uses the pre-existing visible hover radius");
    assert.deepEqual(f.inspected,[]);
    await f.pointer("onPointerDown",outsideVisibleDot);
    assert.equal(f.captured.has(1),true);
    await f.pointer("onPointerMove",{x:center.x+70,y:center.y+40});
    assert.equal(f.view(),original,"slipping a paper-origin gesture cannot turn it into a canvas drag");
    assert.notEqual(f.svg().props["data-interaction"],"pan");
    await f.pointer("onPointerUp",{x:center.x+70,y:center.y+40});
    assert.equal(f.captured.size,0);assert.deepEqual(f.inspected,[]);
    assert.equal(JSON.stringify(coordinates),savedBefore,"pointer state never changes stored map coordinates");
  } finally {await f.close();}
});

test("overlapping screen hitboxes arbitrate by distance rather than the event's painted target",async()=>{
  const f=await fixture({a:[0,0],b:[1,0],c:[100,100]});
  try {
    const a=f.center("a"),b=f.center("b"),nearB={x:b.x-.2,y:b.y};
    assert.ok(Math.hypot(a.x-b.x,a.y-b.y)<PAPER_HIT_RADIUS_PX);
    await f.pointer("onPointerMove",nearB,"a");
    assert.equal(f.highlighted.at(-1),"b","hover and activation share the same nearest-point arbitration");
    await f.pointer("onPointerDown",nearB,"a");
    await f.pointer("onPointerUp",nearB,"a");
    await f.pointer("onClick",nearB,"a");
    assert.deepEqual(f.inspected,["b"],"the native click following pointer-up cannot select the painted target a second time");
    assert.equal(f.captured.size,0);
  } finally {await f.close();}
});

test("the hit radius stays in CSS pixels after responsive scaling, button zooming and panning",async()=>{
  const f=await fixture();
  try {
    const original=Object.fromEntries(Object.keys(coordinates).map(id=>[id,[f.circle(id).props.cx,f.circle(id).props.cy]]));
    await act(async()=>f.renderer.root.findByProps({"aria-label":"Zoom map in"}).props.onClick());
    await act(async()=>f.renderer.root.findByProps({"aria-label":"Pan map right"}).props.onClick());
    const center=f.center("b"),view=f.view();
    await f.pointer("onPointerMove",{x:center.x+13.9,y:center.y});
    assert.equal(f.svg().props["data-interaction"],"paper");assert.equal(f.highlighted.at(-1),"b");
    await f.pointer("onPointerDown",{x:center.x+13.9,y:center.y});
    await f.pointer("onPointerUp",{x:center.x+13.9,y:center.y});
    assert.deepEqual(f.inspected,["b"]);assert.equal(f.view(),view);
    await f.pointer("onPointerMove",{x:center.x+14.1,y:center.y});
    assert.equal(f.svg().props["data-interaction"],"canvas");assert.equal(f.highlighted.at(-1),null);
    for(const id of Object.keys(coordinates))assert.deepEqual([f.circle(id).props.cx,f.circle(id).props.cy],original[id]);
  } finally {await f.close();}
});

test("a visibly painted high-zoom marker remains a paper target outside the minimum invisible radius",async()=>{
  const f=await fixture({a:[0,0],b:[50,0],c:[100,0]});
  try {
    for(let index=0;index<8;index++)await act(async()=>f.renderer.root.findByProps({"aria-label":"Zoom map in"}).props.onClick());
    const center=f.center("b"),original=f.view(),onVisibleMarker={x:center.x+25,y:center.y};
    assert.equal(f.circle("b").props.r,8,"zoom transforms the same visible dot rather than replacing it with a larger marker");
    // The original r=8 circle at 8x zoom and .5 CSS scale paints a 32px radius.
    assert.ok(25>PAPER_HIT_RADIUS_PX);
    await f.pointer("onPointerMove",onVisibleMarker,"b");
    assert.equal(f.svg().props["data-interaction"],"paper");
    await f.pointer("onPointerDown",onVisibleMarker,"b");
    await f.pointer("onPointerUp",onVisibleMarker,"b");
    assert.deepEqual(f.inspected,["b"]);assert.equal(f.view(),original);
  } finally {await f.close();}
});

test("only an empty-space origin starts panning, and releasing over a paper does not activate it",async()=>{
  const f=await fixture();
  try {
    const start={x:370,y:230},before=f.view();
    await f.pointer("onPointerMove",start);assert.equal(f.svg().props["data-interaction"],"canvas");
    await f.pointer("onPointerDown",start);assert.equal(f.svg().props["data-interaction"],"canvas");
    await f.pointer("onPointerMove",{x:start.x+2,y:start.y+1});
    assert.equal(f.view(),before,"small empty-canvas tap jitter does not move the viewport");
    assert.equal(f.svg().props["data-interaction"],"canvas");
    await f.pointer("onPointerMove",{x:start.x+20,y:start.y+10});
    assert.equal(f.svg().props["data-interaction"],"pan");
    assert.equal(f.view(),"translate(540,310) scale(1) translate(-500,-290)","pan deltas invert root CTM instead of using letterboxed bounding-box ratios");
    await f.pointer("onPointerUp",f.center("b"),"b");
    await f.pointer("onClick",f.center("b"),"b");
    assert.deepEqual(f.inspected,[]);assert.equal(f.captured.size,0);
    assert.notEqual(f.svg().props["data-interaction"],"pan");
  } finally {await f.close();}
});

test("cancellation and lost capture end the drag, ignore foreign pointers, and leave keyboard activation available",async()=>{
  const f=await fixture();
  try {
    const start={x:370,y:230};
    for(const ending of ["onPointerCancel","onLostPointerCapture"]){
      await f.pointer("onPointerDown",start);
      await f.pointer("onPointerMove",{x:start.x+12,y:start.y+8});
      assert.equal(f.svg().props["data-interaction"],"pan");
      const dragging=f.view();
      await f.pointer("onPointerMove",{x:start.x+100,y:start.y+100},undefined,{pointerId:2});
      assert.equal(f.view(),dragging,"another touch/pointer cannot hijack the captured gesture");
      if(ending==="onLostPointerCapture")f.captured.delete(1);
      await f.pointer(ending,start);
      assert.notEqual(f.svg().props["data-interaction"],"pan");assert.equal(f.captured.size,0);
      await f.pointer("onPointerMove",{x:start.x+100,y:start.y+100});assert.equal(f.view(),dragging,"movement after cleanup cannot continue the old drag");
    }
    for(const key of ["Enter"," "]){let prevented=false;await act(async()=>f.circle("a").props.onKeyDown({key,preventDefault(){prevented=true;}}));assert.equal(prevented,true);}
    assert.deepEqual(f.inspected,["a","a"]);
    await f.pointer("onClick",f.center("c"),"c",{detail:0});
    assert.deepEqual(f.inspected,["a","a","c"],"screen-reader/keyboard click remains available without pointer coordinates");
    assert.equal(f.circle("a").props.tabIndex,0);
  } finally {await f.close();}
});

test("touch activation happens once, foreign pointer endings do not steal it, and an empty tap cannot select a nearby paper",async()=>{
  const f=await fixture();
  try {
    const paper=f.center("a");
    await f.pointer("onPointerDown",paper,"a",{pointerType:"touch"});
    await f.pointer("onPointerUp",paper,"a",{pointerId:2,pointerType:"touch"});
    await f.pointer("onPointerCancel",paper,"a",{pointerId:2,pointerType:"touch"});
    assert.equal(f.captured.has(1),true,"another pointer ending leaves the original gesture captured");
    assert.deepEqual(f.inspected,[]);
    await f.pointer("onPointerUp",paper,"a",{pointerType:"touch"});
    assert.deepEqual(f.inspected,["a"]);assert.equal(f.captured.size,0);
    assert.equal(f.svg().props["data-interaction"],"canvas","touch release clears the transient cursor and hover");
    await f.pointer("onClick",paper,"a",{detail:0,nativeEvent:{pointerType:"touch"}});
    assert.deepEqual(f.inspected,["a"],"a touch-generated zero-detail click does not activate a second time");
    const before=f.view();
    await f.pointer("onPointerDown",{x:paper.x+16,y:paper.y});
    await f.pointer("onPointerUp",{x:paper.x+13,y:paper.y});
    assert.deepEqual(f.inspected,["a"],"the release entered the paper hitbox, but the gesture began on empty canvas");
    assert.equal(f.view(),before);
  } finally {await f.close();}
});
