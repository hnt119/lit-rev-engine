'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');const os=require('node:os');const {EventEmitter}=require('node:events');
const source=path.resolve(__dirname,'../../apps/desktop');
test('research and license windows use the exact hardened owned Session object',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'litrev-desktop-window-policy-'));const windows=[];let worker;const sessions=new Map();const app=new EventEmitter();
 Object.assign(app,{enableSandbox(){},setName(){},setPath(){},requestSingleInstanceLock:()=>true,whenReady:()=>Promise.resolve(),isPackaged:true,quit(){},exit(){},getPath:()=>root,getAppMetrics:()=>[]});
 const policy={setPermissionRequestHandler(fn){this.permission=fn;},setPermissionCheckHandler(fn){this.check=fn;},webRequest:{onBeforeRequest(fn){policy.requests=fn;}},on(event,fn){if(event==='will-download')this.download=fn;}};
 class Window extends EventEmitter{constructor(options){super();this.options=options;this.webContents=new EventEmitter();this.webContents.session=options.webPreferences.session;this.webContents.setWindowOpenHandler=fn=>{this.open=fn;};windows.push(this);}loadURL(){return Promise.resolve();}show(){}focus(){}close(){}isDestroyed(){return false;}}
 const electron={app,BrowserWindow:Window,dialog:{showErrorBox(){assert.fail('Unexpected native startup failure');},showMessageBoxSync:()=>0},session:{fromPartition(name){sessions.set(name,policy);return policy;}},shell:{openExternal(){assert.fail('No citation opening expected');}},utilityProcess:{fork(){worker=new EventEmitter();worker.stdout=new EventEmitter();worker.stderr=new EventEmitter();worker.pid=1234;return worker;}},powerMonitor:new EventEmitter(),Menu:{buildFromTemplate:x=>x,setApplicationMenu(){}}};
 const security={atomicStatus(){},externalURL:()=>null,ownURL:u=>u.startsWith('http://127.0.0.1:43000/'),dataRoot:()=>root,privateDirectory:p=>{fs.mkdirSync(p,{recursive:true});return p;},cleanEnvironment:()=>({}),installationProblem:()=>null};
 const optional={status:()=>({state:'unavailable',message:'No target in this software fixture'}),cancelAll(){}};
 const context={require(name){if(name==='electron')return electron;if(name==='./security.cjs')return security;if(name==='./optional-runtime.cjs')return optional;if(name==='./native-exports.cjs')return {installNativeExports(options){assert.equal(options.session,policy);policy.download=()=>{};return {cancelAll(){}};}};return require(name);},__dirname:source,process:{argv:['fixture'],pid:123,execPath:'/Applications/Literature Review Engine.app/Contents/MacOS/LiteratureReviewEngine',resourcesPath:'/synthetic/Resources',platform:'darwin',env:{},versions:{chrome:'fixture',electron:'fixture',node:'fixture'}},console,setTimeout:()=>({unref(){}}),clearTimeout(){},setInterval:()=>({unref(){}}),Date,URL};
 try{
  vm.runInNewContext(fs.readFileSync(path.join(source,'main.cjs'),'utf8'),context);await new Promise(resolve=>setImmediate(resolve));assert.ok(worker);worker.emit('message',{type:'ready',node:'fixture'});
  assert.equal(windows.length,1);const main=windows[0];assert.equal(sessions.size,1);assert.ok(sessions.has('persist:litrev-desktop'));
  assert.equal(main.webContents.session,policy);assert.equal(main.options.webPreferences.sandbox,true);assert.equal(main.options.webPreferences.nodeIntegration,false);assert.equal(main.options.webPreferences.contextIsolation,true);assert.equal(policy.check(),false);
  let approved;policy.permission(null,'camera',value=>{approved=value;});assert.equal(approved,false);let response;policy.requests({url:'https://outside.invalid/'},v=>{response=v;});assert.equal(response.cancel,true);
  main.open({url:'http://127.0.0.1:43000/license'});assert.equal(windows.length,2);assert.equal(windows[1].webContents.session,policy);assert.equal(windows[1].options.webPreferences.sandbox,true);
  assert.equal(typeof policy.download,'function');
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
