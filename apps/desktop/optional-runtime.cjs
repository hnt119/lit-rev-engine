'use strict';
/** The signed app pins executable capsules; user-selected files are never trusted by name. */
const installers=new Set();
const fs=require('node:fs');const path=require('node:path');const {spawnSync,spawn}=require('node:child_process');
function argumentsFor(options,operation){
 const {resources,dataRoot,platform=process.platform,arch=process.arch}=options;
 const target=platform+'-'+arch;
 const python=path.join(resources,platform==='win32'?'python/python.exe':'python/bin/python3.12');
 const helper=path.join(resources,'engine/scripts',operation==='install'?'desktop_runtime_supervisor.py':'install_desktop_optional_runtime.py');
 const catalog=path.join(resources,'app/optional-runtime-catalog.json');
 if(!['darwin-arm64','win32-x64'].includes(target)||!fs.existsSync(python)||!fs.existsSync(helper)||!fs.existsSync(catalog))throw Error('Optional runtime is unavailable for this packaged target.');
 const args=['-I','-B',helper,operation,'--catalog',catalog,'--data-root',dataRoot,'--target',target];
 if(operation==='install'){if(!options.archivePath||!path.isAbsolute(options.archivePath))throw Error('Choose an exact local runtime capsule.');args.push('--archive',options.archivePath);}
 const env={};for(const k of ['SystemRoot','WINDIR','TMP','TEMP','TMPDIR','HOME','USERPROFILE'])if(process.env[k])env[k]=process.env[k];
 env.PYTHONNOUSERSITE='1';env.PYTHONDONTWRITEBYTECODE='1';
 return {python,args,env};
}
function parse(result){let value;try{value=JSON.parse(result.stdout||'');}catch{throw Error('Optional runtime verification did not return a safe status.');}if(result.status!==0||!value||typeof value.state!=='string')throw Error(value?.message||'Optional runtime could not be verified. Core remains available.');return value;}
function status(options){try{const {python,args,env}=argumentsFor(options,'status');return parse(spawnSync(python,args,{env,encoding:'utf8',windowsHide:true,timeout:120000,maxBuffer:65536}));}catch{return {state:'unavailable',message:'No compatible verified optional runtime is active. Core remains available; use the application runtime menu.'};}}
function install(options){const {python,args,env}=argumentsFor(options,'install');return new Promise((resolve,reject)=>{const child=spawn(python,args,{env,windowsHide:true,stdio:['pipe','pipe','ignore']});installers.add(child);child.stdin.on('error',()=>{});let text='';const timeout=setTimeout(()=>{child.stdin.end();reject(Error('Optional runtime installation timed out. Core remains available; inspect the recovery guide.'));},300000);child.stdout.on('data',b=>{text+=b.toString();if(text.length>65536){child.stdin.end();reject(Error('Optional runtime returned oversized status.'));}});child.on('error',()=>{installers.delete(child);clearTimeout(timeout);reject(Error('Bundled runtime installer could not start.'));});child.on('exit',code=>{installers.delete(child);clearTimeout(timeout);try{resolve(parse({status:code,stdout:text}));}catch(e){reject(e);}});});}
function cancelAll(){for(const child of installers){try{child.stdin.end();}catch{}}}
module.exports={status,install,cancelAll};
