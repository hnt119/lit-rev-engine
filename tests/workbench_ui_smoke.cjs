/*
 * Run with Node.js 18+: node tests/workbench_ui_smoke.cjs
 * Executes the actual browser asset with a deliberately small DOM/event shim.
 * This checks software behavior; it is not browser layout/security QA, server
 * persistence validation, or a real human judgment of the saved literature.
 * All sessions, ratings and save responses below are synthetic and in memory.
 */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'src/review_workbench/page.py'), 'utf8');
const source = fs.readFileSync(path.join(root, 'src/review_workbench/static/workbench.js'), 'utf8');
class Element {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.events = {}; this.value=''; this.checked=false; this.disabled=false; this.hidden=false; this._text=''; this.className=''; this.classList={toggle:()=>{}}; }
  set textContent(value) { this._text=String(value); this.children=[]; }
  get textContent() { return this._text+this.children.map(c=>c.textContent).join(''); }
  append(...children) { for(const child of children) { this.children.push(child); if(this.tagName==='SELECT' && !this.value && child.tagName==='OPTION') this.value=child.value; } }
  replaceChildren(...children) { this.children=[]; this._text=''; this.append(...children); }
  setAttribute(k,v) { this[k]=v; }
  addEventListener(k,fn) { (this.events[k] ||= []).push(fn); }
  async emit(k) { for(const fn of this.events[k] || []) await fn({preventDefault(){},target:this}); }
  focus() {} scrollIntoView() {}
}
const walk=(root)=>[root,...root.children.flatMap(walk)];
const text='A😀 before DIRECT after';
const passage={id:'p1',rank:1,anchor:{block_id:'block1',start:10,end:16,quote:'DIRECT'},locator:{page:1},record_id:'r',document_id:'d',document_version:1,source_sha256:'hash',blocks_sha256:'blocks',title:'<script>unsafe()</script>',candidate_kind:'title_or_navigation'};
assert.equal(Array.from(text).slice(passage.anchor.start,passage.anchor.end).join(''),'DIRECT');
const packet={packet_id:'a'.repeat(64),binding:{receipt_sha256:'b'.repeat(64)},display_mode:'blinded',limitations:['Saved text only'],questions:[{id:'q1',text:'<img src=x onerror=unsafe()>',components:[{id:'c1',text:'Required component'}]},{id:'q2',text:'Whole?',components:[]}],bundles:[{id:'b1',question_id:'q1',label:'A',passages:[passage]},{id:'b2',question_id:'q1',label:'B',passages:[{...passage,id:'p2'}]},{id:'b3',question_id:'q2',label:'A',passages:[{...passage,id:'p3'}]}],sources:[{id:'s1',title:'Document <b>title</b>',record_id:'r',document_id:'d',document_version:1,source_sha256:'hash',blocks_sha256:'blocks',source_url:'https://example.invalid/source',blocks:[{id:'block1',ordinal:1,text,locator:{page:1}}]}]};
let records=[]; let requests=[]; let fail=false; let reveal=false;
async function boot() {
 const ids=[...html.matchAll(/id="([a-z-]+)"/g)].map(m=>m[1]);
 const elements=Object.fromEntries(ids.map(id=>[id,new Element(['question-select','source-select','assessment-status','supersedes'].includes(id)?'select':'div')]));
 const document={getElementById:id=>elements[id],createElement:t=>new Element(t),createTextNode:t=>{const e=new Element('#text');e.textContent=t;return e},addEventListener(){},hidden:false};
 const fetch=async(url,opts)=>{
   if(url==='/api/session') return {ok:true,json:async()=>({packet,assessments:structuredClone(records),csrf_token:'csrf',reveal_methods:reveal})};
   const draft=JSON.parse(opts.body); requests.push({draft,opts});
   if(fail) return {ok:false,status:400,json:async()=>({error:'Software test failure'})};
   const row={...draft,id:'record-'+(records.length+1),created_at:'2026-10-15T00:00:00+00:00',display_mode:'blinded'};records.push(row);
   return {ok:true,json:async()=>({assessment:row})};
 };
 vm.runInNewContext(source,{document,window:{addEventListener(){}},fetch,TextEncoder,Date,Map,Set,console});
 for(let i=0;i<5;i++) await new Promise(resolve=>setImmediate(resolve));
 assert.equal(elements['load-error'].textContent,'');
 return elements;
}
const input=async(el,value,event='input')=>{el.value=value;await el.emit(event)};
const check=async(el,checked)=>{el.checked=checked;await el.emit('change')};
(async()=>{
 let el=await boot();
 assert.equal(el['question-text'].textContent,packet.questions[0].text);
 assert.match(el.passages.textContent,/Title \/ navigation/);
 let ratings=walk(el.passages).filter(n=>n.tagName==='SELECT');
 assert.deepEqual(ratings.map(r=>r.value),['','']);
 await walk(el.passages).find(n=>n.tagName==='BUTTON').emit('click');
 const marks=walk(el['source-blocks']).filter(n=>n.tagName==='MARK');
 assert.equal(marks.length,1);assert.equal(marks[0].textContent,'DIRECT');
 assert.equal(el['source-inspected'].checked,false);
 await input(el.reviewer,'software-ui-test');await input(el['assessment-status'],'sufficient','change');await input(el.reason,'Software fixture only: missing c1.');
 await el['assessment-form'].emit('submit');
 assert.equal(requests.length,0);assert.match(el['save-error'].textContent,/supporting passage/);
 await input(el['assessment-status'],'partial','change');
 await check(walk(el['missing-components']).find(n=>n.tagName==='INPUT'),true);
 await input(ratings[0],'3','change');
 await check(walk(el.passages).find(n=>n.tagName==='INPUT'),true);
 await check(el['source-inspected'],true); await check(el.contradiction,true);
 await el['assessment-form'].emit('submit');
 assert.equal(requests.length,1);const first=requests[0];
 assert.equal(first.opts.headers['X-Workbench-CSRF'],'csrf');
 assert.equal(first.draft.ratings[0].rating,3);assert.equal(first.draft.ratings[0].component_ratings.c1,null);
 assert.equal(first.draft.source_inspected,true);assert.equal(first.draft.contradiction,true);
 assert.equal(el['save-button'].disabled,true);assert.match(el['save-result'].textContent,/Saved assessment/);
 await walk(el['assessment-history']).find(n=>n.tagName==='BUTTON').emit('click');
 assert.equal(el.supersedes.value,'record-1');await input(el.reason,'Revised software-only reason');
 await el['assessment-form'].emit('submit');assert.equal(requests[1].draft.supersedes,'record-1');
 assert.equal(records.length,2);
 el=await boot();assert.match(el['assessment-history'].textContent,/CURRENT/);assert.match(el['assessment-history'].textContent,/SUPERSEDED/);assert.match(el['assessment-history'].textContent,/Revised software-only reason/);
 await el['bundle-choices'].children[1].emit('click');
 await input(el.reviewer,'error-case');await input(el['assessment-status'],'uncertain','change');await input(el.reason,'Preserve this reason on failure.');
 fail=true;await el['assessment-form'].emit('submit');
 assert.match(el['save-error'].textContent,/Software test failure/);assert.equal(el.reason.value,'Preserve this reason on failure.');assert.equal(el.reviewer.value,'error-case');assert.equal(el['save-button'].disabled,false);
 await input(el['question-select'],'q2','change');
 assert.match(el['missing-components'].textContent,/whole_question/);
 await input(el['question-select'],'q1','change');await el['bundle-choices'].children[1].emit('click');assert.equal(el.reason.value,'Preserve this reason on failure.');
 assert(!walk(el.passages).some(n=>['IMG','SCRIPT'].includes(n.tagName)));
 assert.doesNotMatch(el['selected-bundle'].textContent,/method-software-only/);
 reveal=true;packet.display_mode='revealed';packet.bundles[0].method_key='method-software-only';
 el=await boot();
 assert.match(el['display-mode'].textContent,/Diagnostic reveal enabled/);
 assert.match(el['selected-bundle'].textContent,/method-software-only/);
 assert.match(el.passages.textContent,/Revealed diagnostic details/);
 console.log('PASS: actual JS event flows, null ratings, Unicode source anchor, save, reload history, explicit supersession, error draft preservation, question switching, inert text.');
})().catch(e=>{console.error(e);process.exitCode=1});
