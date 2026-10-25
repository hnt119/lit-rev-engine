/* Real Chromium test-only driver. Never log or upload its private QA files. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const [tools, origin, qa, phase] = process.argv.slice(2);
const {chromium} = require(path.join(tools, 'node_modules', 'playwright'));
const progressPath = path.join(qa, 'browser-progress.json');
const cookiesPath = path.join(qa, 'browser-state.json');
const marker = 'SOFTWARE QA Windows browser unsent draft — not a research judgment';
let browserStep='launch', lastPreparationStatus=null, diagnostics={};
const checkpoint=name=>{browserStep=name;console.log(JSON.stringify({browser_step:name}));};

(async()=>{
  const browser = await chromium.launch({headless:true,chromiumSandbox:true});
  const context = await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true,
    ...(phase==='verify'?{storageState:cookiesPath}:{})});
  const requests=[], errors=[];
  await context.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.origin!==origin) return route.abort('blockedbyclient');
    requests.push({method:route.request().method(),path:url.pathname});
    return route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(45000);
  page.on('pageerror',error=>errors.push(error.name));
  page.on('response',async response=>{
    if(!/\/preparation-jobs(?:\/|$)/.test(new URL(response.url()).pathname)||!response.ok())return;
    try{const value=await response.json();const state=value.job?.status??value.status;
      if(['queued','running','succeeded','failed','stale','cancelled','cancel_requested'].includes(state))lastPreparationStatus=state;
    }catch{} // Diagnostics observe already-requested reads; they perform no new work.
  });
  const button=name=>page.getByRole('button',{name,exact:true});
  const readyEditor=async()=>{
    await page.locator('.board-cell-editor').waitFor();
    await page.locator('.board-cell-editor').getByText('Draft: saved',{exact:true}).waitFor();
  };
  const readyPassageSearch=async()=>{
    const question=page.getByRole('textbox',{name:'Evidence question',exact:true});
    await question.waitFor();
    await page.locator('section').filter({has:question}).getByText('Draft: saved',{exact:true}).waitFor();
  };
  const showComment=async()=>{
    const value=page.getByRole('textbox',{name:'Manual cell value',exact:true});
    if(!await value.isVisible())await button('2. Comment & judge').click();
    await value.waitFor();
  };
  const assertDraft=async()=>{await showComment();assert.equal(await page.getByRole('textbox',{name:'Manual cell value',exact:true}).inputValue(),marker);};
  const moreTools=async()=>{
    const tools=page.locator('.board-cell-editor details').filter({has:page.getByText('More evidence tools, proposals and history',{exact:true})});
    if(!await tools.evaluate(node=>node.open))await tools.locator('summary').first().click();
  };
  try {
    if(phase==='create'){
      checkpoint('create-workspace');
      await page.goto(origin,{waitUntil:'domcontentloaded'});
      await page.getByRole('textbox',{name:'Research question',exact:true}).fill('SYNTHETIC SOFTWARE QA Windows browser: 亚洲女性 🧬 inspect retained microbiome evidence');
      await button('Create workspace').click();
      checkpoint('open-saved-example');
      await button('Open saved example').click();
      await page.locator('article[data-paper-id]').nth(29).waitFor();
      for(let i=0;i<3;i++) await page.locator('article[data-paper-id]').nth(i).getByRole('checkbox',{name:'Select for exploration',exact:true}).check();
      checkpoint('prepare-three-selected-papers');
      await button('Prepare & compare (3)').click();
      const form=page.getByRole('textbox',{name:'Field 1 retrieval subquestion',exact:true});
      const openReady=button('Open ready comparison (3)'),continueReady=button('Continue to comparison (3)');
      // Next's route announcer can expose an empty transient alert outside the app.
      const failure=page.locator('#main').getByRole('alert').filter({hasText:/\S/}).first();
      const terminalFailure=page.locator('section[aria-label="Preparation job receipt"] p.meta')
        .filter({hasText:/ · (?:failed|stale|cancelled) · /}).first();
      const outcome=await Promise.race([
        form.waitFor({timeout:90000}).then(()=>'form'),
        openReady.waitFor({timeout:90000}).then(()=>'open-ready'),
        continueReady.waitFor({timeout:90000}).then(()=>'continue-ready'),
        failure.waitFor({timeout:90000}).then(()=>'failure'),
        terminalFailure.waitFor({timeout:90000}).then(()=>'failure')
      ]);
      if(outcome==='failure')throw new Error('Preparation UI reported a failure; no retry or resubmission was attempted.');
      if(!await form.isVisible()){
        checkpoint('open-exact-ready-comparison');
        const control=outcome==='open-ready'?openReady:continueReady;
        try{await control.click({timeout:10000});}catch(error){if(!await form.isVisible())throw error;}
      }
      await form.waitFor({timeout:45000});
      checkpoint('create-three-field-board');
      for(let i=1;i<=3;i++) await page.getByRole('textbox',{name:`Field ${i} retrieval subquestion`,exact:true}).fill('microbiome');
      await button('Create comparison board').click();
      await page.locator('button[data-board-cell]').nth(8).waitFor();
      await page.locator('button[data-board-cell]').first().click();
      let firstPaper;
      for(let i=0;i<3;i++){
        checkpoint('inline-same-paper-field-'+(i+1));
        await readyEditor();
        const currentPaper=new URL(page.url()).searchParams.get('paper');
        if(i===0)firstPaper=currentPaper;
        assert.equal(currentPaper,firstPaper);
        assert.equal(await page.locator('[aria-label="Current paper and field"]').innerText(),`Paper 1 of 3 · Field ${i+1} of 3`);
        await button('Find excerpts in this paper').focus();await page.keyboard.press('Enter');
        await button('Read in source · passage 1').click();
        await page.locator('.board-cell-editor .source-text').waitFor();
        await button('I have read this excerpt — use it').click();
        await page.getByRole('textbox',{name:'Manual cell value',exact:true}).waitFor();
        assert.equal(await page.getByRole('textbox',{name:'Manual cell value',exact:true}).evaluate(node=>node===document.activeElement),true);
        await page.getByRole('textbox',{name:'Manual cell value',exact:true}).fill(`SOFTWARE QA unassessed Windows cell ${i}`);
        await page.getByRole('textbox',{name:'Reason',exact:true}).fill('Mechanical software exercise only; no researcher support judgment.');
        await button('Review entry before saving').click();
        await button('Save reviewed entry').click();
        await page.getByText('Saved to comparison.',{exact:true}).waitFor();
        const next=await page.locator('[aria-label="Next unfinished cell destination"]').innerText();
        assert.ok(next.startsWith(i<2?'Next: another field in the same paper':'Next: a different paper'));
        if(i<2)await button('Next unfinished cell').click();
      }
      await button('Back to table').first().click();
      await page.locator('button[data-board-cell]').first().click();
      checkpoint('edit-unsent-cell-draft');
      await button('Edit saved cell').click();
      await page.getByRole('textbox',{name:'Manual cell value',exact:true}).fill(marker);
      await moreTools();
      const before=requests.filter(v=>v.method==='POST'&&v.path.endsWith('/evidence-runs')).length;
      await button('Open passage search for this field').click();
      checkpoint('comparison-passage-search');
      await readyPassageSearch();
      assert.equal(requests.filter(v=>v.method==='POST'&&v.path.endsWith('/evidence-runs')).length,before);
      await page.getByRole('textbox',{name:'Evidence question',exact:true}).fill('microbiome');
      await page.getByLabel('Maximum passages for next search',{exact:true}).fill('10');
      await button('Retrieve passages').click();
      checkpoint('inspect-exact-passage-source');
      await button('Inspect source for passage 1 ↓').click();
      await page.locator('#source-context .source-text').waitFor();
      await button('Open in comparison cell · passage 1').click();
      checkpoint('return-cell-and-refresh-draft');
      await page.getByText(/Returned passage opened for inspection only/).waitFor();
      await assertDraft();
      const boardUrl=page.url();
      await page.reload({waitUntil:'domcontentloaded'});await readyEditor();await assertDraft();
      await page.goBack({waitUntil:'domcontentloaded'});
      await readyPassageSearch();
      assert.equal(await page.getByRole('textbox',{name:'Evidence question',exact:true}).inputValue(),'microbiome');
      assert.equal(await page.getByLabel('Maximum passages for next search',{exact:true}).inputValue(),'10');
      await button('Back to cell').click();await readyEditor();await assertDraft();
      checkpoint('return-focus-and-export');
      await button('Back to table').first().click();
      assert.equal(await page.locator('button[data-board-cell]').first().evaluate(node=>node===document.activeElement),true);
      await page.getByText('Comparison tools and revision history',{exact:true}).click();
      const downloadWait=page.waitForEvent('download');
      await page.getByRole('link',{name:'Download board audit JSON',exact:true}).click();
      const downloaded=await downloadWait;const jsonPath=path.join(qa,'browser-board-export.json');await downloaded.saveAs(jsonPath);
      const exported=JSON.parse(fs.readFileSync(jsonPath,'utf8'));
      assert.equal(exported.table.length,9);assert.equal(exported.cell_revisions.length,3);
      assert.ok(exported.cell_revisions.every(v=>v.semantic_assessment==='unassessed'&&v.paper_id===firstPaper));
      const csvWait=page.waitForEvent('download');await page.getByRole('link',{name:'Download board CSV',exact:true}).click();
      await (await csvWait).saveAs(path.join(qa,'browser-board-export.csv'));
      // Genuine browser citation upload/preview/commit; no metadata resolution.
      checkpoint('import-synthetic-citation');
      await button('Discover & explore').click();await button('Import papers').click();
      await page.getByLabel('Citation file',{exact:true}).setInputFiles({name:'SYNTHETIC-Windows-public-fixture.csv',mimeType:'text/csv',
        buffer:Buffer.from('Title,Authors,Year,DOI,Abstract\nSYNTHETIC Windows software fixture,Software QA,2026,10.5555/windows-software-fixture,Public synthetic microbiome fixture for software checks only\n')});
      await button('Parse and preview citations').click();
      await page.getByRole('checkbox',{name:'Accept row 1 for the collection',exact:true}).check();
      await page.getByRole('textbox',{name:'Collection name',exact:true}).fill('SYNTHETIC Windows browser import');
      await button('Commit 1 accepted records').click();
      await page.getByText('SYNTHETIC Windows browser import',{exact:true}).first().waitFor();
      await page.goto(boardUrl,{waitUntil:'domcontentloaded'});await readyEditor();await assertDraft();
      checkpoint('persist-browser-session');
      await context.storageState({path:cookiesPath});
      fs.writeFileSync(progressPath,JSON.stringify({boardUrl,checks:{browser_import:'PASS',three_fields_same_paper_context:'PASS',excerpt_comment_review_save:'PASS',
        comparison_passage_exact_source_return:'PASS',no_navigation_search:'PASS',draft_refresh_back:'PASS',keyboard_return_focus:'PASS',exports:'PASS'}}));
    }else{
      checkpoint('reopen-browser-draft-after-restart');
      const state=JSON.parse(fs.readFileSync(progressPath,'utf8'));
      await page.goto(state.boardUrl,{waitUntil:'domcontentloaded'});await readyEditor();await assertDraft();
      await button('1. Select evidence').click();
      await button('Browse this source').click();await page.locator('.board-cell-editor .source-text').waitFor();
      await button('Back to table').first().click();
      await page.getByText('Comparison tools and revision history',{exact:true}).click();
      await page.getByRole('link',{name:'Download board audit JSON',exact:true}).waitFor();
      await context.storageState({path:cookiesPath});
    }
    assert.deepEqual(errors,[]);
    assert.equal(requests.filter(v=>v.method==='POST'&&/\/(?:hybrid-index|planner-proposals|proposals)(?:\/|$)/.test(v.path)).length,0);
    console.log(JSON.stringify({status:'PASS',actual_browser:'Chromium',phase,playwright:'1.62.1',
      source_calls:'saved public example only',paid_calls:0,generation:'NOT_RUN',research_judgment:'NOT_RUN'}));
  }catch(error){
    diagnostics=await page.evaluate(()=>{
      const page=new URLSearchParams(location.search).get('page');
      return {page:['workspaces','discover','compare','evidence','history','settings'].includes(page)?page:'unknown',
        alert_count:document.querySelectorAll('[role="alert"]').length,
        board_form_present:!!document.querySelector('section[aria-label="New comparison board"]'),
        ready_action_present:Array.from(document.querySelectorAll('button')).some(node=>/^(?:Open ready comparison|Continue to comparison) \(3\)$/.test(node.textContent.trim()))};
    }).catch(()=>({page:'unavailable'}));
    throw error;
  } finally {await context.close();await browser.close();}
})().catch(error=>{
  const message=String(error.message??'');
  const errorCode=message.includes('strict mode violation')?'locator-ambiguous':
    /Unexpected token|Invalid selector|Error while parsing selector|not a valid selector/.test(message)?'selector-syntax':
    message.includes('Preparation UI reported a failure')?'preparation-ui-failure':
    /Target page, context or browser has been closed|Protocol error/.test(message)?'browser-protocol':
    error.name==='TimeoutError'?'timeout':'unclassified';
  console.error(JSON.stringify({status:'FAIL',error_type:error.name,error_code:errorCode,browser_step:browserStep,
    last_preparation_status:lastPreparationStatus,diagnostics}));process.exitCode=1;
});
