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

(async()=>{
  const browser = await chromium.launch({headless:true});
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
  const button=name=>page.getByRole('button',{name,exact:true});
  const readyEditor=async()=>{
    await page.getByLabel('Manual cell value',{exact:true}).waitFor();
    await page.locator('.board-cell-editor').getByText(/Saved draft|No unsaved changes|Draft saved|Saved locally/).first().waitFor({timeout:1500}).catch(()=>{});
  };
  const assertDraft=async()=>assert.equal(await page.getByLabel('Manual cell value',{exact:true}).inputValue(),marker);
  try {
    if(phase==='create'){
      await page.goto(origin,{waitUntil:'domcontentloaded'});
      await page.getByLabel('Research question',{exact:true}).fill('SYNTHETIC SOFTWARE QA Windows browser: 亚洲女性 🧬 inspect retained microbiome evidence');
      await button('Create workspace').click();
      await button('Open saved example').click();
      await page.locator('article[data-paper-id]').nth(29).waitFor();
      for(let i=0;i<3;i++) await page.locator('article[data-paper-id]').nth(i).getByRole('checkbox',{name:'Select for exploration',exact:true}).check();
      await button('Prepare & compare (3)').click();
      await page.getByLabel('Field 1 retrieval subquestion',{exact:true}).waitFor({timeout:90000});
      for(let i=1;i<=3;i++) await page.getByLabel(`Field ${i} retrieval subquestion`,{exact:true}).fill('microbiome');
      await button('Create comparison board').click();
      await page.locator('button[data-board-cell]').nth(8).waitFor();
      for(let i=0;i<3;i++){
        await page.locator('button[data-board-cell]').nth(i).click();
        await readyEditor();
        await button('Find relevant passages').click();
        await button('Read in source · passage 1').click();
        await page.locator('.board-cell-editor .source-text').waitFor();
        await button('I have read this excerpt — attach as evidence').click();
        await page.getByLabel('Manual cell value',{exact:true}).fill(`SOFTWARE QA unassessed Windows cell ${i}`);
        await page.getByLabel('Reason',{exact:true}).fill('Mechanical software exercise only; no researcher support judgment.');
        await button('Save cell to table').click();
        await page.getByText('Saved to comparison.',{exact:true}).waitFor();
      }
      await page.locator('button[data-board-cell]').first().click();
      await button('Edit saved cell').click();
      await page.getByLabel('Manual cell value',{exact:true}).fill(marker);
      const before=requests.filter(v=>v.method==='POST'&&v.path.endsWith('/evidence-runs')).length;
      await button('Open passage search for this field').click();
      await page.getByLabel('Evidence question',{exact:true}).waitFor();
      assert.equal(requests.filter(v=>v.method==='POST'&&v.path.endsWith('/evidence-runs')).length,before);
      await page.getByLabel('Evidence question',{exact:true}).fill('microbiome');
      await page.getByLabel('Maximum passages for next search',{exact:true}).fill('10');
      await button('Retrieve passages').click();
      await button('Inspect source for passage 1 ↓').click();
      await page.locator('#source-context .source-text').waitFor();
      await button('Open in comparison cell · passage 1').click();
      await page.getByText(/Returned passage opened for inspection only/).waitFor();
      await assertDraft();
      const boardUrl=page.url();
      await page.reload({waitUntil:'domcontentloaded'});await readyEditor();await assertDraft();
      await page.goBack({waitUntil:'domcontentloaded'});
      await page.getByLabel('Evidence question',{exact:true}).waitFor();
      assert.equal(await page.getByLabel('Evidence question',{exact:true}).inputValue(),'microbiome');
      assert.equal(await page.getByLabel('Maximum passages for next search',{exact:true}).inputValue(),'10');
      await button('Back to cell').click();await readyEditor();await assertDraft();
      await button('Back to table').first().click();
      assert.equal(await page.locator('button[data-board-cell]').first().evaluate(node=>node===document.activeElement),true);
      const downloadWait=page.waitForEvent('download');
      await page.getByRole('link',{name:'Download board audit JSON',exact:true}).click();
      const downloaded=await downloadWait;const jsonPath=path.join(qa,'browser-board-export.json');await downloaded.saveAs(jsonPath);
      const exported=JSON.parse(fs.readFileSync(jsonPath,'utf8'));
      assert.equal(exported.table.length,9);assert.equal(exported.cell_revisions.length,3);
      assert.ok(exported.cell_revisions.every(v=>v.semantic_assessment==='unassessed'));
      const csvWait=page.waitForEvent('download');await page.getByRole('link',{name:'Download board CSV',exact:true}).click();
      await (await csvWait).saveAs(path.join(qa,'browser-board-export.csv'));
      // Genuine browser citation upload/preview/commit; no metadata resolution.
      await button('Discover & explore').click();await button('Import papers').click();
      await page.getByLabel('Citation file',{exact:true}).setInputFiles({name:'SYNTHETIC-Windows-public-fixture.csv',mimeType:'text/csv',
        buffer:Buffer.from('Title,Authors,Year,DOI,Abstract\nSYNTHETIC Windows software fixture,Software QA,2026,10.5555/windows-software-fixture,Public synthetic microbiome fixture for software checks only\n')});
      await button('Parse and preview citations').click();
      await page.getByRole('checkbox',{name:'Accept row 1 for the collection',exact:true}).check();
      await page.getByLabel('Collection name',{exact:true}).fill('SYNTHETIC Windows browser import');
      await button('Commit 1 accepted records').click();
      await page.getByText('SYNTHETIC Windows browser import',{exact:true}).first().waitFor();
      await page.goto(boardUrl,{waitUntil:'domcontentloaded'});await readyEditor();await assertDraft();
      await context.storageState({path:cookiesPath});
      fs.writeFileSync(progressPath,JSON.stringify({boardUrl,checks:{browser_import:'PASS',three_inline_cells:'PASS',
        comparison_passage_exact_source_return:'PASS',no_navigation_search:'PASS',draft_refresh_back:'PASS',keyboard_return_focus:'PASS',exports:'PASS'}}));
    }else{
      const state=JSON.parse(fs.readFileSync(progressPath,'utf8'));
      await page.goto(state.boardUrl,{waitUntil:'domcontentloaded'});await readyEditor();await assertDraft();
      await button('Browse retained source').click();await page.locator('.board-cell-editor .source-text').waitFor();
      await page.getByRole('link',{name:'Download board audit JSON',exact:true}).waitFor();
      await context.storageState({path:cookiesPath});
    }
    assert.deepEqual(errors,[]);
    assert.equal(requests.filter(v=>v.method==='POST'&&/\/(?:hybrid-index|planner-proposals|proposals)(?:\/|$)/.test(v.path)).length,0);
    console.log(JSON.stringify({status:'PASS',actual_browser:'Chromium',phase,playwright:'1.62.1',
      source_calls:'saved public example only',paid_calls:0,generation:'NOT_RUN',research_judgment:'NOT_RUN'}));
  } finally {await context.close();await browser.close();}
})().catch(error=>{console.error(JSON.stringify({status:'FAIL',error_type:error.name}));process.exitCode=1;});
