import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestRenderer} from "react-test-renderer";
import {useEffect,useState} from "react";
import SemanticMap from "../components/semantic-map.tsx";
import MapExplorer from "../components/map-explorer.tsx";
import ExplorationPanels from "../components/exploration-panels.tsx";
import type {Schema} from "../lib/api.ts";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const papers:Schema<"Paper">[]=["a","b","c"].map(id=>({id,title:"SOFTWARE TEST PAPER "+id,authors:["Synthetic test author"],year:2020,abstract:"Synthetic software test metadata, not a demonstration corpus.",pmid:null,pmcid:null,doi:null,url:""}));
const coordinates={a:[0,0] as [number,number],b:[1,1] as [number,number],c:[100,100] as [number,number]};

test("SVG inspection and pan/zoom are keyboard operable without changing saved positions",async()=>{
  const before=JSON.stringify(coordinates);const inspected:string[]=[];
  const props={coordinates,papers,visibleIds:new Set(["a","b","c"]),selectedIds:new Set(["b"]),inspectedId:null,hoveredId:null,onInspect:(id:string)=>inspected.push(id),onHover:()=>{}};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<SemanticMap {...props}/>);});
  let circles=renderer.root.findAllByType("circle");assert.equal(circles.length,3);assert.equal(circles[1].props.className.includes("selected"),true);
  let prevented=false;await act(async()=>circles[0].props.onKeyDown({key:"Enter",preventDefault(){prevented=true;}}));
  assert.deepEqual(inspected,["a"]);assert.equal(prevented,true);assert.equal(circles[0].props.tabIndex,0);
  const originalX=circles[0].props.cx,originalY=circles[0].props.cy;
  await act(async()=>renderer.root.findByProps({"aria-label":"Zoom map in"}).props.onClick());
  await act(async()=>renderer.root.findByProps({"aria-label":"Pan map left"}).props.onClick());
  assert.notEqual(renderer.root.findByType("g").props.transform,"translate(500,290) scale(1) translate(-500,-290)");
  await act(async()=>renderer.update(<SemanticMap {...props} visibleIds={new Set(["a","b"])}/>));
  circles=renderer.root.findAllByType("circle");assert.equal(circles.length,2);assert.equal(circles[0].props.cx,originalX);assert.equal(circles[0].props.cy,originalY);assert.equal(JSON.stringify(coordinates),before);
  await act(async()=>renderer.unmount());
});

test("opening/filtering/reopening a persisted map uses GET only and never builds or refits",async()=>{
  const requests:{method:string;url:string}[]=[];
  const artifact={map_id:"saved-map",search_id:"search",coordinates_by_paper_id:coordinates,projection_method:"pca_small_corpus_v1",created_at:"2026-01-01T00:00:00Z",status:"ready",representation_by_paper_id:{a:"title_abstract",b:"title_abstract",c:"title_only"},excluded_papers_with_reasons:[],coordinate_sha256:"persisted-coordinate-checksum"};
  const listing={maps:[{map_id:"saved-map",search_id:"search",created_at:artifact.created_at,status:"ready",projection_method:artifact.projection_method,embedded_count:3,excluded_count:0,paper_count:3}],jobs:[]};
  globalThis.fetch=async(url,options)=>{
    const path=String(url);requests.push({method:options?.method??"GET",url:path});
    const value=path.endsWith("/session")?{csrf_token:"test"}:path.includes("/maps?")?listing:path.endsWith("/maps/saved-map")?{artifact,counts:{provider_reported:500,fetched_records:3,distinct_records:3,embedded_papers:3,excluded_papers:0,map_points:3}}:{};
    return new Response(JSON.stringify(value),{headers:{"Content-Type":"application/json"}});
  };
  const search={id:"search",papers} as Schema<"SearchPreview">;
  const props={workspaceId:"workspace",search,capability:{ready:false,reason:"Optional weights missing"},visibleIds:new Set(["a","b","c"]),selectedIds:new Set<string>(),inspectedId:null,hoveredId:null,onInspect:()=>{},onHover:()=>{},onChooseMap:()=>{}};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<MapExplorer {...props}/>);});
  assert.equal(renderer.root.findAllByType("circle").length,3);
  await act(async()=>renderer.update(<MapExplorer {...props} visibleIds={new Set(["a"])}/>));
  assert.equal(renderer.root.findAllByType("circle").length,1);
  assert.equal(requests.some(item=>item.method!=="GET"),false);
  assert.equal(requests.filter(item=>item.url.endsWith("/maps/saved-map")).length,1);
  await act(async()=>renderer.unmount());
  await act(async()=>{renderer=create(<MapExplorer {...props}/>);});
  assert.equal(renderer.root.findAllByType("circle").length,3);assert.equal(requests.some(item=>item.method!=="GET"),false);
  assert.equal(JSON.stringify(artifact.coordinates_by_paper_id),JSON.stringify(coordinates));
  await act(async()=>renderer.unmount());
});

test("map computation and cooperative cancellation require explicit buttons",async()=>{
  const requests:{method:string;url:string;body:Record<string,unknown>}[]=[];
  const storage=new Map<string,string>();
  Object.defineProperty(globalThis,"sessionStorage",{configurable:true,value:{getItem:(key:string)=>storage.get(key)??null,setItem:(key:string,value:string)=>storage.set(key,value)}});
  const job={id:"job",workspace_id:"workspace",search_id:"search",map_id:"map",status:"queued",attempt:0,max_attempts:2,progress_completed:0,progress_total:3,interrupted_count:0,created_at:"2026-01-01T00:00:00Z",updated_at:"2026-01-01T00:00:00Z",error:null};
  let submitted=false;
  globalThis.fetch=async(url,options)=>{
    const path=String(url),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):{};requests.push({method,url:path,body});
    let value:unknown;
    if(path.endsWith("/session"))value={csrf_token:"test"};
    else if(path.includes("/maps?"))value={maps:[],jobs:submitted?[job]:[]};
    else if(path.endsWith("/maps")&&method==="POST"){submitted=true;value={job,map_id:null,reused:false};}
    else if(path.endsWith("/jobs/job/cancel"))value={...job,status:"cancel_requested"};
    else value=job;
    return new Response(JSON.stringify(value),{headers:{"Content-Type":"application/json"}});
  };
  const props={workspaceId:"workspace",search:{id:"search",papers} as Schema<"SearchPreview">,capability:{ready:true,reason:"Configured optional local weights"},visibleIds:new Set(["a","b","c"]),selectedIds:new Set<string>(),inspectedId:null,hoveredId:null,onInspect:()=>{},onHover:()=>{},onChooseMap:()=>{}};
  let renderer!:ReactTestRenderer;await act(async()=>{renderer=create(<MapExplorer {...props}/>);});
  assert.equal(requests.filter(request=>request.method==="POST").length,0);
  const button=(label:string)=>renderer.root.findAllByType("button").find(item=>item.children.join("")===label)!;
  await act(async()=>button("Build map of this saved search").props.onClick());
  const build=requests.find(request=>request.method==="POST"&&request.url.endsWith("/maps"))!;
  assert.equal(build.body.search_id,"search");assert.equal(build.body.profile_id,"paper_bge_v1");assert.equal(build.body.rebuild,false);assert.equal(typeof build.body.request_id,"string");
  await act(async()=>button("Cancel map build").props.onClick());
  assert.equal(requests.filter(request=>request.method==="POST").length,2);assert.equal(requests.some(request=>request.url.includes("source-preparations")||request.url.includes("evidence-runs")),false);
  await act(async()=>renderer.unmount());
});

test("mobile Map/Papers switching retains mounted map state and keeps the inspector outside both panels",async()=>{
  let mapMounts=0,mapUnmounts=0;
  function MapProbe(){const [zoom,setZoom]=useState(1);useEffect(()=>{mapMounts++;return()=>{mapUnmounts++;};},[]);return <button aria-label="Test map zoom" onClick={()=>setZoom(value=>value+1)}>{zoom}</button>;}
  let renderer!:ReactTestRenderer;
  await act(async()=>{renderer=create(<ExplorationPanels map={<MapProbe/>} papers={<p>SOFTWARE TEST paper list</p>} inspector={<aside aria-label="Test inspector">SOFTWARE TEST inspector</aside>}/>);});
  await act(async()=>renderer.root.findByProps({"aria-label":"Test map zoom"}).props.onClick());
  const group=renderer.root.findByProps({"aria-label":"Mobile exploration view"});
  const buttons=group.findAllByType("button");
  await act(async()=>buttons[1].props.onClick());
  assert.equal(renderer.root.findByProps({"data-exploration-panel":"map"}).props["data-active"],false);
  assert.equal(renderer.root.findByProps({"data-exploration-panel":"papers"}).props["data-active"],true);
  assert.equal(renderer.root.findByProps({"aria-label":"Test map zoom"}).children[0],"2");assert.equal(mapMounts,1);assert.equal(mapUnmounts,0);
  const inspector=renderer.root.findByProps({"aria-label":"Test inspector"});
  assert.equal(inspector.parent?.props["data-exploration-panel"],undefined);
  await act(async()=>buttons[0].props.onClick());
  assert.equal(renderer.root.findByProps({"aria-label":"Test map zoom"}).children[0],"2");assert.equal(mapMounts,1);
  await act(async()=>renderer.unmount());assert.equal(mapUnmounts,1);
});
