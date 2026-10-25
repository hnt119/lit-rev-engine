'use strict';
const fs=require('node:fs');const path=require('node:path');const net=require('node:net');const http=require('node:http');
const {spawn,spawnSync}=require('node:child_process');
const [resources,root,apiText,webText]=process.argv.slice(2);const apiPort=Number(apiText),webPort=Number(webText);
let python,pythonExited=false,stopping=false,nextStarted=false;
const notify=value=>process.parentPort?.postMessage(value);
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function available(port){return new Promise((resolve,reject)=>{const s=net.createServer();s.once('error',reject);s.listen(port,'127.0.0.1',()=>s.close(resolve));});}
function owned(pid,port){const result=spawnSync('/usr/sbin/lsof',['-nP','-a','-p',String(pid),`-iTCP@127.0.0.1:${port}`,'-sTCP:LISTEN','-F','pn'],{encoding:'utf8',timeout:2500});const rows=(result.stdout||'').split('\n');return result.status===0&&rows.includes('p'+pid)&&rows.includes(`n127.0.0.1:${port}`);}
function health(port,route,expected){return new Promise(resolve=>{const req=http.get({host:'127.0.0.1',port,path:route,headers:{Host:`127.0.0.1:${port}`},timeout:2000},res=>{let body='';res.on('data',chunk=>{body+=chunk;if(body.length>1024)req.destroy();});res.on('end',()=>{try{resolve(res.statusCode===200&&JSON.stringify(JSON.parse(body))===JSON.stringify(expected));}catch{resolve(false);}});});req.on('error',()=>resolve(false));req.on('timeout',()=>{req.destroy();resolve(false);});});}
async function stop(){if(stopping)return;stopping=true;if(python&&!pythonExited&&python.exitCode===null&&python.signalCode===null){try{process.kill(-python.pid,'SIGTERM');}catch{}const until=Date.now()+11000;while(!pythonExited&&python.exitCode===null&&python.signalCode===null&&Date.now()<until)await delay(50);if(!pythonExited&&python.exitCode===null&&python.signalCode===null){try{process.kill(-python.pid,'SIGKILL');}catch{}}}notify({type:'stopped'});setTimeout(()=>process.exit(0),50);}
process.parentPort?.on('message',event=>{if(event.data?.type==='stop')void stop();if(event.data?.type==='resume'&&!stopping)void (async()=>{if(!owned(python.pid,apiPort)||!owned(process.pid,webPort)||!await health(apiPort,'/readyz',{ready:true})||!await health(webPort,'/healthz',{status:'ok'})){notify({type:'failed',code:'resume_failed'});await stop();}})();});
process.on('SIGTERM',()=>void stop());process.on('SIGINT',()=>void stop());
(async()=>{try{
await available(apiPort);await available(webPort);
const pythonPath=path.join(resources,'python/bin/python3.12');
if(!fs.existsSync(pythonPath))throw Error('missing_runtime');
python=spawn(pythonPath,['-B',path.join(resources,'engine/scripts/desktop_backend.py'),String(process.pid)],{cwd:path.join(resources,'engine'),env:process.env,detached:true,stdio:['ignore','ignore','ignore']});
python.once('exit',()=>{pythonExited=true;if(!stopping){notify({type:'failed',code:'backend_stopped'});void stop();}});
python.once('error',()=>{notify({type:'failed',code:'backend_stopped'});void stop();});
process.chdir(path.join(resources,'web/apps/web'));
require(path.join(resources,'web/apps/web/server.js'));nextStarted=true;
const until=Date.now()+80000;
while(!stopping&&Date.now()<until){
if(pythonExited||python.exitCode!==null||python.signalCode!==null)throw Error('backend_stopped');
if(owned(python.pid,apiPort)&&owned(process.pid,webPort)&&await health(apiPort,'/readyz',{ready:true})&&await health(webPort,'/healthz',{status:'ok'})){
if(!owned(python.pid,apiPort)||!owned(process.pid,webPort))throw Error('ownership_changed');
notify({type:'ready',api_pid:python.pid,web_pid:process.pid,api_port:apiPort,web_port:webPort,node:process.versions.node,python:'CPython3.12.15+20261021',runtimes:'packaged',model_downloads:0});return;
}await delay(150);
}if(!stopping)throw Error('readiness_timeout');
}catch(error){notify({type:'failed',code:error.code==='EADDRINUSE'?'port_conflict':'startup_failed'});await stop();}})();
