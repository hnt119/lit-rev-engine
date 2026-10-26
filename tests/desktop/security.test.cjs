'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const {externalURL,ownURL,dataRoot,cleanEnvironment,atomicStatus}=require('../../apps/desktop/security.cjs');
test('external citations use fixed HTTPS hosts only',()=>{assert.equal(externalURL('https://doi.org/10.1/test'),'https://doi.org/10.1/test');for(const value of ['file:///etc/passwd','javascript:alert(1)','https://doi.org.evil.test/','http://doi.org/','https://key@doi.org/','https://doi.org:444/'])assert.equal(externalURL(value),null);});
test('renderer navigation stays on its owned exact origin',()=>{for(const value of ['http://127.0.0.1:43001/','http://localhost:43000/','https://evil.test/','file:///'])assert.equal(ownURL(value,'http://127.0.0.1:43000'),false);assert.equal(ownURL('http://127.0.0.1:43000/?page=compare','http://127.0.0.1:43000'),true);});
test('desktop data root cannot reuse browser beta or pilot by a QA override',()=>{assert.ok(dataRoot('/private/home').endsWith('LiteratureReviewEngineDesktopPreview'));assert.throws(()=>dataRoot('/private/home','/private/tmp/not-dedicated'));assert.throws(()=>dataRoot('/private/home','/private/tmp/litrev-desktop-qa-x/../../sensitive'));assert.equal(dataRoot('/private/home','/private/tmp/litrev-desktop-qa-fixture'),'/private/tmp/litrev-desktop-qa-fixture');});
test('packaged runtime environment strips inherited providers hosted settings and developer paths',()=>{const value=cleanEnvironment({PATH:'/developer/bin',HOME:'/private/fixture',OPENAI_API_KEY:'synthetic',DEEPSEEK_API_KEY:'synthetic',NCBI_EMAIL:'person@example.invalid',PYTHONPATH:'bad',PYTHONHOME:'bad',NODE_OPTIONS:'bad',HTTPS_PROXY:'bad',MVP_DEPLOYMENT_MODE:'hosted',MVP_WEB_DATA_DIR:'/old/database'},{root:'/private/desktop',apiPort:48765,webPort:43000});assert.equal(value.PATH,'/usr/bin:/bin:/usr/sbin:/sbin');assert.equal(value.MVP_DEPLOYMENT_MODE,'local');assert.equal(value.MVP_WEB_DATA_DIR,'/private/desktop/engine');for(const key of ['OPENAI_API_KEY','DEEPSEEK_API_KEY','NCBI_EMAIL','PYTHONPATH','PYTHONHOME','NODE_OPTIONS','HTTPS_PROXY'])assert.equal(value[key],undefined);for(const key of ['MVP_MAP_ENABLED','MVP_SEARCH_PLANNER_ENABLED','MVP_PROPOSALS_ENABLED'])assert.equal(value[key],'0');});

test('native product data roots stay separate from source beta and legacy preview',()=>{
 const native=dataRoot('/private/home',null,{dataName:'LiteratureReviewEngineDesktop'});
 assert.ok(native.endsWith('/LiteratureReviewEngineDesktop'));
 assert.notEqual(native,dataRoot('/private/home'));
 assert.equal(dataRoot('unused',null,{platform:'win32',localAppData:'C:\\Users\\Fixture\\AppData\\Local',dataName:'LiteratureReviewEngineDesktop'}),'C:\\Users\\Fixture\\AppData\\Local\\LiteratureReviewEngineDesktop');
 assert.throws(()=>dataRoot('unused',null,{platform:'win32'}));
 assert.throws(()=>dataRoot('unused',null,{platform:'win32',localAppData:'\\\\server\\share'}));
});
test('Windows core uses system-only DLL path and strips injected research/provider settings',()=>{
 const env=cleanEnvironment({SystemRoot:'C:\\Windows',LOCALAPPDATA:'C:\\Users\\Fixture\\AppData\\Local',PATH:'C:\\developer',OPENAI_API_KEY:'synthetic',PYTHONPATH:'bad',MVP_WEB_DATA_DIR:'old'},{root:'C:\\Users\\Fixture\\AppData\\Local\\LiteratureReviewEngineDesktop',apiPort:48765,webPort:43000,platform:'win32'});
 assert.equal(env.PATH,'C:\\Windows\\System32');assert.equal(env.LITREV_DESKTOP_RUNTIME_MODE,'managed');assert.equal(env.OPENAI_API_KEY,undefined);assert.equal(env.PYTHONPATH,undefined);assert.notEqual(env.MVP_WEB_DATA_DIR,'old');
 assert.throws(()=>cleanEnvironment({},{root:'C:\\data',apiPort:48765,webPort:43000,platform:'win32'}));
});

test('all model caches ignore inherited shared directories',()=>{
 const value=cleanEnvironment({HOME:'/fixture',LITREV_RETRIEVAL_CACHE:'/shared/retrieval',HF_HOME:'/shared/hf',HF_HUB_CACHE:'/shared/hub',XDG_CACHE_HOME:'/shared/cache'},{root:'/isolated/native',apiPort:48765,webPort:43000});
 assert.equal(value.LITREV_RETRIEVAL_CACHE,'/isolated/native/models/retrieval');assert.equal(value.HF_HOME,'/isolated/native/models/huggingface');assert.equal(value.HF_HUB_CACHE,'/isolated/native/models/huggingface/hub');assert.equal(value.XDG_CACHE_HOME,'/isolated/native/cache');
});
test('status writes are private atomic replacements and never follow a status symlink',()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path');const base=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'litrev-status-policy-'))),root=path.join(base,'owned'),external=path.join(base,'unrelated');
 try{fs.writeFileSync(external,'Preserve unrelated data');atomicStatus(root,'status.json',{phase:'ready'});assert.equal(JSON.parse(fs.readFileSync(path.join(root,'status.json'))).phase,'ready');assert.equal(fs.statSync(path.join(root,'status.json')).mode&0o777,0o600);fs.unlinkSync(path.join(root,'status.json'));fs.symlinkSync(external,path.join(root,'status.json'));assert.throws(()=>atomicStatus(root,'status.json',{phase:'stopped'}));assert.equal(fs.readFileSync(external,'utf8'),'Preserve unrelated data');assert.deepEqual(fs.readdirSync(root),['status.json']);}finally{fs.rmSync(base,{recursive:true,force:true});}
});
