/* Offline production-browser software acceptance. Fresh public/synthetic state only.
 * Never upload the private QA directory, cookies, screenshots or source exports.
 * Args: Playwright module directory, loopback origin, fresh QA directory, create|verify.
 */
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{createHash}=require('node:crypto');
const [tools,origin,qa,phase='create']=process.argv.slice(2);
if(!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(origin)||!qa)throw Error('Explicit loopback origin and fresh QA directory required');
const {chromium}=require(tools),hash=x=>createHash('sha256').update(x).digest('hex');
fs.mkdirSync(qa,{recursive:true,mode:0o700});
const record=path.join(qa,'workbench-state.private.json'),cookies=path.join(qa,'browser-state.private.json');
const marker='SOFTWARE QA unsent comment — not a research judgment';
(async()=>{
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,...(process.env.LITREV_CHROME?{executablePath:process.env.LITREV_CHROME}:{})});
 const context=await browser.newContext({viewport:{width:1440,height:1100},reducedMotion:'reduce',acceptDownloads:true,...(phase==='verify'?{storageState:cookies}:{})});
 const started=Date.now(),requests=[],external=[],errors=[],checks=[];
 await context.route('**/*',r=>{const u=new URL(r.request().url());if(u.origin===origin||['data:','blob:','about:'].includes(u.protocol))return r.continue();external.push(u.origin);return r.abort();});
 context.on('request',r=>{const u=new URL(r.url());if(u.pathname.startsWith('/api/'))requests.push({method:r.method(),path:u.pathname});});
 const page=await context.newPage();page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
 const button=(name,p=page)=>p.getByRole('button',{name,exact:true});
 const control=(scope,name,selector='input,textarea,select')=>scope.locator('label').filter({hasText:new RegExp('^'+name)}).locator(selector).first();
 const select=(scope,name)=>control(scope,name,'select');
 const mark=x=>{checks.push(x);console.log(JSON.stringify({browser_step:x}));};
 async function api(method,route,body){return page.evaluate(async({method,route,body})=>{const session=await(await fetch('/api/v1/session')).json();const r=await fetch('/api/v1/'+route,{method,headers:{'Content-Type':'application/json',...(method==='GET'?{}:{'X-CSRF-Token':session.csrf_token})},body:body===undefined?undefined:JSON.stringify(body)});if(!r.ok)throw Error('Fixture HTTP '+r.status+' '+route);return r.json();},{method,route,body});}
 const noWork=()=>requests.filter(r=>r.method==='POST'&&/\/(?:evidence-runs|candidates|source-preparations|propose|proposal-runs|prepare-generation|diagnose|execute|query-suggestions|searches|hybrid-index|hybrid-runs|collection-preparation-jobs|preparation-jobs|map-jobs|install)$/.test(r.path)).length;
 const details=async(text,scope=page)=>{const s=scope.getByText(text,{exact:true});await s.waitFor();if(!await s.evaluate(n=>n.parentElement.open))await s.click();};
 const waitEditor=async()=>{await page.locator('.board-cell-editor').waitFor();await page.locator('.board-cell-editor').getByText('Draft: saved',{exact:true}).waitFor();};
 const waitViews=async()=>{await page.getByRole('region',{name:'Comparison table · scroll horizontally on small screens',exact:true}).waitFor();await page.locator('[aria-label="Evidence views"]').getByText('Draft: saved',{exact:true}).waitFor();await button('Overview').waitFor({state:'visible'});};
 async function showComment(){if(!await page.getByRole('textbox',{name:'Manual cell value',exact:true}).isVisible())await button('2. Comment & judge').click();}
 async function digestExport(state){const result={};for(const f of ['csv','json']){const text=await page.evaluate(async href=>{const r=await fetch(href);if(!r.ok)throw Error('Export failed');return r.text();},'/api/v1/workspaces/'+state.workspace+'/boards/'+state.board+'/exports?'+new URLSearchParams({format:f,revision_id:state.revision}));result[f]=hash(text);}return result;}
 try{
 if(phase==='create'){
  await page.goto(origin,{waitUntil:'domcontentloaded'});await page.getByRole('textbox',{name:'Research question',exact:true}).fill('SOFTWARE QA: microbiome sample sites, reproductive ageing and healthy ageing in Asian women; definitions unresolved.');await button('Create workspace').click();await button('Open saved example').waitFor();
  const workspace=new URL(page.url()).searchParams.get('workspace'),base='workspaces/'+workspace;
  const raw=' \r\n(microbiome[tiab]) AND women[tiab]  \r\n';
  const plan=await api('POST',base+'/search-plans',{request_id:'qa-plan',draft:{original_question:'SOFTWARE QA broad microbiome question; eligibility unresolved.',input_mode:'manual_strategy',manual_strategy:raw}});
  const planId=plan.revision.plan_id,planRevision=plan.revision.revision_id;
  await page.goto(origin+'/?'+new URLSearchParams({page:'discover',workspace,plan:planId}),{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Approve this candidate',exact:true}).waitFor();
  await page.getByRole('checkbox',{name:/Acknowledge that this exact specialist strategy/}).check();await button('Approve this candidate').click();
  await page.getByText(/APPROVED/).first().waitFor();
  const candidate=page.locator('[aria-label^="Compiled candidate:"]');assert.equal(await button('Search papers',candidate).isDisabled(),true);assert.equal(await button('Check matches',candidate).isDisabled(),true);
  const beforeNotes=noWork();await button('Add later extraction question').click();
  const later=page.getByRole('textbox',{name:'Later extraction question 1',exact:true});await later.fill('SOFTWARE QA: Which specimen sites are reported?');await button('Save design notes for this revision').click();
  await page.locator('[aria-label="Search design notes"]').getByText('Draft: saved',{exact:true}).waitFor();
  const download=page.waitForEvent('download');await page.getByRole('link',{name:'Download readable strategy',exact:true}).click();await(await download).saveAs(path.join(qa,'strategy.md'));
  const retained=await api('GET',base+'/search-plans/'+planId);assert.equal(retained.revision.draft.manual_strategy,raw);assert.equal(noWork(),beforeNotes);mark('manual-approved-strategy-notes-export-no-provider');
  // The saved example is deliberately independent of the approved PubMed query.
  const search=await api('POST',base+'/searches',{request_id:'qa-example',query:'saved public example; not an executed PubMed strategy',max_results:30});
  const ids=search.papers.slice(0,3).map(p=>p.id);const prep=await api('POST',base+'/source-preparations',{request_id:'qa-preparation',search_id:search.id,paper_ids:ids});
  const fields=['population','design','specimen','focus','geography'].map(id=>({id,label:id[0].toUpperCase()+id.slice(1),subquestion:'microbiome'}));
  const board=await api('POST',base+'/boards',{schema_version:'mvp.board-profile-request.v2',request_id:'qa-board',preparation_id:prep.id,question:'SOFTWARE QA comparison — three retained public reports, not a systematic review.',paper_ids:ids,fields,retrieval_profile_id:'lexical_spans_v1'});
  const state={workspace,board:board.definition.board_id,revision:board.definition.revision_id,paper:ids[0],field:'population'};
  const tableURL=origin+'/?'+new URLSearchParams({page:'compare',workspace,board:state.board,revision:state.revision});state.tableURL=tableURL;
  const started=noWork();await page.goto(tableURL,{waitUntil:'domcontentloaded'});await waitViews();assert.equal(await page.locator('button[data-board-cell]').count(),15);await button('Overview').click();await page.locator('[aria-label="Evidence views"]').getByText('Draft: saved',{exact:true}).waitFor();assert.equal(noWork(),started);mark('three-paper-five-field-view-no-inference');
  const cell=page.locator('button[data-board-cell]').first();await cell.focus();await page.keyboard.press('Enter');await waitEditor();
  await button('Find excerpts in this paper').click();await button('Read in source · passage 1').click();await button('I have read this excerpt — use it').click();
  const value=page.getByRole('textbox',{name:'Manual cell value',exact:true});await value.waitFor();assert.equal(await value.evaluate(n=>n===document.activeElement),true);
  await value.fill('SOFTWARE QA unassessed source-linked entry');await page.getByRole('textbox',{name:'Reason',exact:true}).fill('Mechanical exercise only; no scientist has judged support.');await button('Review entry before saving').click();await button('Save reviewed entry').click();await page.getByText('Saved to comparison.',{exact:true}).waitFor();mark('excerpt-comment-explicit-save-same-editor');
  await button('Back to table').first().click();await waitViews();
  let profile=page.locator('tbody tr').first().locator('.paper-profile-details');await details('Paper profile & explicit classification',profile);await details('Map a dimension and normalize an existing entry',profile);
  await select(profile,'Dimension').selectOption('specimen');await select(profile,'Existing scientific field').selectOption('population');await control(profile,'Dimension definition').fill('SOFTWARE QA normalized labels; not real specimen findings.');await button('Save explicit dimension binding',profile).click();await profile.getByText(/CURRENT BINDING/).waitFor();
  await control(profile,'Value 1').fill('SOFTWARE example A');await button('Add another value',profile).click();await control(profile,'Value 2').fill('SOFTWARE example B');await control(profile,'Classification reason').fill('SOFTWARE QA only. These labels are unreviewed and do not assert a biological fact.');await button('Save typed classification revision',profile).click();await profile.getByText(/Typed classification revision saved/).waitFor();
  await control(profile,'Classification reason').fill('SOFTWARE QA retained unfinished normalization note');
  await button('Inspect or revise the original source-linked cell',profile).click();await waitEditor();await button('Back to table').first().click();await waitViews();
  profile=page.locator('tbody tr').first().locator('.paper-profile-details');await details('Paper profile & explicit classification',profile);await details('Map a dimension and normalize an existing entry',profile);assert.equal(await control(profile,'Classification reason').inputValue(),'SOFTWARE QA retained unfinished normalization note');mark('profile-draft-source-roundtrip');
  const controls=page.locator('[aria-label="Evidence views"]');await details('Filters, columns and order',controls);await controls.getByRole('checkbox',{name:'Include explicitly typed unreviewed suggestions/classifications',exact:true}).check();
  await controls.getByRole('checkbox',{name:'SOFTWARE example A',exact:true}).check();await controls.getByRole('checkbox',{name:'SOFTWARE example B',exact:true}).check();await select(controls,'Group report occurrences').selectOption('specimen');await controls.getByText(/1 unique reports · 2 grouped occurrences/).waitFor();
  await details('Save and reopen a named view',controls);await control(controls,'View name').fill('SOFTWARE QA multisite view');await button('Save view',controls).click();await controls.getByText('Draft: saved',{exact:true}).waitFor();
  const viewDownload=page.waitForEvent('download');await button('Download current-view JSON',controls).click();const vd=await viewDownload;await vd.saveAs(path.join(qa,'current-view.json'));const exported=JSON.parse(fs.readFileSync(path.join(qa,'current-view.json'),'utf8'));assert.equal(exported.view.unique_report_count,1);assert.deepEqual(exported.view.paper_ids,[state.paper]);assert.equal(exported.view.profiles.papers.length,1);mark('multivalue-filter-group-save-filtered-export');
  await page.reload({waitUntil:'domcontentloaded'});await waitViews();await controls.getByText(/1 unique reports · 2 grouped occurrences/).waitFor();
  await page.locator('button[data-board-cell]').filter({visible:true}).first().click();await waitEditor();await button('Edit saved cell').click();await showComment();await page.getByRole('textbox',{name:'Manual cell value',exact:true}).fill(marker);
  await details('More evidence tools, proposals and history',page.locator('.board-cell-editor'));const before=noWork();await button('Open passage search for this field').click();const question=page.getByRole('textbox',{name:'Evidence question',exact:true});await question.waitFor();assert.equal(noWork(),before);
  await question.fill('microbiome');await page.getByLabel('Maximum passages for next search',{exact:true}).fill('10');await button('Retrieve passages').click();await button('Inspect source for passage 1 ↓').click();await page.locator('#source-context .source-text').waitFor();await button('Open in comparison cell · passage 1').click();await waitEditor();await page.getByText(/Returned passage opened for inspection only/).waitFor();await showComment();assert.equal(await page.getByRole('textbox',{name:'Manual cell value',exact:true}).inputValue(),marker);
  state.cellURL=page.url();await page.reload({waitUntil:'domcontentloaded'});await waitEditor();await showComment();assert.equal(await page.getByRole('textbox',{name:'Manual cell value',exact:true}).inputValue(),marker);await page.goBack({waitUntil:'domcontentloaded'});await question.waitFor();assert.equal(await question.inputValue(),'microbiome');await button('Back to cell').click();await waitEditor();await showComment();assert.equal(await page.getByRole('textbox',{name:'Manual cell value',exact:true}).inputValue(),marker);mark('passage-source-return-back-refresh-retains-draft-and-view');
  await page.getByRole('textbox',{name:'Manual cell value',exact:true}).fill('SOFTWARE QA explicitly revised source-linked entry');await button('Review entry before saving').click();await button('Save revision').click();await page.getByText('Saved to comparison.',{exact:true}).waitFor();
  const history=await api('GET',base+'/boards/'+state.board+'/cells/'+encodeURIComponent(state.paper)+'/population/history?revision_id='+encodeURIComponent(state.revision));assert.equal(history.total,2);assert.ok(history.items.every(c=>c.semantic_assessment==='unassessed'));mark('explicit-revision-preserves-original-entry');
  await button('Edit saved cell').click();await showComment();await page.getByRole('textbox',{name:'Manual cell value',exact:true}).fill(marker);
  await button('Back to table').first().click();await waitViews();
  // The explicit cell revision correctly made the old typed classification
  // outdated, so the saved scientific facet no longer matches that report.
  const reveal=button('Show this cell in the table');await reveal.waitFor();assert.equal(await page.locator('button[data-board-cell]:visible').count(),0);assert.equal(await reveal.evaluate(n=>n===document.activeElement),true);await reveal.click();await controls.getByText(/3 unique reports/).waitFor();
  const restored=page.locator('button[data-board-cell]').first();await page.waitForFunction(node=>node===document.activeElement,await restored.elementHandle());state.expectedReports=3;mark('outdated-filtered-active-report-explicit-reveal-focus');state.exports=await digestExport(state);
  await page.screenshot({path:path.join(qa,'workbench-wide.private.png'),fullPage:false});await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:path.join(qa,'workbench-narrow.private.png'),fullPage:false});mark('keyboard-return-and-narrow-layout');
  await context.storageState({path:cookies});fs.writeFileSync(record,JSON.stringify(state));
 }else{
  const state=JSON.parse(fs.readFileSync(record,'utf8'));await page.goto(state.cellURL,{waitUntil:'domcontentloaded'});await waitEditor();await showComment();assert.equal(await page.getByRole('textbox',{name:'Manual cell value',exact:true}).inputValue(),marker);await button('Back to table').first().click();await waitViews();await page.locator('[aria-label="Evidence views"]').getByText(new RegExp(state.expectedReports+' unique reports')).waitFor();assert.deepEqual(await digestExport(state),state.exports);mark('restart-reopen-draft-view-exports');
 }
 assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(qa,phase+'-report.private.json'),JSON.stringify({status:'PASS',checks,browser_version:browser.version(),driver_seconds:(Date.now()-started)/1000,api_requests:requests.length,external_requests:external.length,browser_errors:errors.length,platform:process.platform,architecture:process.arch,scope:'Production Chromium/public retained reports + synthetic unreviewed inputs; no live/model/human evaluation'},null,2));console.log(JSON.stringify({status:'PASS',checks:checks.length,external_requests:0,browser_errors:0}));
 }catch(e){
  fs.writeFileSync(path.join(qa,phase+'-failure.private.txt'),String(e.stack));
  await page.screenshot({path:path.join(qa,phase+'-failure.private.png'),fullPage:false}).catch(()=>{});
  fs.writeFileSync(path.join(qa,phase+'-failure-dom.private.html'),await page.content().catch(()=>''));
  console.error(e.stack);process.exitCode=1;
 }finally{await browser.close();}
})();
