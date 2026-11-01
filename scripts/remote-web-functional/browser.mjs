// Public functional candidate. No strict-J01 helper, API seeding, or dialog shims.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE);
const [root, phase] = process.argv.slice(2);
const question = 'Remote functional software QA';
const qa = 'SOFTWARE QA ONLY: public-source workflow check';
const reason = 'Software fixture, not participant judgment or scientific support.';
const profile = path.join(root, 'profile');
const origin = 'http://127.0.0.1:31882';
const status = pid => Object.fromEntries(fs.readFileSync(`/proc/${pid}/status`, 'utf8').split('\n').filter(x=>x.includes(':')).map(x=>{const i=x.indexOf(':');return [x.slice(0,i),x.slice(i+1).trim()]}));
const ns = (pid, kind) => fs.readlinkSync(`/proc/${pid}/ns/${kind}`);
function processes() {
  return fs.readdirSync('/proc').filter(x=>/^\d+$/.test(x)).flatMap(x=>{try {
    return [{pid:Number(x), exe:fs.readlinkSync(`/proc/${x}/exe`), args:fs.readFileSync(`/proc/${x}/cmdline`,'utf8').split('\0'), status:status(x)}];
  } catch {return []}});
}
const pause = ms => new Promise(r=>setTimeout(r,ms));
async function gate(page) {
  await page.goto('chrome://sandbox', {waitUntil:'domcontentloaded'});
  const rows = await page.locator('tr').allTextContents();
  const has = re => rows.some(r=>re.test(r.replace(/\s+/g,' ').trim()));
  assert(has(/^(Namespace sandbox|PID namespaces)\s+Yes\b/i));
  assert(has(/^Network namespaces\s+Yes\b/i));
  assert(has(/^Seccomp-BPF sandbox\s+Yes\b/i));
  await page.setContent('<title>Sandbox probe</title><p>public diagnostic</p>');
  let ok=false, rendererCount=0;
  for(let i=0;i<40&&!ok;i++) {
    const all=processes();
    const main=all.find(p=>p.exe==='/opt/google/chrome/chrome' && p.args.includes(`--user-data-dir=${profile}`) && !p.args.some(a=>a.startsWith('--type=')));
    if(main) {
      const descendants = p=>{let cur=p; for(let j=0;j<20&&cur;j++){if(cur.pid===main.pid)return true;cur=all.find(x=>x.pid===Number(cur.status.PPid));}return false;};
      const family=all.filter(descendants);
      const owned=family.map(p=>({pid:p.pid,start:fs.readFileSync(`/proc/${p.pid}/stat`,'utf8').split(') ')[1].split(' ')[19]}));
      fs.writeFileSync(path.join(root,phase+'.owned.json'),JSON.stringify(owned),{mode:0o600});
      const bad=family.some(p=>p.args.some(a=>['--no-sandbox','--disable-setuid-sandbox','--disable-seccomp-filter-sandbox','--disable-namespace-sandbox','--single-process','--no-zygote'].includes(a)));
      rendererCount=family.filter(p=>p.args.includes('--type=renderer')).length;
      const renderer=family.find(p=>p.args.includes('--type=renderer') && p.status.Seccomp==='2' && Number(p.status.Seccomp_filters)>Number(main.status.Seccomp_filters) && ns(p.pid,'user')!==ns(main.pid,'user') && ns(p.pid,'pid')!==ns(main.pid,'pid'));
      ok=!bad && Boolean(renderer) && main.args.includes('--remote-debugging-pipe');
    }
    if(!ok)await pause(250);
  }
  assert(ok);
  await page.setContent(`<button>Probe confirm</button><output>pending</output><script>document.querySelector('button').onclick=()=>document.querySelector('output').textContent=String(confirm('REMOTE_FUNCTIONAL_CONFIRM'))</script>`);
  assert(await page.evaluate(()=>Function.prototype.toString.call(window.confirm).includes('[native code]')));
  for(const accept of [false,true]) {
    const pending=page.waitForEvent('dialog',{timeout:10000});
    const clicked=page.getByRole('button',{name:'Probe confirm'}).click();
    const d=await pending; assert.equal(d.type(),'confirm');assert.equal(d.message(),'REMOTE_FUNCTIONAL_CONFIRM');
    if(accept)await d.accept();else await d.dismiss();
    await clicked; assert.equal(await page.locator('output').innerText(),String(accept));
  }
  return {chrome_sandbox_report:true, renderer_namespace_distinct:true, renderer_extra_filter:true, pipe:true, native_confirm:true, cancel_false:true, confirm_true:true, renderer_count:rendererCount};
}
function allowed(url, method) {
  let u;try {u=new URL(url)} catch {return false}
  if(u.origin!==origin)return false;
  if(method==='GET'||method==='HEAD')return true;
  if(method==='POST')return u.pathname==='/api/v1/workspaces'||/^\/api\/v1\/workspaces\/[^/]+\/(searches|source-preparations|preparation-jobs|boards)$/.test(u.pathname)||/^\/api\/v1\/workspaces\/[^/]+\/boards\/[^/]+\/cell-revisions$/.test(u.pathname);
  if(method==='PUT')return /^\/api\/v1\/workspaces\/[^/]+\/drafts\/[^/]+$/.test(u.pathname)||/^\/api\/v1\/workspaces\/[^/]+\/boards\/[^/]+\/drafts\/[^/]+\/[^/]+$/.test(u.pathname);
  return false;
}
let context;
let stage='gate';
try {
  assert(['drive','reopen'].includes(phase));
  if(phase==='drive'){assert(!fs.existsSync(profile));fs.mkdirSync(profile,{mode:0o700});}
  else assert(fs.statSync(profile).isDirectory());
  context=await chromium.launchPersistentContext(profile,{executablePath:'/opt/google/chrome/chrome',chromiumSandbox:true,headless:true,timeout:30000,acceptDownloads:true,downloadsPath:path.join(root,'downloads'),viewport:{width:1280,height:900}});
  const page=context.pages()[0]??await context.newPage();page.setDefaultTimeout(20000);
  const checks=await gate(page);
  // Persistent contexts need not expose a Browser object. Browser.getVersion
  // is available through a Chromium page CDP session without another launch.
  const cdp=await context.newCDPSession(page);
  const product=(await cdp.send('Browser.getVersion')).product;
  await cdp.detach();
  const version=/^Chrome\/([0-9.]{1,64})$/.exec(product)?.[1];assert(version);
  const gateReceipt={version,...checks};
  fs.writeFileSync(path.join(root,phase+'.gate.json'),JSON.stringify(gateReceipt),{mode:0o600,flag:'wx'});
  stage='journey';
  await context.route('**/*',route=>allowed(route.request().url(),route.request().method())?route.continue():route.abort('blockedbyclient'));
  await page.goto(origin);const button=name=>page.getByRole('button',{name,exact:true});
  const cells=page.locator('.board-cell');
  const target=page.getByRole('button',{name:/^Population for Influences of dietary intake on Chinese women/});
  async function download(name){for(const [format,label] of [['json','Download board audit JSON'],['csv','Download board CSV']]){const pending=page.waitForEvent('download');await page.getByRole('link',{name:label,exact:true}).click();const dl=await pending;assert.equal(dl.suggestedFilename(),`comparison-board.${format}`);await dl.saveAs(path.join(root,'downloads',`${name}.${format}`));assert.equal(await dl.failure(),null);}}
  async function submitted(){await target.waitFor();assert.equal(await cells.count(),9);assert.equal(await cells.filter({hasText:'Not yet submitted'}).count(),8);assert((await target.innerText()).includes(qa));await target.click();}
  if(phase==='drive') {
    await page.getByText('No workspaces in this browser session yet.',{exact:true}).waitFor();
    assert(await page.locator('select option[value="live"]').isDisabled());
    await page.getByLabel('Research question',{exact:true}).fill(question);await button('Create workspace').click();
    await button('Import papers').click();
    let importPosts=0;
    page.on('request', request=>{if(request.method()==='POST' && /\/imports(?:\/|$)/.test(new URL(request.url()).pathname))importPosts++;});
    await page.getByLabel('Citation file',{exact:true}).setInputFiles({name:'dialog-probe.csv',mimeType:'text/csv',buffer:Buffer.from('Title,PMID\nDisposable software QA fixture,42051515\n')});
    await button('Browse collections').click();
    const discard=button('Discard unfinished intake changes…');await discard.waitFor();
    for(const accept of [false,true]) {
      const pending=page.waitForEvent('dialog',{timeout:10000});
      const clicked=discard.click();const d=await pending;
      assert.equal(d.type(),'confirm');assert.equal(d.message(),'Discard the unfinished local intake changes described here? Saved imports and collections remain retained.');
      if(accept)await d.accept();else await d.dismiss();await clicked;
      if(!accept){assert((await page.getByLabel('Citation file',{exact:true}).inputValue()).endsWith('dialog-probe.csv'));await discard.waitFor();}
      else assert.equal(await page.getByLabel('Citation file',{exact:true}).inputValue(),'');
    }
    assert.equal(importPosts,0);
    Object.assign(gateReceipt,{app_cancel_retained:true,app_confirm_cleared:true,no_import_post:true});
    fs.writeFileSync(path.join(root,phase+'.gate.json'),JSON.stringify(gateReceipt),{mode:0o600});
    await button('Search papers').click();
    await button('Open saved example').click();
    for(const pmid of ['42051515','42683105','42196995'])await page.locator('article.paper').filter({hasText:'PMID '+pmid}).getByRole('checkbox',{name:/Select for exploration/}).check();
    await button('Prepare & compare (3)').click();
    const form=page.getByRole('region',{name:'New comparison board',exact:true});
    await Promise.race([form.waitFor(),button('Continue to comparison (3)').waitFor()]);
    if(await button('Continue to comparison (3)').isVisible())await button('Continue to comparison (3)').click();
    await form.waitFor();
    await form.getByText('Advanced · retrieval profile and component queries',{exact:true}).click();
    await form.getByLabel('Retrieval profile for this definition',{exact:true}).selectOption('legacy_block_prefix_v1');
    await form.getByRole('button',{name:'Create comparison board',exact:true}).click();
    await target.waitFor();assert.equal(await cells.count(),9);assert.equal(await cells.filter({hasText:'Not yet submitted'}).count(),9);
    await target.click();await button('Browse this source').click();assert((await page.locator('.source-text').first().innerText()).length>0);
    await button('I have read this excerpt — use it').click();
    await page.getByLabel('Manual cell value',{exact:true}).fill(qa);await page.getByLabel('Reason',{exact:true}).fill(reason);
    assert.equal(await page.getByLabel('Human support judgment',{exact:true}).inputValue(),'unassessed');
    assert.equal(await page.getByLabel('Inspected scope result',{exact:true}).inputValue(),'not_assessed');
    await page.getByRole('region',{name:'Population cell editor'}).getByText('Draft: saved',{exact:true}).waitFor();
    await page.reload();await page.getByLabel('Manual cell value',{exact:true}).waitFor();assert.equal(await page.getByLabel('Manual cell value',{exact:true}).inputValue(),qa);assert.equal(await page.getByLabel('Reason',{exact:true}).inputValue(),reason);assert.equal(await cells.filter({hasText:'Not yet submitted'}).count(),9);
    await button('Review entry before saving').click();await button('Save reviewed entry').click();await page.getByText('Saved to comparison.',{exact:true}).waitFor();
    await download('before');
  } else {
    await button('Workspaces').click();await button(question).click();await button('Comparison board').click();await button('Open comparison board').click();
    await submitted();await button('3. Review & save').click();await page.getByText(qa,{exact:true}).first().waitFor();await download('after');
  }
  await context.close();context=null;
  fs.writeFileSync(path.join(root,phase+'.ok'),'ok',{mode:0o600,flag:'wx'});
} catch {process.exitCode=stage==='gate'?2:3;} finally {if(context)await context.close().catch(()=>{});}
