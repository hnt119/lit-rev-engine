import assert from "node:assert/strict";
import test from "node:test";
import {act,create,type ReactTestInstance,type ReactTestRenderer} from "react-test-renderer";
import WorkspaceApp from "../components/workspace-app";
import DesktopSetup,{ObservedSetupSummary} from "../components/desktop-setup";
import ResearchSettings from "../components/research-settings";
import {flushDrafts,registerDraftFlusher} from "../lib/drafts";
import {loadOnboardingExample,readDesktopOnboarding,type DesktopOnboarding} from "../lib/desktop-onboarding";
import type {RuntimeSettings} from "../lib/runtime-settings";
import {setupDestination,settingsDestination,researchDestination} from "../lib/settings-navigation";
import {allowedRoute,allowedQuery} from "../lib/bridge";
import type {Schema} from "../lib/api";

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,window:{addEventListener(){},removeEventListener(){}}});
const content=(node:ReactTestInstance|string):string=>typeof node==="string"?node:node.children.map(content).join("");
const button=(r:ReactTestRenderer,label:string)=>{const item=r.root.findAllByType("button").find(node=>content(node)===label);assert.ok(item,label);return item;};
const control=(r:ReactTestRenderer,label:string)=>{const item=r.root.findAllByType("label").find(node=>content(node).startsWith(label));assert.ok(item,label);return item.findAll(node=>["input","select","textarea"].includes(String(node.type)))[0];};
const settings=():RuntimeSettings=>({schema_version:"runtime-settings.v1",revision:7,configured:true,preferences:{pubmed:{enabled:false,email:""},ai:{provider:"none",model:"",model_revision:"",local_url:"http://127.0.0.1:8000/v1/chat/completions",planning_enabled:false,proposals_enabled:false},defaults:{max_results:30,sort:"relevance"},maps:{cache_dir:""},retrieval:{profile_id:"legacy_block_prefix_v1",device:"cpu"}},credentials:{ai_api_key:false,ncbi_api_key:false},status:{pubmed:{state:"Disabled",message:"Manual research remains available."},ai:{state:"Disabled",message:"No generation configured."},maps:{state:"Disabled",message:"No map model."}},operator_configuration:"unchanged"});
const progress=(step:DesktopOnboarding["step"]="welcome",completed=false):DesktopOnboarding=>({schema_version:"desktop-onboarding.v1",revision:2,step,completed});
const capabilities={saved_example:{query:"public saved query",question:"Public example question",bundle_id:"public-30"}} as unknown as Schema<"Capabilities">;
function storage(){const values=new Map<string,string>();Object.assign(globalThis,{sessionStorage:{getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>values.set(key,value),removeItem:(key:string)=>values.delete(key)}});return values;}
function fetcher(){const calls:{method:string;path:string;body:any}[]=[];let saved=settings(),onboarding=progress();globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):undefined;calls.push({path,method,body});if(path.endsWith("/session"))return Response.json({csrf_token:"software"});if(path.endsWith("/settings/onboarding")){if(method==="PUT")onboarding={...onboarding,step:body.step,completed:onboarding.completed||body.completed,revision:onboarding.revision+1};return Response.json(onboarding);}if(path.endsWith("/settings/retrieval"))return Response.json({packs:[]});if(path.endsWith("/capabilities"))return Response.json(capabilities);if(path.endsWith("/settings")){if(method==="PUT")saved={...saved,revision:saved.revision+1,preferences:body.preferences};return Response.json(saved);}throw Error("Unexpected request "+method+" "+path);};return calls;}
const forbidden=(calls:{method:string;path:string}[])=>calls.filter(call=>call.method!=="GET"&&!call.path.endsWith("/settings/onboarding")&&!call.path.endsWith("/settings"));

test("welcome mount reads no provider and creates nothing; optional continuation saves only progress",async()=>{
  storage();const calls=fetcher();const steps:string[]=[];let current=progress();let r!:ReactTestRenderer;
  await act(async()=>{r=create(<DesktopSetup progress={current} step="welcome" capabilities={capabilities} onProgress={value=>{current=value;}} onStep={async value=>{steps.push(value);}} onReturn={async()=>{}} onExample={async()=>assert.fail("No example without click")}/>);});
  try{assert.equal(calls.length,0);assert.ok(button(r,"Try the saved example"));await act(async()=>button(r,"Set up my research workspace").props.onClick());assert.deepEqual(steps,["sources"]);assert.equal(current.step,"sources");const writes=calls.filter(call=>call.method!=="GET");assert.deepEqual(writes.map(call=>call.path),["/api/v1/settings/onboarding"]);assert.deepEqual(writes[0].body,{expected_revision:2,step:"sources",completed:false});assert.equal(forbidden(calls).length,0);}finally{await act(async()=>r.unmount());}
});

test("guided settings filter sections and skip without saving configuration, tests or inference",async()=>{
  storage();const calls=fetcher();let r!:ReactTestRenderer;let skipped=0;
  await act(async()=>{r=create(<ResearchSettings section="sources" guided={{section:"sources",pending:false,continueLabel:"Continue to retrieval",onContinue:async()=>{},onSkip:async()=>{skipped++;}}} onReturn={async()=>{}}/>);});
  try{assert.ok(control(r,"NCBI contact email"));assert.equal(r.root.findAllByProps({id:"settings-retrieval"}).length,0);assert.equal(r.root.findAllByProps({id:"settings-ai"}).length,0);assert.equal(calls.filter(call=>call.path.endsWith("/settings/retrieval")).length,0);assert.equal(calls.every(call=>call.method==="GET"),true);
    await act(async()=>button(r,"Set up later").props.onClick());assert.equal(skipped,1);assert.equal(calls.every(call=>call.method==="GET"),true);
    await act(async()=>control(r,"NCBI contact email").props.onChange({target:{value:"synthetic@example.org"}}));assert.equal(button(r,"Set up later").props.disabled,true);await assert.rejects(flushDrafts(),/Save Research/);
    await act(async()=>r.root.findByType("form").props.onSubmit({preventDefault(){}}));assert.equal(button(r,"Set up later").props.disabled,false);assert.equal(calls.filter(call=>call.method==="PUT"&&call.path.endsWith("/settings")).length,1);assert.equal(forbidden(calls).length,0);
  }finally{await act(async()=>r.unmount());}
});

test("progress conflict preserves settings edits and requires explicit progress inspection",async()=>{
  storage();const calls=fetcher(),original=globalThis.fetch;let conflict=true;globalThis.fetch=async(input,options)=>{if(String(input).endsWith("/settings/onboarding")&&options?.method==="PUT"&&conflict){conflict=false;return Response.json({detail:{code:"stale_onboarding",message:"Progress changed elsewhere."}},{status:409});}return original(input,options);};let latest=progress(),r!:ReactTestRenderer;
  await act(async()=>{r=create(<DesktopSetup progress={latest} step="sources" capabilities={capabilities} onProgress={value=>{latest=value;}} onStep={async()=>assert.fail("Conflicting progress cannot navigate")} onReturn={async()=>{}} onExample={async()=>{}}/>);});
  try{await act(async()=>button(r,"Set up later").props.onClick());assert.match(content(r.root),/Setup progress changed in another window/);assert.equal(button(r,"Research sources").props.disabled,true);await act(async()=>control(r,"NCBI contact email").props.onChange({target:{value:"synthetic-retained@example.org"}}));await act(async()=>button(r,"Inspect latest setup progress").props.onClick());assert.equal(button(r,"Research sources").props.disabled,false);assert.equal(control(r,"NCBI contact email").props.value,"synthetic-retained@example.org");assert.equal(button(r,"Set up later").props.disabled,true);await assert.rejects(flushDrafts(),/Save Research/);assert.equal(forbidden(calls).length,0);}finally{await act(async()=>r.unmount());}
});

test("saved progress resumes after remount, while Back and refresh keep exact opaque task context",async()=>{
  storage();const calls=fetcher();let r!:ReactTestRenderer;
  const original={page:"compare" as const,workspace:"w",board:"b",revision:"r",paper:"p",field:"f",run:"run",passage:"passage",preparation:"preparation",returnTo:"cell" as const};
  const route=setupDestination(original,"retrieval");assert.deepEqual(researchDestination(route),original);assert.equal(route.setupGuide,"retrieval");assert.equal("setupGuide" in settingsDestination(route,"ai"),false);
  const loaded=await readDesktopOnboarding();await act(async()=>{r=create(<DesktopSetup progress={{...loaded,step:"retrieval"}} step="retrieval" capabilities={capabilities} onProgress={()=>{}} onStep={async()=>{}} onReturn={async()=>{}} onExample={async()=>{}}/>);});
  try{assert.equal(r.root.findAllByProps({id:"settings-sources"}).length,0);assert.ok(r.root.findByProps({id:"settings-retrieval"}));assert.equal(forbidden(calls).length,0);await act(async()=>r.unmount());await act(async()=>{r=create(<DesktopSetup progress={{...loaded,step:"retrieval"}} step="retrieval" capabilities={capabilities} onProgress={()=>{}} onStep={async()=>{}} onReturn={async()=>{}} onExample={async()=>{}}/>);});assert.ok(r.root.findByProps({id:"settings-retrieval"}));assert.equal(forbidden(calls).length,0);}finally{await act(async()=>r.unmount());}
});

test("existing draft barrier blocks setup progress navigation without touching its config or tasks",async()=>{
  storage();const calls=fetcher();let r!:ReactTestRenderer;const remove=registerDraftFlusher(async()=>{throw Error("Synthetic cell draft conflict");});
  await act(async()=>{r=create(<DesktopSetup progress={progress()} step="welcome" capabilities={capabilities} onProgress={()=>assert.fail("No progress save")} onStep={async()=>assert.fail("No navigation")} onReturn={async()=>{}} onExample={async()=>{}}/>);});
  try{await act(async()=>button(r,"Set up my research workspace").props.onClick());assert.match(content(r.root),/Synthetic cell draft conflict/);assert.equal(calls.filter(call=>call.method!=="GET").length,0);}finally{remove();await act(async()=>r.unmount());}
});

test("observed summary does not mark configured or partial optional features Ready and retries reads only",async()=>{
  storage();const calls=fetcher(),original=globalThis.fetch;let failed=true;globalThis.fetch=async(input,options)=>{if(String(input).endsWith("/settings/retrieval")){calls.push({path:String(input),method:options?.method??"GET",body:undefined});if(failed){failed=false;throw Error("Synthetic pack status failure");}return Response.json({packs:[{label:"Qwen experimental",state:"runtime_failed",installed:true,dependencies:{state:"available"},runtime:{encoder_executed:true,reranker_executed:true,device:"cpu"}}]});}return original(input,options);};let r!:ReactTestRenderer;
  await act(async()=>{r=create(<ObservedSetupSummary/>);});
  try{assert.match(content(r.root),/Core research does not need a model/);assert.match(content(r.root),/Optional pack status could not be read/);assert.match(content(r.root),/does not certify an optional/);await act(async()=>button(r,"Read setup status again").props.onClick());assert.match(content(r.root),/Qwen experimental · Failed/);assert.match(content(r.root),/did not establish a usable runtime/);assert.doesNotMatch(content(r.root),/encoder and reranker execution recorded/);assert.equal(calls.every(call=>call.method==="GET"),true);}finally{await act(async()=>r.unmount());}
});

test("explicit example load uses existing saved services with idempotent retry and no preparation/provider endpoint",async()=>{
  const values=storage(),calls:{path:string;method:string;body:any}[]=[];let fail=true;
  globalThis.fetch=async(input,options)=>{const path=String(input),method=options?.method??"GET",body=options?.body?JSON.parse(String(options.body)):null;calls.push({path,method,body});if(path.endsWith("/session"))return Response.json({csrf_token:"software"});if(path.endsWith("/workspaces"))return Response.json({id:"example",mode:"saved_example"});if(path.endsWith("/searches")){if(fail){fail=false;throw Error("Synthetic interrupted search");}return Response.json({id:"saved-search"});}if(path.endsWith("/settings/onboarding"))return Response.json({...progress("ready",true),revision:3});throw Error("Unexpected action "+path);};
  await assert.rejects(loadOnboardingExample(capabilities,progress()),/Synthetic interrupted/);assert.ok(values.size>0);const result=await loadOnboardingExample(capabilities,progress());assert.equal(result.search.id,"saved-search");
  const creates=calls.filter(call=>call.path.endsWith("/workspaces"));assert.equal(creates[0].body.request_id,creates[1].body.request_id);assert.equal(creates[0].body.mode,"saved_example");const searches=calls.filter(call=>call.path.endsWith("/searches"));assert.equal(searches[0].body.request_id,searches[1].body.request_id);assert.equal(searches[0].body.max_results,30);assert.equal(searches[0].body.query,capabilities.saved_example.query);assert.equal(values.size,0);assert.ok(calls.every(call=>/\/(?:session|workspaces|searches|onboarding)$/.test(call.path)));assert.equal(calls.filter(call=>/prepare|propose|install|runtime|test-pubmed/.test(call.path)).length,0);
});

test("bridge permits only local progress GET/PUT with no query payload channel",()=>{assert.equal(allowedRoute("GET","settings/onboarding"),true);assert.equal(allowedRoute("PUT","settings/onboarding"),true);assert.equal(allowedRoute("POST","settings/onboarding"),false);assert.equal(allowedRoute("DELETE","settings/onboarding"),false);for(const name of ["question","key","notes","url"])assert.equal(allowedQuery("settings/onboarding",new URLSearchParams({[name]:"synthetic"})),false);});

test("all optional steps can wait; finishing progress never saves settings or tests services",async()=>{
  storage();const calls=fetcher();let current=progress(),step:DesktopOnboarding["step"]="welcome",returned=0,r!:ReactTestRenderer;
  const render=()=> <DesktopSetup progress={current} step={step} capabilities={capabilities} onProgress={value=>{current=value;}} onStep={async value=>{step=value;r.update(render());}} onReturn={async()=>{returned++;}} onExample={async()=>assert.fail("No example without explicit action")}/>;
  await act(async()=>{r=create(render());});
  try{await act(async()=>button(r,"Set up my research workspace").props.onClick());for(let i=0;i<3;i++)await act(async()=>button(r,"Set up later").props.onClick());assert.equal(step,"ready");assert.equal(current.completed,false);await act(async()=>button(r,"Open workspaces").props.onClick());assert.equal(current.completed,true);assert.equal(returned,1);const writes=calls.filter(call=>call.method!=="GET");assert.equal(writes.length,5);assert.ok(writes.every(call=>call.path.endsWith("/settings/onboarding")));assert.ok(writes.slice(0,-1).every(call=>call.body.completed===false));assert.deepEqual(writes.at(-1)!.body,{expected_revision:6,step:"ready",completed:true});}finally{await act(async()=>r.unmount());}
});

function browserState(initial:string){
  let url=new URL(initial),state:any={},pop:(()=>void)|null=null;
  const location={get search(){return url.search;},get href(){return url.href;},reload(){}};
  const window={location,history:{get state(){return state;},replaceState(next:any,_title:string,value:string){state=next;url=new URL(value,url);},pushState(next:any,_title:string,value:string){state=next;url=new URL(value,url);},go(){}},scrollY:0,scrollTo(){},addEventListener(name:string,callback:()=>void){if(name==="popstate")pop=callback;},removeEventListener(name:string){if(name==="popstate")pop=null;}};
  Object.defineProperty(globalThis,"window",{configurable:true,value:window});return{url:()=>url,pop:()=>pop?.()};
}

test("desktop capability gates first-run welcome; completed, browser-beta and direct task URLs are not interrupted",async()=>{
  for(const scenario of [{desktop:false,completed:false,url:"/?page=workspaces",welcome:false},{desktop:true,completed:true,url:"/?page=workspaces",welcome:false},{desktop:true,completed:false,url:"/?page=workspaces",welcome:true},{desktop:true,completed:false,url:"/?page=evidence&board=b&revision=r&paper=p&field=f&run=run",welcome:false}]){
    storage();const browser=browserState("http://127.0.0.1:3000"+scenario.url),calls:string[]=[];
    globalThis.fetch=async(input,options)=>{const path=String(input);calls.push((options?.method??"GET")+" "+path);if(path.endsWith("/session"))return Response.json({csrf_token:"software"});if(path.endsWith("/capabilities"))return Response.json({...capabilities,desktop_onboarding_ready:scenario.desktop});if(path.endsWith("/settings/onboarding"))return Response.json(progress("welcome",scenario.completed));if(path.endsWith("/settings"))return Response.json(settings());if(path.endsWith("/workspaces"))return Response.json({workspaces:[]});throw Error("Unexpected implicit action "+path);};
    let r!:ReactTestRenderer;await act(async()=>{r=create(<WorkspaceApp/>);});
    try{assert.equal(content(r.root).includes("Welcome to Literature Review Engine"),scenario.welcome);assert.equal(calls.some(call=>call.endsWith("/settings/onboarding")),scenario.desktop);assert.ok(calls.every(call=>call.startsWith("GET ")));if(!scenario.welcome)assert.equal(browser.url().search,scenario.url.slice(1));else assert.equal(browser.url().searchParams.get("setupGuide"),"welcome");}finally{await act(async()=>r.unmount());}
  }
});

test("progress read failure leaves ordinary workspaces usable without resetting storage",async()=>{
  storage();browserState("http://127.0.0.1:3000/?page=workspaces");const writes:string[]=[];
  globalThis.fetch=async(input,options)=>{const path=String(input);if(options?.method&&options.method!=="GET")writes.push(path);if(path.endsWith("/session"))return Response.json({csrf_token:"software"});if(path.endsWith("/capabilities"))return Response.json({...capabilities,desktop_onboarding_ready:true});if(path.endsWith("/settings/onboarding"))return Response.json({detail:{code:"onboarding_storage",message:"Setup progress is invalid; research settings are preserved."}},{status:422});if(path.endsWith("/settings"))return Response.json(settings());if(path.endsWith("/workspaces"))return Response.json({workspaces:[]});throw Error("Unexpected request "+path);};let r!:ReactTestRenderer;
  await act(async()=>{r=create(<WorkspaceApp/>);});
  try{assert.match(content(r.root),/Setup progress is invalid/);assert.ok(button(r,"Create workspace"));assert.ok(button(r,"Open workspaces"));assert.equal(content(r.root).includes("Welcome to Literature Review Engine"),false);assert.deepEqual(writes,[]);}finally{await act(async()=>r.unmount());}
});

test("actual URL parser restores a guided AI step on refresh and drops unsupported/non-settings guide values",async()=>{
  for(const [query,guided] of [["?page=settings&setupGuide=ai&settingsReturn=compare&board=b&revision=r&paper=p&field=f",true],["?page=settings&setupGuide=unknown&settingsReturn=compare",false],["?page=workspaces&setupGuide=ai",false]] as const){
    storage();const browser=browserState("http://127.0.0.1:3000/"+query);const calls:string[]=[];
    globalThis.fetch=async(input,options)=>{const path=String(input);calls.push((options?.method??"GET")+" "+path);if(path.endsWith("/session"))return Response.json({csrf_token:"software"});if(path.endsWith("/capabilities"))return Response.json({...capabilities,desktop_onboarding_ready:true});if(path.endsWith("/settings/onboarding"))return Response.json(progress("retrieval",true));if(path.endsWith("/settings/retrieval"))return Response.json({packs:[]});if(path.endsWith("/settings"))return Response.json(settings());if(path.endsWith("/workspaces"))return Response.json({workspaces:[]});throw Error("Unexpected request "+path);};
    let r!:ReactTestRenderer;await act(async()=>{r=create(<WorkspaceApp/>);});
    try{assert.equal(r.root.findAllByProps({"aria-label":"Desktop welcome and setup"}).length,guided?1:0);if(guided){assert.equal(r.root.findAllByProps({id:"settings-ai"}).length,1);assert.equal(r.root.findAllByProps({id:"settings-sources"}).length,0);assert.equal(browser.url().searchParams.get("board"),"b");assert.equal(browser.url().searchParams.get("field"),"f");}assert.ok(calls.every(call=>call.startsWith("GET ")));}finally{await act(async()=>r.unmount());}
  }
});

test("an existing desktop research profile without progress is not interrupted by automatic welcome",async()=>{
  storage();const browser=browserState("http://127.0.0.1:3000/?page=workspaces");const calls:string[]=[];
  globalThis.fetch=async(input,options)=>{const path=String(input);calls.push((options?.method??"GET")+" "+path);if(path.endsWith("/session"))return Response.json({csrf_token:"software"});if(path.endsWith("/capabilities"))return Response.json({...capabilities,desktop_onboarding_ready:true});if(path.endsWith("/settings/onboarding"))return Response.json(progress());if(path.endsWith("/settings"))return Response.json(settings());if(path.endsWith("/workspaces"))return Response.json({workspaces:[{id:"existing",question:"Synthetic existing research",created_at:"2026-10-27T00:00:00Z",mode:"saved_example",searches:[],runs:[]}]});throw Error("Unexpected request "+path);};let r!:ReactTestRenderer;
  await act(async()=>{r=create(<WorkspaceApp/>);});
  try{assert.equal(content(r.root).includes("Welcome to Literature Review Engine"),false);assert.ok(button(r,"Synthetic existing research"));assert.equal(browser.url().search,"?page=workspaces");assert.ok(button(r,"Help & setup"));assert.ok(calls.every(call=>call.startsWith("GET ")));}finally{await act(async()=>r.unmount());}
});


test("guided defaults avoid operator boilerplate while ordinary Settings retains its diagnostic information",async()=>{
  storage();const defaults={...settings(),configured:false,status:{...settings().status,pubmed:{state:"Operator configuration",message:"Existing private launch configuration remains effective."}}};
  globalThis.fetch=async(input)=>String(input).endsWith("/session")?Response.json({csrf_token:"software"}):String(input).endsWith("/settings/retrieval")?Response.json({packs:[]}):Response.json(defaults);
  let r!:ReactTestRenderer;await act(async()=>{r=create(<ResearchSettings onReturn={async()=>{}} guided={{section:"sources",pending:false,continueLabel:"Continue",onContinue:async()=>{},onSkip:async()=>{}}}/>);});
  try{const copy=content(r.root);assert.match(copy,/CURRENT PREFERENCES/);assert.match(copy,/These are the current defaults/);assert.doesNotMatch(copy,/CONFIGURATION REVISION|OPERATOR LAUNCH|private launch configuration/);await act(async()=>r.update(<ResearchSettings onReturn={async()=>{}}/>));assert.match(content(r.root),/CONFIGURATION REVISION/);assert.match(content(r.root),/Private launch configuration is unchanged/);}finally{await act(async()=>r.unmount());}
});

test("latest capability failure withholds Core readiness and entered AI/model settings do not establish execution",async()=>{
  storage();const configured={...settings(),credentials:{ai_api_key:true,ncbi_api_key:false},preferences:{...settings().preferences,ai:{...settings().preferences.ai,provider:"openai",model:"synthetic-entered-model",model_revision:"entered-profile"}},status:{...settings().status,ai:{state:"Configuration valid",message:"Entered but not tested."}}};
  globalThis.fetch=async(input,options)=>{assert.ok(!options?.method||options.method==="GET");const url=String(input);if(url.endsWith("/session"))return Response.json({csrf_token:"software"});if(url.endsWith("/capabilities"))throw Error("Synthetic unavailable capability status");if(url.endsWith("/settings/retrieval"))return Response.json({packs:[{label:"Incomplete runtime",state:"runtime_passed",installed:true,dependencies:{state:"available"},runtime:{encoder_executed:true,reranker_executed:false}}]});return Response.json(configured);};
  let r!:ReactTestRenderer;await act(async()=>{r=create(<ObservedSetupSummary/>);});
  try{const copy=content(r.root);assert.match(copy,/Connection status unavailable/);assert.doesNotMatch(copy,/Ready for manual work/);assert.match(copy,/AI assistanceSetup required/);assert.match(copy,/Incomplete runtime · Installed/);assert.doesNotMatch(copy,/Runtime checked/);assert.match(copy,/Sources need indexing/);}finally{await act(async()=>r.unmount());}
});


test("a CPU runtime receipt is historical when the selected device is MPS",async()=>{
  storage();const selected={...settings(),preferences:{...settings().preferences,retrieval:{profile_id:"hybrid_qwen3_06b_rrf_rerank_v1",device:"mps"}}};
  globalThis.fetch=async(input,options)=>{assert.ok(!options?.method||options.method==="GET");const url=String(input);if(url.endsWith("/session"))return Response.json({csrf_token:"software"});if(url.endsWith("/capabilities"))return Response.json(capabilities);if(url.endsWith("/settings/retrieval"))return Response.json({packs:[{label:"Qwen CPU receipt",state:"runtime_passed",installed:true,dependencies:{state:"available"},runtime:{encoder_executed:true,reranker_executed:true,device:"cpu"}}]});return Response.json(selected);};
  let r!:ReactTestRenderer;await act(async()=>{r=create(<ObservedSetupSummary/>);});
  try{const copy=content(r.root);assert.match(copy,/Qwen CPU receipt · Installed/);assert.match(copy,/Historical runtime check on CPU/);assert.match(copy,/selected MPS/);assert.doesNotMatch(copy,/Qwen CPU receipt · Runtime checked/);}finally{await act(async()=>r.unmount());}
});
