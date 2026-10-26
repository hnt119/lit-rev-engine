'use strict';
const {app,BrowserWindow,dialog,session,shell,utilityProcess,powerMonitor,Menu}=require('electron');
const fs=require('node:fs');const path=require('node:path');const os=require('node:os');
const {externalURL,ownURL,dataRoot,privateDirectory,cleanEnvironment,installationProblem,atomicStatus}=require('./security.cjs');
app.enableSandbox();
const productFile=path.join(__dirname,'product.json');
const product=fs.existsSync(productFile)?JSON.parse(fs.readFileSync(productFile,'utf8')):{name:'Literature Review Engine Desktop Preview',data_name:'LiteratureReviewEngineDesktopPreview',partition:'persist:litrev-desktop-preview',require_installed_location:false};
app.setName(product.name);if(process.platform==='win32'&&product.app_id)app.setAppUserModelId(product.app_id);
const qaIndex=process.argv.indexOf('--qa-data-dir');
let root;
try{root=privateDirectory(dataRoot(os.homedir(),qaIndex<0?null:process.argv[qaIndex+1],{dataName:product.data_name}));app.setPath('userData',privateDirectory(path.join(root,'browser')));}catch{dialog.showErrorBox('Desktop Preview cannot start','Use an ordinary private data directory owned by you. Existing browser-beta data was not opened.');app.exit(1);}
let nativeExportsController;
let window,worker,ready=false,quitting=false,stopped=false,startTimer;
const webPort=43000,apiPort=48765,origin=`http://127.0.0.1:${webPort}`;
const metricsPath=path.join(root,'desktop-status.json');
let status={schema:'litrev.desktop-preview.status.v1',phase:'starting',started_at:new Date().toISOString(),desktop_pid:process.pid,root_isolated:true,developer_path_removed:true};
function saveStatus(extra={}){status={...status,...extra};atomicStatus(root,path.basename(metricsPath),status);}
function fail(message){if(quitting)return;saveStatus({phase:'failed',error:message});dialog.showErrorBox('Desktop Preview stopped',message+' No unrelated listener was stopped. Research data stays outside the app.');app.quit();}
if(!app.requestSingleInstanceLock()){app.exit(0);}else{
app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.focus();}});
app.on('before-quit',event=>{if(stopped)return;event.preventDefault();if(quitting)return;if(window&&!window.isDestroyed()){window.close();return;}quitting=true;nativeExportsController?.cancelAll();try{require('./optional-runtime.cjs').cancelAll?.();}catch{}clearTimeout(startTimer);if(worker){try{worker.postMessage({type:'stop'});}catch{stopped=true;saveStatus({phase:'stopped_after_service_exit'});app.quit();return;}setTimeout(()=>{if(!stopped){try{worker.kill();}catch{}saveStatus({phase:'stopped_forced'});stopped=true;app.quit();}},14000).unref();}else{stopped=true;app.quit();}});
app.on('window-all-closed',()=>app.quit());
app.on('activate',()=>{if(window)window.focus();});
app.whenReady().then(()=>{
const resources=process.resourcesPath;
const installError=installationProblem(process.execPath,{required:product.require_installed_location});if(installError)return fail(installError);
if(!app.isPackaged)return fail('Use the prepared application bundle; this prototype does not invoke developer runtimes.');
privateDirectory(path.join(root,'engine'));
const ownedSession=session.fromPartition(product.partition);
ownedSession.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
ownedSession.setPermissionCheckHandler(()=>false);
ownedSession.webRequest.onBeforeRequest((details,callback)=>callback({cancel:!ownURL(details.url,origin)}));
nativeExportsController=require('./native-exports.cjs').installNativeExports({session:ownedSession,dialog,getWindow:()=>window,origin,resources,dataRoot:root,installRoot:path.resolve(resources,'../..'),downloadsDirectory:app.getPath('downloads')});
let runtimeInstallPending=false;let optionalModule;try{optionalModule=require('./optional-runtime.cjs');}catch(error){if(error.code!=='MODULE_NOT_FOUND')throw error;}
const optionalStatus=()=>optionalModule?optionalModule.status({resources,dataRoot:root}):{state:'unavailable',reason:'This internal preview has no optional-runtime catalog.'};
async function installLibraries(){
 if(runtimeInstallPending||quitting)return;runtimeInstallPending=true;
 try{
  const current=optionalStatus();if(current.state==='unavailable'){dialog.showErrorBox('Optional libraries unavailable',current.message||current.reason||'No reviewed runtime is available for this platform. Core research remains available.');return;}
  const selected=await dialog.showOpenDialog(window,{title:'Select reviewed optional runtime archive',properties:['openFile'],filters:[{name:'Reviewed runtime ZIP',extensions:['zip']}]});if(selected.canceled||selected.filePaths.length!==1)return;
  const confirm=await dialog.showMessageBox(window,{type:'question',buttons:['Cancel','Install libraries'],defaultId:0,cancelId:0,message:'Install optional research libraries outside the application?',detail:'Only a catalog-bound archive is accepted. This does not install models or change a retrieval profile. The current research window stays open. Save your work, then quit and reopen to activate the runtime. Reopening clears backend session keys. Models remain separate explicit installations.'});if(confirm.response!==1)return;
  await optionalModule.install({resources,dataRoot:root,archivePath:selected.filePaths[0]});await dialog.showMessageBox(window,{type:'info',buttons:['Continue research'],message:'Libraries installed outside the application',detail:'The current backend is unchanged. Save your work, then use Quit and reopen the installed app to activate the verified runtime. Re-enter session keys if needed; no models were downloaded.'});
 }catch{if(!quitting)dialog.showErrorBox('Optional runtime was not installed','The archive or private installation failed verification. Existing application, research data and models were preserved. Use the installation guide; no pip or provider fallback runs.');}finally{runtimeInstallPending=false;}
}
const menu=[{label:product.name,submenu:[{role:'about'},{label:'Install optional research libraries…',click:()=>void installLibraries()},{type:'separator'},{role:'quit'}]},{role:'editMenu'},{role:'viewMenu'},{role:'windowMenu'}];Menu.setApplicationMenu(Menu.buildFromTemplate(menu));
const env=cleanEnvironment(process.env,{root,apiPort,webPort});
worker=utilityProcess.fork(path.join(__dirname,'services.cjs'),[resources,root,String(apiPort),String(webPort)],{cwd:path.join(resources,'web/apps/web'),env,stdio:'pipe',serviceName:'Literature Review Engine services'});
// Service output is intentionally not persisted: provider/source text and keys must not become logs.
worker.stdout?.on('data',()=>{});worker.stderr?.on('data',()=>{});
worker.on('message',message=>{
if(message?.type==='failed')return fail(message.code==='port_conflict'?'Desktop ports are in use. Close the other desktop application or free ports43000/48765; existing processes were left alone.':'Packaged services did not become ready. See the installation guide for verified recovery; no system Python/Node fallback is used.');
if(message?.type==='stopped'){stopped=true;saveStatus({phase:'stopped'});app.quit();return;}
if(message?.type!=='ready'||ready||quitting)return;
ready=true;clearTimeout(startTimer);saveStatus({phase:'ready',...message,app:undefined,chrome:process.versions.chrome,electron:process.versions.electron,node:message.node,startup_ms:Date.now()-Date.parse(status.started_at)});
window=new BrowserWindow({title:product.name,width:1440,height:1000,minWidth:840,minHeight:600,show:false,webPreferences:{session:ownedSession,sandbox:true,contextIsolation:true,nodeIntegration:false,webSecurity:true,allowRunningInsecureContent:false}});
window.webContents.setWindowOpenHandler(({url})=>{if(ownURL(url,origin)&&new URL(url).pathname==='/license'&&!new URL(url).search){const about=new BrowserWindow({title:'MIT license & about',parent:window,width:800,height:750,webPreferences:{session:ownedSession,sandbox:true,contextIsolation:true,nodeIntegration:false,webSecurity:true}});about.webContents.setWindowOpenHandler(({url:link})=>{const allowed=externalURL(link);if(allowed)void shell.openExternal(allowed);return {action:'deny'};});about.webContents.on('will-navigate',(event,link)=>{if(link===origin+'/'){event.preventDefault();about.close();window?.focus();return;}if(link!==origin+'/license'){event.preventDefault();const allowed=externalURL(link);if(allowed)void shell.openExternal(allowed);}});void about.loadURL(origin+'/license');return {action:'deny'};}const allowed=externalURL(url);if(allowed)void shell.openExternal(allowed);return {action:'deny'};});
window.webContents.on('will-navigate',(event,url)=>{if(!ownURL(url,origin)){event.preventDefault();const allowed=externalURL(url);if(allowed)void shell.openExternal(allowed);}});
window.webContents.on('will-redirect',(event,url)=>{if(!ownURL(url,origin))event.preventDefault();});
window.webContents.on('will-prevent-unload',event=>{const answer=dialog.showMessageBoxSync(window,{type:'warning',buttons:['Keep editing','Discard unsaved input and continue'],defaultId:0,cancelId:0,message:'Unsaved research input remains',detail:'Saved research is retained. Keep this window open to finish saving, or explicitly discard only the unsaved input.'});if(answer===1)event.preventDefault();});
window.webContents.on('render-process-gone',()=>fail('The desktop window stopped unexpectedly. Quit and reopen; retained data remains separate from the app.'));
window.once('ready-to-show',()=>{window.show();saveStatus({window_visible_ms:Date.now()-Date.parse(status.started_at)});});
window.on('closed',()=>{window=null;app.quit();});
void window.loadURL(origin);
const memoryTimer=setInterval(()=>{if(!quitting)saveStatus({memory_observed_at:new Date().toISOString(),process_memory:app.getAppMetrics().map(value=>({pid:value.pid,type:value.type,working_set_kib:value.memory.workingSetSize,private_bytes_kib:value.memory.privateBytes}))});},5000);memoryTimer.unref();
powerMonitor.on('resume',()=>{if(!quitting&&worker)worker.postMessage({type:'resume'});});
});
worker.on('exit',code=>{worker=null;if(quitting){stopped=true;saveStatus({phase:'stopped',service_exit_code:code});app.quit();}else fail('An owned service stopped. Reopen the Desktop Preview after it closes; it will refuse unidentified listeners.');});
startTimer=setTimeout(()=>fail('Startup did not finish within90seconds. No browser-beta workspace was opened.'),90000);
saveStatus({service_pid:worker.pid});
}).catch(()=>fail('The packaged application could not initialize.'));
}
