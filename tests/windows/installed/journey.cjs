'use strict';
// Attach to the real installed Electron window. Never launch another browser,
// replace dialogs, intercept responses, call mutation APIs, or save cookies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const [tools, output, mode, python] = process.argv.slice(2);
const {chromium} = require(path.join(tools, 'node_modules/playwright'));
const report = {checks:{}, phase:'cdp-attach', error_type:'none'};
const acceptancePhase = {
  'cdp-attach':'installed_driver_compatibility',
  'saved-example':'saved_example_offline',
  'prepare-three':'source_preparation',
  exact_excerpt_attach:'exact_excerpt_attach',
  interpretation_submit:'interpretation_submit',
  missing_information:'missing_information',
  draft_distinct:'draft_distinct',
  native_json_export:'native_json_export', native_csv_export:'native_csv_export',
  independent_export_parse:'independent_export_parse', reopen_persistence:'reopen_persistence',
};
const stateFile = path.join(output, 'private-journey-position.json');
const submitted = 'SOFTWARE TRIAL: retained microbiome excerpt; support remains unassessed';
const draft = 'UNSUBMITTED SOFTWARE TRIAL DRAFT';
const missing = 'Allocation concealment details unresolved; full paper not assessed.';
const checkpoint = value => {report.phase=value;};
const pass = value => {report.checks[value]='PASS';};

function command(args) {
  return new Promise((resolve,reject)=>{
    const child=spawn(python,args,{stdio:'ignore'});
    child.on('error',reject);
    child.on('exit',code=>code===0?resolve():reject(new Error('Native helper failed')));
  });
}

(async()=>{
  const browser=await chromium.connectOverCDP('http://127.0.0.1:49228');
  const contexts=browser.contexts();
  assert.equal(contexts.length,1);
  const page=contexts[0].pages().find(p=>p.url().startsWith('http://127.0.0.1:43000/'));
  assert.ok(page,'Installed production page required');
  pass('installed_driver_compatibility');
  page.setDefaultTimeout(45000);
  const button=name=>page.getByRole('button',{name,exact:true});
  const text=name=>page.getByRole('textbox',{name,exact:true});
  const editor=async()=>{
    await page.locator('.board-cell-editor').waitFor();
    await page.locator('.board-cell-editor').getByText('Draft: saved',{exact:true}).waitFor();
  };
  const comment=async()=>{
    if(!await text('Manual cell value').isVisible())await button('2. Comment & judge').click();
    await text('Manual cell value').waitFor();
  };
  const forbidden=[];
  page.on('request',request=>{
    const url=new URL(request.url());
    if(request.method()==='POST'&&/\/(?:hybrid-index|planner-proposals|proposals|install-model|search-pubmed)(?:\/|$)/.test(url.pathname))forbidden.push('unexpected-optional-operation');
  });
  // Observe responses already requested by UI for independent exact-source
  // assertions. The driver never performs the research action through an API.
  let inspectedResponse=null;
  page.on('response',async response=>{
    if(response.ok()&&/\/(?:context|passage-source-context|blocks)(?:\?|$)/.test(response.url())){
      try{inspectedResponse=await response.json();}catch{}
    }
  });
  if(mode==='create'){
    checkpoint('saved-example');
    await button('Try the saved example').click();
    await page.locator('article[data-paper-id]').nth(29).waitFor();
    pass('saved_example_offline');
    for(let i=0;i<3;i++)await page.locator('article[data-paper-id]').nth(i).getByRole('checkbox',{name:'Select for exploration',exact:true}).check();
    checkpoint('prepare-three');
    await button('Prepare & compare (3)').click();
    const form=text('Field 1 retrieval subquestion');
    const ready=page.getByRole('button',{name:/^(?:Open ready comparison|Continue to comparison) \(3\)$/});
    await Promise.race([form.waitFor({timeout:120000}),ready.waitFor({timeout:120000})]);
    if(!await form.isVisible())await ready.click();
    await form.waitFor();
    pass('source_preparation');
    checkpoint('three_papers_three_fields');
    const labels=['Study focus','Allocation concealment details','Reviewer notes'];
    for(let i=1;i<=3;i++){
      await text(`Field ${i} label`).fill(labels[i-1]);
      await text(`Field ${i} retrieval subquestion`).fill(i===1?'microbiome':labels[i-1]);
    }
    await button('Create comparison board').click();
    const cells=page.locator('button[data-board-cell]');
    await cells.nth(8).waitFor();
    assert.equal(await cells.count(),9);
    pass('three_papers_three_fields');
    checkpoint('exact_excerpt_attach');
    await cells.first().click();await editor();
    await button('Find excerpts in this paper').click();
    await button('Read in source · passage 1').click();
    const excerpt=await page.locator('.board-cell-editor .source-text').innerText();
    assert.ok(excerpt.length>20);
    await button('I have read this excerpt — use it').click();
    await comment();
    pass('exact_excerpt_attach');
    checkpoint('interpretation_submit');
    await text('Manual cell value').fill(submitted);
    await text('Reason').fill('Mechanical public-fixture acceptance only; no scientific support claim.');
    await button('Review entry before saving').click();
    await button('Save reviewed entry').click();
    await page.getByText('Saved to comparison.',{exact:true}).waitFor();
    pass('interpretation_submit');
    checkpoint('missing_information');
    await button('Next unfinished cell').click();await editor();
    await button('Continue with notes or missing information').click();
    await text('Manual cell value').fill('');
    await text('Reason').fill('The retained material has not been assessed for this detail.');
    await text('Missing information').fill(missing);
    await button('Review entry before saving').click();
    await button('Save reviewed entry').click();
    await page.getByText('Saved to comparison.',{exact:true}).waitFor();
    pass('missing_information');
    checkpoint('draft_distinct');
    await button('Next unfinished cell').click();await editor();
    await button('Continue with notes or missing information').click();
    await text('Manual cell value').fill(draft);
    await page.locator('.board-cell-editor').getByText('Draft: saved',{exact:true}).waitFor();
    const draftUrl=page.url();
    await button('Back to table').first().click();
    assert.ok((await cells.nth(2).innerText()).includes('Not yet submitted'));
    assert.ok((await cells.nth(2).innerText()).includes('SAVED DRAFT'));
    pass('draft_distinct');
    await page.getByText('Comparison tools and revision history',{exact:true}).click();
    const folder=path.join(output,'exports with spaces 亚洲');
    await command([path.join(__dirname,'trial.py'),'--private-export-directory',folder]);
    for(const [extension,name] of [['json','Download board audit JSON'],['csv','Download board CSV']]){
      checkpoint(`native_${extension}_export`);
      const save=command([path.join(__dirname,'trial.py'),'--save-dialog',path.join(folder,`comparison.${extension}`)]);
      await page.getByRole('link',{name,exact:true}).click();
      await save;
      // Installed export completion is a native modal. Acknowledge normally.
      await command([path.join(__dirname,'trial.py'),'--export-ack']);
      pass(`native_${extension}_export`);
    }
    pass('unicode_path');
    checkpoint('independent_export_parse');
    fs.writeFileSync(path.join(output,'private-expected-excerpt.json'),JSON.stringify({excerpt,submitted,draft,missing,inspectedResponse}));
    await command([path.join(__dirname,'trial.py'),'--parse-exports',output]);
    pass('independent_export_parse');
    fs.writeFileSync(stateFile,JSON.stringify({draftUrl}));
  }else{
    checkpoint('reopen_persistence');
    const state=JSON.parse(fs.readFileSync(stateFile,'utf8'));
    await page.goto(state.draftUrl,{waitUntil:'domcontentloaded'});await editor();await comment();
    assert.equal(await text('Manual cell value').inputValue(),draft);
    await button('Back to table').first().click();
    const cells=page.locator('button[data-board-cell]');
    assert.equal(await cells.count(),9);
    assert.ok((await cells.first().innerText()).includes(submitted));
    assert.ok((await cells.nth(2).innerText()).includes('Not yet submitted'));
    await cells.first().click();
    await page.getByText(submitted,{exact:true}).first().waitFor();
    const more=page.locator('details').filter({has:page.getByText('More evidence tools, proposals and history',{exact:true})});
    await more.locator('summary').click();
    await button('Load immutable cell history').click();
    const history=page.locator('[aria-label="Immutable cell history"]');
    await history.getByText(submitted,{exact:true}).waitFor();
    assert.equal(await history.locator('article.history-item').count(),1);
    pass('reopen_persistence');
  }
  assert.equal(forbidden.length,0);
  // Do not call browser.close(): that is not the application's normal quit.
  // Exiting this driver disconnects CDP. Python performs WM_CLOSE afterwards.
})().catch(error=>{
  report.error_type=['AssertionError','TimeoutError','Error','TypeError'].includes(error.name)?error.name:'unknown';
  const failedCheck=acceptancePhase[report.phase]??report.phase;
  report.checks[failedCheck]='FAIL';
  process.exitCode=1;
}).finally(()=>{
  fs.writeFileSync(path.join(output,'journey-result.json'),JSON.stringify(report));
  process.exit(process.exitCode||0);
});
