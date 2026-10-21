import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import {useState} from "react";
import Discover from "../components/discover.tsx";
import SemanticMap from "../components/semantic-map.tsx";
import type {Schema} from "../lib/api.ts";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
const text=(node:ReactTestInstance):string=>node.children.map(child=>typeof child==="string"?child:text(child)).join("");

/** Drive real SVG handlers with screen geometry, including current pan/zoom. */
function mapDriver(renderer:()=>ReactTestRenderer) {
  const captured=new Set<number>();
  const svgNode={getScreenCTM:()=>({a:1,b:0,c:0,d:1,e:0,f:0}),setPointerCapture:(id:number)=>captured.add(id),hasPointerCapture:(id:number)=>captured.has(id),releasePointerCapture:(id:number)=>captured.delete(id)};
  function matrix(){
    const value=renderer().root.findByType("g").props.transform;
    const match=/translate\(([-\d.]+),([-\d.]+)\) scale\(([-\d.]+)\)/.exec(value)!;
    const zoom=Number(match[3]);
    return {a:zoom,b:0,c:0,d:zoom,e:Number(match[1])-500*zoom,f:Number(match[2])-290*zoom};
  }
  function event(id:string){
    const marker=renderer().root.findByProps({"data-map-point":id}),m=matrix();
    return {clientX:m.a*marker.props.cx+m.e,clientY:m.d*marker.props.cy+m.f,pointerId:1,pointerType:"mouse",button:0,isPrimary:true,currentTarget:svgNode,preventDefault(){}};
  }
  return {
    nodeMock:(element:{type:unknown})=>element.type==="svg"?svgNode:element.type==="g"?{getScreenCTM:matrix}:null,
    hover:(id:string)=>renderer().root.findByType("svg").props.onPointerMove(event(id)),
    leave:()=>renderer().root.findByType("svg").props.onPointerLeave(),
    click:(id:string)=>{renderer().root.findByType("svg").props.onPointerDown(event(id));renderer().root.findByType("svg").props.onPointerUp(event(id));},
  };
}

/** Synthetic persisted metadata and DOM geometry test navigation, not model/retrieval quality. */
async function navigationFixture(mobile:boolean) {
  const papers:Schema<"Paper">[]=Array.from({length:4},(_,index)=>({id:`software-navigation:${index}`,title:`SOFTWARE NAVIGATION PAPER ${index}`,authors:["Synthetic test author"],year:2020+index,abstract:`Synthetic navigation fixture ${index}.`,pmid:null,doi:null,pmcid:null,url:""}));
  const search:Schema<"SearchPreview">={schema_version:"mvp.exploratory-preview.v1",id:"software-navigation-search",query:"software navigation test",research_question:"Software navigation test",query_translation:null,searched_at:"2026-10-21T00:00:00Z",sort:"relevance",date_from:null,date_to:null,total_reported:4,fetched_count:4,ordered_identifiers:papers.map(paper=>paper.id),papers,warnings:[],truncated:false,provider:"software-test",mode:"test",errors:[]};
  const workspace={id:`software-navigation-${mobile?"mobile":"desktop"}`,question:search.research_question,mode:"saved_example",created_at:search.searched_at,source_revision:0,current_preparation_id:null,selected_paper_ids:[],current_run_id:null,current_assessment_ids:{},searches:[{...search,distinct_count:4}],preparations:[],runs:[],assessments:[]} as Schema<"WorkspaceSummary">;
  const capabilities={default_mode:"saved_example",live_available:false,saved_example:{question:search.research_question,query:search.query},limits:{},boards:{max_fields:6,max_cells:60,max_boards:10,max_definition_revisions:20,max_cell_revisions:50,max_references:5,max_workspace_bytes:33554432,max_candidate_characters:1200,max_inspector_characters:4000},map:{ready:false,reason:"No model calls in this software fixture"}} as Schema<"Capabilities">;
  const coordinates=Object.freeze(Object.fromEntries(papers.map((paper,index)=>[paper.id,Object.freeze([index,index%2])])));
  const artifact={map_id:"software-navigation-map",search_id:search.id,coordinates_by_paper_id:coordinates,projection_method:"pca_small_corpus_v1",created_at:search.searched_at,status:"ready",representation_by_paper_id:Object.fromEntries(papers.map(paper=>[paper.id,"title_abstract"])),excluded_papers_with_reasons:[],coordinate_sha256:"software-fixed-coordinates"};
  const selected=[papers[0].id,papers[2].id];
  const requests:{method:string;url:string}[]=[];
  const originalFetch=globalThis.fetch;
  const originalWindow=Object.getOwnPropertyDescriptor(globalThis,"window"),originalDocument=Object.getOwnPropertyDescriptor(globalThis,"document");
  const events:{kind:string;id?:string;options?:unknown}[]=[];
  const rows=papers.map((paper,index)=>({
    id:"paper-selection-"+encodeURIComponent(paper.id),dataset:{paperId:paper.id},
    getAttribute:(name:string)=>name==="data-paper-id"?paper.id:null,
    getBoundingClientRect:()=>({top:300+index*180+24-panel.scrollTop,bottom:460+index*180+24-panel.scrollTop,left:800,right:1200,width:400,height:160}),
    focus:(options:unknown)=>events.push({kind:"row-focus",id:paper.id,options}),
    scrollIntoView:(options:unknown)=>events.push({kind:"row-scroll",id:paper.id,options}),
  }));
  const panel={clientTop:1,scrollTop:24,clientHeight:600,scrollHeight:1600,
    getBoundingClientRect:()=>({top:100,bottom:700,left:800,right:1200,width:400,height:600}),
    querySelectorAll:()=>rows,
    querySelector:(selector:string)=>rows.find(row=>selector.includes(row.dataset.paperId)||selector.includes(row.id))??null,
    scrollTo:(options:ScrollToOptions)=>{events.push({kind:"panel-scroll",options});if(options.top!==undefined)panel.scrollTop=options.top;},
  };
  const mapPanel={scrollIntoView:(options:unknown)=>events.push({kind:"map-scroll",options})};
  const inspector={scrollIntoView:(options:unknown)=>events.push({kind:"inspector-scroll",options})};
  Object.defineProperty(globalThis,"window",{configurable:true,value:{matchMedia:(query:string)=>({matches:mobile,media:query}),scrollTo:(options:unknown)=>events.push({kind:"window-scroll",options})}});
  Object.defineProperty(globalThis,"document",{configurable:true,value:{getElementById:(id:string)=>id==="paper-inspector"?inspector:rows.find(row=>row.id===id)??null}});
  globalThis.fetch=async(url,options)=>{
    const path=String(url),method=options?.method??"GET";requests.push({method,url:path});
    assert.equal(method,"GET","map navigation never writes a draft or submits retrieval/model work");
    let value:unknown;
    if(path.endsWith("/session"))value={csrf_token:"software-navigation"};
    else if(path.endsWith("/papers"))value=search;
    else if(path.includes("/maps?"))value={maps:[{map_id:artifact.map_id,search_id:search.id,created_at:artifact.created_at,status:artifact.status,projection_method:artifact.projection_method,embedded_count:4,excluded_count:0,paper_count:4}],jobs:[]};
    else if(path.includes("/neighbors/"))value={map_id:artifact.map_id,paper_id:decodeURIComponent(path.split("/").at(-1)!),neighbors:[{paper_id:papers[1].id,cosine_similarity:.8}]};
    else if(path.endsWith("/maps/"+artifact.map_id))value={artifact,counts:{provider_reported:4,fetched_records:4,distinct_records:4,embedded_papers:4,excluded_papers:0,map_points:4}};
    else if(path.includes("/drafts/")){const scope=decodeURIComponent(path.split("/").at(-1)!);value={scope,version:scope.startsWith("selection:")?1:0,data:scope.startsWith("selection:")?{selected_paper_ids:selected}:{},expected_assessment_head:null,updated_at:null};}
    else assert.fail(`Unexpected ${method} ${path}`);
    return new Response(JSON.stringify(value),{headers:{"Content-Type":"application/json"}});
  };
  let renderer!:ReactTestRenderer;const driver=mapDriver(()=>renderer);
  await act(async()=>{renderer=create(<Discover workspace={workspace} capabilities={capabilities} requestedMap={artifact.map_id} refresh={async()=>{assert.fail("Paper navigation must not refresh the workspace");}} navigate={async()=>{assert.fail("Paper navigation must not navigate away");}}/>,{createNodeMock:element=>{const props=element.props as Record<string,unknown>;return driver.nodeMock(element)??(props["data-exploration-panel"]==="papers"?panel:props["data-exploration-panel"]==="map"?mapPanel:props.id==="paper-inspector"?inspector:rows.find(row=>row.dataset.paperId===props["data-paper-id"])??null);}});});
  return {renderer,papers,artifact,requests,events,rows,panel,driver,async cleanup(){await act(async()=>renderer.unmount());globalThis.fetch=originalFetch;if(originalWindow)Object.defineProperty(globalThis,"window",originalWindow);else Reflect.deleteProperty(globalThis,"window");if(originalDocument)Object.defineProperty(globalThis,"document",originalDocument);else Reflect.deleteProperty(globalThis,"document");}};
}

const point=(renderer:ReactTestRenderer,id:string)=>renderer.root.findByProps({"data-map-point":id});
const paperSelections=(renderer:ReactTestRenderer)=>renderer.root.findAllByType("article").map(row=>row.findByType("input").props.checked);
const positions=(renderer:ReactTestRenderer)=>renderer.root.findAllByType("circle").map(circle=>[circle.props["data-map-point"],circle.props.cx,circle.props.cy]);
const turn=()=>new Promise(resolve=>setTimeout(resolve,0));

test("desktop map activations reveal the matching paper row repeatedly without jumping to the inspector",async()=>{
  const fixture=await navigationFixture(false),{renderer,papers,artifact,requests,events}=fixture;
  try {
    assert.equal(events.length,0,"opening a saved map does not scroll the page");
    const selectedBefore=paperSelections(renderer),positionsBefore=positions(renderer),coordinatesBefore=JSON.stringify(artifact.coordinates_by_paper_id);
    await act(async()=>renderer.root.findByProps({"aria-label":"Zoom map in"}).props.onClick());
    await act(async()=>renderer.root.findByProps({"aria-label":"Pan map left"}).props.onClick());
    const transformed=renderer.root.findByType("g").props.transform;
    for(const activation of ["click","click","Enter"," "]){
      events.length=0;let prevented=false;
      await act(async()=>{const marker=point(renderer,papers[3].id);if(activation==="click")fixture.driver.click(papers[3].id);else marker.props.onKeyDown({key:activation,preventDefault(){prevented=true;}});await turn();});
      assert.deepEqual(events.map(event=>event.kind),["row-focus","panel-scroll"],"desktop activation focuses the row and scrolls only its paper panel");
      assert.equal(events[0].id,papers[3].id);assert.deepEqual(events[0].options,{preventScroll:true});
      assert.equal((events[1].options as ScrollToOptions).behavior,"instant");
      assert.equal((events[1].options as ScrollToOptions).top,747,"the row aligns inside its panel with the 16px inset, including repeated activations");
      if(activation!=="click")assert.equal(prevented,true,"Space/Enter activation prevents native scrolling");
      assert.deepEqual(paperSelections(renderer),selectedBefore,"navigating to a paper does not select or deselect it");
      assert.equal(renderer.root.findByType("g").props.transform,transformed);assert.deepEqual(positions(renderer),positionsBefore);
    }
    events.length=0;
    const neighbor=renderer.root.findByProps({className:"neighbor-list"}).findAllByType("button")[0];
    await act(async()=>{neighbor.props.onClick();await turn();});
    assert.equal(events.find(event=>event.kind==="row-focus")?.id,papers[1].id,"neighbor navigation uses the same paper-row target");
    assert.equal(events.some(event=>event.kind==="inspector-scroll"||event.kind==="window-scroll"||event.kind==="row-scroll"),false);
    const filter=()=>renderer.root.findAllByType("input").find(input=>input.props.type==="search")!;
    await act(async()=>filter().props.onChange({target:{value:papers[3].title}}));
    assert.equal(renderer.root.findAllByType("circle").length,1);
    await act(async()=>{fixture.driver.click(papers[3].id);await turn();});
    assert.equal(filter().props.value,papers[3].title,"a visible map target preserves the user's local filter");
    events.length=0;
    await act(async()=>{renderer.root.findByProps({className:"neighbor-list"}).findAllByType("button")[0].props.onClick();await turn();});
    assert.equal(filter().props.value,"","a hidden neighbor is made visible in the list before focus");
    assert.match(text(renderer.root),/Local filter cleared to show the requested paper/);
    assert.equal(events.find(event=>event.kind==="row-focus")?.id,papers[1].id);
    assert.equal(events.some(event=>event.kind==="inspector-scroll"||event.kind==="window-scroll"||event.kind==="row-scroll"),false);
    events.length=0;
    await act(async()=>renderer.root.findByProps({"aria-label":"Mobile exploration view"}).findAllByType("button")[0].props.onClick());
    assert.equal(events.length,0,"the Map tab never scrolls the document on desktop");
    assert.equal(JSON.stringify(artifact.coordinates_by_paper_id),coordinatesBefore);assert.deepEqual(paperSelections(renderer),selectedBefore);
    assert.equal(requests.every(request=>request.method==="GET"),true);assert.equal(requests.filter(request=>request.url.endsWith("/maps/"+artifact.map_id)).length,1);
  } finally {await fixture.cleanup();}
});

test("mobile map activation opens Papers and focuses its corresponding row; inspection remains explicit",async()=>{
  const fixture=await navigationFixture(true),{renderer,papers,requests,events}=fixture;
  try {
    assert.equal(events.length,0,"initial mobile load does not scroll to the map");
    const selectedBefore=paperSelections(renderer),map=renderer.root.findByType("svg"),positionsBefore=positions(renderer);
    await act(async()=>renderer.root.findByProps({"aria-label":"Zoom map in"}).props.onClick());
    const transformed=renderer.root.findByType("g").props.transform;
    assert.equal(renderer.root.findByProps({"data-exploration-panel":"papers"}).props["data-active"],false);
    await act(async()=>{fixture.driver.click(papers[2].id);await turn();});
    assert.equal(renderer.root.findByProps({"data-exploration-panel":"papers"}).props["data-active"],true);
    assert.deepEqual(events.map(event=>event.kind),["row-focus","row-scroll"]);
    assert.equal(events[0].id,papers[2].id);assert.deepEqual(events[0].options,{preventScroll:true});
    assert.deepEqual(events[1].options,{behavior:"instant",block:"start"});
    assert.equal(renderer.root.findByType("svg"),map,"switching to Papers retains the mounted map");
    const tabs=renderer.root.findByProps({"aria-label":"Mobile exploration view"}).findAllByType("button");
    events.length=0;
    await act(async()=>tabs[0].props.onClick());
    assert.deepEqual(events,[{kind:"map-scroll",options:{behavior:"instant",block:"start"}}],"returning to Map explicitly reveals it after scrolling to a later paper");
    assert.equal(renderer.root.findByProps({"data-exploration-panel":"map"}).props["data-active"],true);
    assert.equal(renderer.root.findByType("svg"),map);assert.equal(renderer.root.findByType("g").props.transform,transformed);
    events.length=0;
    await act(async()=>tabs[0].props.onClick());
    assert.deepEqual(events,[{kind:"map-scroll",options:{behavior:"instant",block:"start"}}],"a repeated explicit Map activation can reveal the same mounted map again");
    events.length=0;
    await act(async()=>{fixture.driver.click(papers[2].id);await turn();});
    assert.equal(renderer.root.findByProps({"data-exploration-panel":"papers"}).props["data-active"],true,"repeated activation reopens the same row after returning to Map");
    assert.deepEqual(events.map(event=>event.kind),["row-focus","row-scroll"]);
    assert.deepEqual(paperSelections(renderer),selectedBefore);assert.deepEqual(positions(renderer),positionsBefore);
    events.length=0;
    const row=renderer.root.findAllByType("article").find(item=>item.props["data-paper-id"]===papers[2].id)!;
    await act(async()=>{row.findByType("button").props.onClick();await turn();});
    assert.deepEqual(events.map(event=>event.kind),["inspector-scroll"],"only the explicit Inspect paper button scrolls to the full inspector");
    assert.deepEqual(paperSelections(renderer),selectedBefore);assert.equal(requests.every(request=>request.method==="GET"),true);
  } finally {await fixture.cleanup();}
});

test("point hover and focus immediately expose complete metadata even while linked parent updates are deferred",async()=>{
  const authors=Array.from({length:100},(_,index)=>`SOFTWARE HOVER Author ${index}`);
  const papers:Schema<"Paper">[]=[{id:"hover-a",title:"SOFTWARE IMMEDIATE HOVER A",authors,year:2021,abstract:"Synthetic abstract.",pmid:null,doi:null,pmcid:null,url:""},{id:"hover-b",title:"SOFTWARE IMMEDIATE HOVER B",authors:["Synthetic second author"],year:2022,abstract:"",pmid:null,doi:null,pmcid:null,url:""}];
  const forwarded:(string|null)[]=[];let renderer!:ReactTestRenderer;const driver=mapDriver(()=>renderer);
  // Deliberately never send hoveredId back: local pointer details must not wait for parent work.
  await act(async()=>{renderer=create(<SemanticMap coordinates={{"hover-a":[0,0],"hover-b":[1,1]}} papers={papers} visibleIds={new Set(papers.map(paper=>paper.id))} selectedIds={new Set()} inspectedId={null} hoveredId={null} onInspect={()=>assert.fail("Hover cannot inspect or select a paper")} onHover={id=>forwarded.push(id)}/>,{createNodeMock:driver.nodeMock});});
  try {
    const region=()=>renderer.root.findByProps({"aria-label":"Most recently highlighted paper metadata"});
    const mapChildren=renderer.root.findByProps({className:"semantic-map"}).children;
    assert.ok(mapChildren.indexOf(region())<mapChildren.indexOf(renderer.root.findByType("svg")),"metadata is available above the plot without scrolling below it");
    act(()=>driver.hover("hover-a"));
    assert.match(text(region()),/SOFTWARE IMMEDIATE HOVER A/);assert.match(text(region()),/2021/);assert.equal(region().findByType("span").children.join(""),authors.join(", "));
    assert.equal(point(renderer,"hover-a").findAllByType("title").length,0,"the immediate metadata is not hidden behind a delayed native title tooltip");
    act(()=>driver.leave());
    assert.match(text(region()),/SOFTWARE IMMEDIATE HOVER A/);assert.match(text(region()),/SOFTWARE HOVER Author 99/,"complete details remain available while the user moves to the scrollable region");
    act(()=>point(renderer,"hover-b").props.onFocus());
    assert.match(text(region()),/SOFTWARE IMMEDIATE HOVER B/);assert.match(text(region()),/title-only representation/);
    assert.equal(region().props.tabIndex,0);assert.equal(region().props["aria-live"],"polite");
    assert.deepEqual(forwarded,["hover-a",null,"hover-b"]);
  } finally {await act(async()=>renderer.unmount());}
});

test("rapid pointer enter/leave does not revive a stale linked highlight after transition work",async()=>{
  const paper:Schema<"Paper">={id:"rapid-hover",title:"SOFTWARE RAPID HOVER",authors:["Synthetic author"],year:2021,abstract:"Synthetic abstract",pmid:null,doi:null,pmcid:null,url:""};
  function LinkedHover(){const [hovered,setHovered]=useState<string|null>(null);return <SemanticMap coordinates={{[paper.id]:[0,0]}} papers={[paper]} visibleIds={new Set([paper.id])} selectedIds={new Set()} inspectedId={null} hoveredId={hovered} onInspect={()=>{}} onHover={setHovered}/>;}
  let renderer!:ReactTestRenderer;const driver=mapDriver(()=>renderer);await act(async()=>{renderer=create(<LinkedHover/>,{createNodeMock:driver.nodeMock});});
  try {
    await act(async()=>{driver.hover(paper.id);driver.leave();});
    assert.equal(point(renderer,paper.id).props.className.split(" ").includes("hovered"),false);
    assert.equal(point(renderer,paper.id).props.r,8,"the linked highlight stays cleared after transition work flushes");
    assert.match(text(renderer.root.findByProps({"aria-label":"Most recently highlighted paper metadata"})),/SOFTWARE RAPID HOVER/,"the preview remains available after pointer exit");
  } finally {await act(async()=>renderer.unmount());}
});
