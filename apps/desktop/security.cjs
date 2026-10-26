'use strict';
const path=require('node:path');
const fs=require('node:fs');
const os=require('node:os');const crypto=require('node:crypto');const {spawnSync}=require('node:child_process');
const ALLOWED_EXTERNAL=new Set(['pubmed.ncbi.nlm.nih.gov','pmc.ncbi.nlm.nih.gov','europepmc.org','doi.org','www.ncbi.nlm.nih.gov','api-docs.deepseek.com','developers.openai.com','platform.openai.com','github.com','huggingface.co','creativecommons.org','opensource.org']);
function externalURL(value){try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&!u.port&&ALLOWED_EXTERNAL.has(u.hostname)?u.href:null;}catch{return null;}}
function ownURL(value,origin){try{const u=new URL(value);return u.origin===origin&&!u.username&&!u.password;}catch{return false;}}
function dataRoot(home,qa,{platform=process.platform,localAppData=process.env.LOCALAPPDATA,dataName='LiteratureReviewEngineDesktopPreview'}={}){
 const normal=platform==='win32'?path.win32.join(localAppData||'',dataName):path.join(home,'Library','Application Support',dataName);
 if(platform==='win32'&&(!localAppData||!path.win32.isAbsolute(localAppData)||localAppData.startsWith('\\\\')))throw Error('Windows desktop requires a private local LOCALAPPDATA directory.');
 if(!qa)return normal;
 const resolved=path.resolve(qa),prefix=path.join(platform==='win32'?os.tmpdir():'/private/tmp','litrev-desktop-qa-');
 if(!resolved.startsWith(prefix)||resolved.includes('\0')||resolved.includes('..'))throw Error('Desktop QA requires a new dedicated temporary directory.');return resolved;
}
function pythonPath(resources,platform=process.platform){return path.join(resources,platform==='win32'?'python/python.exe':'python/bin/python3.12');}
function privateDirectory(directory,{resources=process.resourcesPath,platform=process.platform}={}){
 if(platform==='win32'){
  const py=pythonPath(resources,platform),helper=path.join(resources,'engine/scripts/desktop_backend.py');
  if(!fs.existsSync(py)||!fs.existsSync(helper))throw Error('The packaged Windows security runtime is missing. Reinstall the application.');
  const result=spawnSync(py,['-B',helper,'--private-directory',directory],{cwd:path.join(resources,'engine'),env:cleanEnvironment(process.env,{root:directory,apiPort:48765,webPort:43000,platform}),windowsHide:true,encoding:'utf8',timeout:10000});
  if(result.status!==0)throw Error('Windows private storage requires an owned local NTFS directory without links; no permissive fallback is used.');return directory;
 }
 const absolute=path.resolve(directory);let current=path.parse(absolute).root;
 for(const part of absolute.slice(current.length).split(path.sep)){current=path.join(current,part);if(fs.existsSync(current)&&fs.lstatSync(current).isSymbolicLink())throw Error('Desktop data/profile paths cannot be symbolic links.');}
 fs.mkdirSync(absolute,{recursive:true,mode:0o700});const info=fs.statSync(absolute);if(!info.isDirectory()||info.uid!==process.getuid())throw Error('Desktop data must be owned by the current user.');fs.chmodSync(absolute,0o700);return absolute;
}
function atomicStatus(directory,filename,value){
 privateDirectory(directory);
 if(path.basename(filename)!==filename)throw Error('Status filename must remain inside its owned directory.');
 const destination=path.join(directory,filename);
 try{if(!fs.lstatSync(destination).isFile()||fs.lstatSync(destination).isSymbolicLink())throw Error('Unsafe status destination.');}catch(error){if(error.code!=='ENOENT')throw error;}
 const temporary=path.join(directory,'.status-'+crypto.randomBytes(16).toString('hex')+'.tmp');let fd;
 try{fd=fs.openSync(temporary,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|(fs.constants.O_NOFOLLOW||0),0o600);fs.writeFileSync(fd,JSON.stringify(value,null,2)+'\n');fs.fsyncSync(fd);fs.closeSync(fd);fd=undefined;fs.renameSync(temporary,destination);}finally{if(fd!==undefined)fs.closeSync(fd);try{fs.unlinkSync(temporary);}catch(error){if(error.code!=='ENOENT')throw error;}}
}
function cleanEnvironment(inherited,{root,apiPort,webPort,platform=process.platform}){
 const out={};for(const key of ['HOME','USER','LOGNAME','TMPDIR','LANG','LC_ALL','LC_CTYPE',...(platform==='win32'?['SystemRoot','WINDIR','TEMP','TMP','USERPROFILE','LOCALAPPDATA','USERNAME','HOMEDRIVE','HOMEPATH']:[])])if(inherited[key])out[key]=inherited[key];
 const system=out.SystemRoot||out.WINDIR;
 if(platform==='win32'&&(!system||!path.win32.isAbsolute(system)))throw Error('Windows system directory is unavailable; reinstall or repair the operating-system environment.');
 return {...out,PATH:platform==='win32'?path.win32.join(system,'System32'):'/usr/bin:/bin:/usr/sbin:/sbin',NODE_ENV:'production',NEXT_TELEMETRY_DISABLED:'1',PYTHONNOUSERSITE:'1',PYTHONDONTWRITEBYTECODE:'1',MVP_DEPLOYMENT_MODE:'local',MVP_WEB_DATA_DIR:path.join(root,'engine'),MVP_API_HOST:`127.0.0.1:${apiPort}`,MVP_API_ORIGIN:`http://127.0.0.1:${apiPort}`,MVP_WEB_ORIGIN:`http://127.0.0.1:${webPort}`,MVP_MAP_ENABLED:'0',MVP_SEARCH_PLANNER_ENABLED:'0',MVP_PROPOSALS_ENABLED:'0',MVP_SEARCH_PLANNER_SPEND_CAP_USD:'0',MVP_PROPOSALS_SPEND_CAP_USD:'0',HF_HUB_OFFLINE:'1',TRANSFORMERS_OFFLINE:'1',HF_HUB_DISABLE_TELEMETRY:'1',HOSTNAME:'127.0.0.1',PORT:String(webPort),LITREV_DESKTOP_RUNTIME_MODE:'managed',LITREV_RETRIEVAL_CACHE:path.join(root,'models','retrieval'),HF_HOME:path.join(root,'models','huggingface'),HF_HUB_CACHE:path.join(root,'models','huggingface','hub'),XDG_CACHE_HOME:path.join(root,'cache')};
}
function installationProblem(executable,{platform=process.platform,home=os.homedir(),required=false}={}){
 if(platform!=='darwin'||!required)return null;
 const actual=fs.realpathSync(executable),app=actual.split('.app/Contents/MacOS/')[0]+'.app';
 if(actual.includes('/AppTranslocation/')||actual.startsWith('/Volumes/'))return 'Drag Literature Review Engine.app into Applications, eject the disk image, then open the installed copy. Do not disable Gatekeeper.';
 if(!app.startsWith('/Applications/')&&!app.startsWith(path.join(home,'Applications')+path.sep))return 'Install the application in Applications (or your own Applications folder) before opening it. The source and internal preview remain separate.';
 return null;
}
module.exports={externalURL,ownURL,dataRoot,privateDirectory,cleanEnvironment,pythonPath,installationProblem,atomicStatus};
