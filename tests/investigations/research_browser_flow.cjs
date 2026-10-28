'use strict';
// Real application browser acceptance. Provider/server must be the offline research fixture.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const [tools,origin,out]=process.argv.slice(2),{chromium}=require(path.join(tools,'node_modules','playwright'));
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms)),record=process.env.LRE_RECORD_DEMO==='1';
const stripFreshness=value=>Array.isArray(value)?value.map(stripFreshness):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).filter(([k])=>!['freshness','freshness_reasons'].includes(k)).map(([k,v])=>[k,stripFreshness(v)])):value;
async function seed(page,label){
 await page.goto(origin);await page.getByRole('heading',{name:'Create a workspace',exact:true}).waitFor();
 return page.evaluate(async label=>{
  const csrf=(await(await fetch('/api/v1/session')).json()).csrf_token;
  const call=async(p,m='GET',body)=>{const r=await fetch('/api/v1/'+p,{method:m,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)}),v=await r.json();if(!r.ok)throw Error(JSON.stringify(v));return v;};
  const ws=await call('workspaces','POST',{request_id:'research-demo-'+crypto.randomUUID(),mode:'live',question:label+' — OFFLINE SIMULATION / public fixtures'}),root='workspaces/'+ws.id;
  const search=await call(root+'/searches','POST',{request_id:'initial',query:'SYNTHETIC INITIAL',max_results:2});
  const prep=await call(root+'/source-preparations','POST',{request_id:'prepare-original',search_id:search.id,paper_ids:search.papers.map(p=>p.id)});
  const board=await call(root+'/boards','POST',{request_id:'original-board',question:'OFFLINE DEMO — gut microbiome and population context',preparation_id:prep.id,paper_ids:prep.selected_paper_ids,fields:[{id:'population',label:'Population',subquestion:'What population was described in the inspected material?'}]});
  const def=board.definition,endpoint=root+'/boards/'+def.board_id,paper=def.paper_ids[0],revision=def.revision_id;
  const candidates=await call(endpoint+'/candidates','POST',{request_id:'original-excerpts',expected_revision_id:revision,paper_id:paper,field_id:'population',top_k:3});
  const ref=candidates.candidates[0].reference,input=Object.fromEntries(['source_id','source_version','source_sha256','blocks_sha256','block_id','start','end'].map(k=>[k,ref[k]]));
  const draft=await call(endpoint+'/drafts/'+encodeURIComponent(paper)+'/population','PUT',{expected_revision_id:revision,version:0,data:{value:'DEMO partial assessment — population detail needs further inspection.',reason:'Synthetic practice interpretation; bounded inspected excerpt only.',semantic_assessment:'partial',scope_result:'value_found',missing_information:'Population context remains unresolved in this inspected excerpt.',references:[input],inspected_ranges:[input]}});
  const cell=await call(endpoint+'/cell-revisions','POST',{request_id:'original-cell',expected_revision_id:revision,paper_id:paper,field_id:'population',draft_version:draft.version});
  return {root,endpoint,paper,revision,board:def.board_id,definition:def,cell,audit:await call(endpoint+'/exports?format=json'),workspace:await call(root)};
 },label);
}
function url(s,cell=false){return origin+'/?'+new URLSearchParams({page:'compare',workspace:s.root.split('/')[1],board:s.board,revision:s.revision,...(cell?{paper:s.paper,field:'population'}:{})});}
(async()=>{
 fs.mkdirSync(out,{recursive:true,mode:0o700});fs.mkdirSync(path.join(out,'exports'),{recursive:true,mode:0o700});
 const options={channel:process.env.LRE_BROWSER_CHANNEL||'chrome',headless:true,chromiumSandbox:true,viewport:{width:1440,height:1000},acceptDownloads:true,args:['--no-first-run','--disable-background-networking','--disable-component-update']};
 const persistent=process.env.LRE_DEMO_PROFILE;
 const browser=persistent?null:await chromium.launch(options),context=persistent?await chromium.launchPersistentContext(persistent,options):await browser.newContext(options);
 const traffic=[],errors=[],external=[];
 await context.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!==origin){external.push(u.origin);return route.abort('blockedbyclient');}traffic.push({method:route.request().method(),path:u.pathname});return route.continue();});
 const page=context.pages()[0]||await context.newPage();page.setDefaultTimeout(25000);page.on('pageerror',e=>errors.push(e.message));
 const button=name=>page.getByRole('button',{name,exact:true}),center=async loc=>{await loc.scrollIntoViewIfNeeded();await wait(100);};
 let capturing=false,capturePromise,start=Date.now(),frames=[],chapters=[];
 const frameDir=path.join(out,'recording-frames');if(record)fs.mkdirSync(frameDir,{recursive:true,mode:0o700});
 const capture=async()=>{while(capturing){const file='frame-'+String(frames.length).padStart(5,'0')+'.jpg',seconds=frames.length?(Date.now()-start)/1000:0;await page.screenshot({path:path.join(frameDir,file),type:'jpeg',quality:80});frames.push({file,seconds});await wait(230);}};
 const step=async(text,ms=2000)=>{console.log(JSON.stringify({step:text}));chapters.push({seconds:(Date.now()-start)/1000,text});if(record)await wait(ms);};
 const call=async(p,m='GET',body)=>page.evaluate(async({p,m,body})=>{const csrf=(await(await fetch('/api/v1/session')).json()).csrf_token,r=await fetch('/api/v1/'+p,{method:m,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)}),v=await r.json();if(!r.ok)throw Error(JSON.stringify(v));return v;},{p,m,body});
 try{
  const setup=await seed(page,'Completed v0.2 walkthrough');await page.goto(url(setup));await page.locator('.board-table').waitFor();
  start=Date.now();capturing=record;if(record)capturePromise=capture();
  await step('OFFLINE SOFTWARE DEMO · Real application, public source fixtures, simulated PubMed responses. No scientific validation.',3200);
  const beforeNav=traffic.length;await page.getByRole('link',{name:'Export comparison',exact:true}).click();
  await page.getByRole('link',{name:'Comparison table',exact:true}).click();assert.equal(traffic.length,beforeNav);
  await step('The sticky sidebar follows the visible section. Section navigation keeps forms mounted and makes no provider request.');
  await button('Needs review').click();await page.locator('[data-board-cell]').first().click();await button('2. Comment & judge').click();
  await center(page.getByRole('region',{name:'Continue this evidence assessment',exact:true}));
  await step('A partial assessment offers two next steps: inspect more of the original paper, or investigate related literature.',3000);
  await button('Inspect more context in this paper').click();await page.locator('[id=comparison-source]').waitFor();
  await button('Investigate related literature').click();
  await page.getByRole('textbox',{name:'Reason for investigating',exact:true}).fill('DEMO: the bounded original excerpt leaves population detail unresolved. Investigate related reports for broader context; do not fill facts about the original paper.');
  await button('Create investigation draft').click();await page.getByText('INVESTIGATION · SAVED LOCALLY',{exact:true}).waitFor();
  const objective=page.getByRole('textbox',{name:'Follow-up objective',exact:true});await objective.fill('gut microbiome in women');
  await button('Suggest editable concepts').click();await button('Use suggestions as editable draft').click();
  const concepts=page.getByRole('region',{name:'Core concept builder',exact:true});
  const reviewConcepts=concepts.locator('article[aria-label^="Review concept"]');assert.equal(await reviewConcepts.count(),2);
  await center(concepts);await step('One shared Core builder proposes phrases and possible synonyms. Their origins and uncertainty remain visible.',3000);
  for(let i=0;i<await reviewConcepts.count();i++)await reviewConcepts.nth(i).getByRole('combobox',{name:/Search use/}).selectOption('required_query');
  await button('Approve reviewed Core terms for compilation').click();await button('Build reviewed Boolean strategies').click();
  await button('Save revised investigation plan').click();
  const exact=page.getByRole('textbox',{name:'Exact executable PubMed query',exact:true});await exact.waitFor();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('textarea')).some(e=>e.readOnly&&e.value.includes('AND')));
  const query=await exact.inputValue();assert.ok(query.includes('AND')&&query.includes('OR'));await center(exact);
  await step('Reviewed synonyms use OR; required concept groups use AND. Review the exact compiled query before approving this revision.',3200);
  await page.getByRole('checkbox',{name:'I reviewed this exact query, dates, sort and stated constraints',exact:true}).check();await button('Approve exact investigation query').click();
  await page.getByText('Approval saved for this exact query revision.',{exact:true}).waitFor();
  await button('Edit this exact query').click();const specialist=page.getByRole('textbox',{name:'Specialist PubMed strategy',exact:true});await specialist.fill(query+' AND humans[Title/Abstract]');
  assert.equal(await button('Run approved PubMed search').isDisabled(),true);
  await step('Any query edit disables the old approval. This explicit specialist edit is preserved exactly.');
  await button('Save revised investigation plan').click();await page.waitForFunction(q=>Array.from(document.querySelectorAll('textarea')).some(e=>e.readOnly&&e.value===q),query+' AND humans[Title/Abstract]');
  for(const deferred of await page.getByRole('checkbox',{name:/^Acknowledge deferred constraint:/}).all())await deferred.check();
  await page.getByRole('checkbox',{name:'Acknowledge that this specialist strategy is unparsed',exact:true}).check();await page.getByRole('checkbox',{name:'I reviewed this exact query, dates, sort and stated constraints',exact:true}).check();await button('Approve exact investigation query').click();
  await page.getByText('Approval saved for this exact query revision.',{exact:true}).waitFor();await button('Run approved PubMed search').click();
  const results=page.getByRole('region',{name:'Saved investigation results',exact:true});await results.waitFor();await center(results);
  await page.getByText(/SIMULATED SEARCH: fixed public fixture papers/).waitFor();
  await step('The offline provider returns fixed public fixture records. These are candidates, not confirmed relevant or eligible studies.',3000);
  await results.getByRole('button',{name:'Shortlist',exact:true}).nth(0).click();await page.getByText('Decision: shortlist · version 1',{exact:true}).waitFor();
  await results.getByRole('button',{name:'Dismiss',exact:true}).nth(1).click();await page.getByText('Decision: dismiss · version 1',{exact:true}).waitFor();
  await button('Add evidence or expand comparison').click();
  const research=page.getByRole('region',{name:'Continue investigation research',exact:true});await research.waitFor();
  await research.getByRole('checkbox',{name:/shortlisted candidate/}).first().check();await research.getByRole('checkbox',{name:/original report/}).first().check();
  await button('Review selected papers for comparison').click();await button('Add selected papers to comparison workflow').click();
  await button('Prepare selected sources').waitFor();await center(page.getByRole('heading',{name:'Committed research selections',exact:true}));
  await step('Commit the reviewed shortlist and chosen original report to an immutable collection. This step alone prepares no sources.',3000);
  const afterCommit=await call(setup.root);assert.deepEqual(afterCommit,setup.workspace);
  await button('Prepare selected sources').click();await button('Use this prepared selection').waitFor({timeout:60000});await center(button('Use this prepared selection'));
  await step('Explicit preparation reuses the source workflow. Full text, abstract-only and unavailable outcomes stay distinct.');
  await button('Use this prepared selection').click();
  await research.getByRole('textbox',{name:'Question for related-paper passages',exact:true}).fill('gut microbiome women diet population');await button('Retrieve prepared passages').click();
  const inspectButton=page.getByRole('button',{name:/^Inspect related-paper passage · /}).first();await inspectButton.waitFor();await inspectButton.click();
  const receipt=page.getByRole('complementary',{name:'Verified related-paper inspection',exact:true});await receipt.waitFor();await center(receipt);
  await step('Route 1: inspect a verified retained passage. The source paper, exact excerpt and full-text/abstract status are explicit.',3200);
  await button('Use this passage in my research evaluation').click();
  await research.getByRole('textbox',{name:'My research interpretation',exact:true}).fill('DEMO interpretation: this related paper provides context for the broader microbiome question. It does not establish missing population facts about the original report.');
  await research.getByRole('checkbox',{name:'I inspected the displayed passage from this prepared source',exact:true}).check();await research.getByRole('checkbox',{name:'I am attributing this evidence to the named related paper, not to the original paper',exact:true}).check();
  await button('Save source-linked research evaluation').click();await research.getByRole('heading',{name:'Saved evaluations',exact:true}).waitFor();await center(research.getByRole('heading',{name:'Saved evaluations',exact:true}));
  await step('Save a researcher-authored evaluation linked to Paper B. It remains separate from the original Paper A cell.',3200);
  await button('Revise this research evaluation').click();await research.getByRole('textbox',{name:'My research interpretation',exact:true}).fill('DEMO revised interpretation: the named related paper supplies broader context only; original-paper population details remain unresolved.');
  await research.getByRole('checkbox',{name:'I inspected the displayed passage from this prepared source',exact:true}).check();await research.getByRole('checkbox',{name:'I am attributing this evidence to the named related paper, not to the original paper',exact:true}).check();await button('Save revised research evaluation').click();await research.getByText(/Revision 2 · Related-paper evidence/).waitFor();
  const activeSelection=research.getByRole('button',{name:/Open committed selection/}).first();await activeSelection.click();assert.ok(await inspectButton.count()>0);
  // Leave immediately after editing: explicit navigation flushes every active draft.
  const unfinished='DEMO unsaved further thought retained through immediate navigation 🧬';await research.getByRole('textbox',{name:'My research interpretation',exact:true}).fill(unfinished);await button('All investigations for this cell').click();const investigations=await call(setup.root+'/investigations?board_id='+encodeURIComponent(setup.board));const savedResearchDraft=await call(setup.root+'/drafts/'+encodeURIComponent('investigation-research:'+investigations.investigations[0].id));assert.equal(savedResearchDraft.data.interpretation,unfinished);await page.reload();
  await page.getByRole('button',{name:/^(Investigate related literature|Reopen cell investigations)$/}).click();await button('Reopen investigation').click();await button('Add evidence or expand comparison').click();await research.getByText('Draft: saved',{exact:true}).waitFor();
  assert.equal(await research.getByRole('textbox',{name:'My research interpretation',exact:true}).inputValue(),unfinished);
  await center(research.getByRole('heading',{name:'Saved evaluations',exact:true}));await step('Notes, source bindings, revision history and unfinished edits survive navigation and refresh.',2800);
  await step('Compact navigation at 390px and 320px keeps the same saved interpretation and source attribution.',2000);
  for(const width of [390,320]){
   await page.setViewportSize({width,height:844});await page.getByRole('button',{name:/Navigate ·/}).click();await page.getByRole('link',{name:'Research evaluation note',exact:true}).click();
   await wait(150);const navigationBounds=await page.locator('.workspace-navigation').boundingBox();assert.ok(navigationBounds.y<=2,JSON.stringify(navigationBounds));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1),false);await page.screenshot({path:path.join(out,'narrow-'+width+'.png')});if(record)await wait(1400);
   assert.equal(await research.getByRole('textbox',{name:'My research interpretation',exact:true}).inputValue(),unfinished);
  }
  await page.setViewportSize({width:1440,height:1000});await center(research.getByRole('heading',{name:'Continue in an expanded comparison',exact:true}));
  await step('Route 2: explicitly choose the prepared previous and new reports. The new comparison starts with unassessed cells.',3000);
  await button('Create expanded comparison').click();await button('Open expanded comparison').click();await page.locator('.board-table').waitFor();
  const derivedEndpoint=setup.root+'/boards/'+new URL(page.url()).searchParams.get('board'),derived=await call(derivedEndpoint);assert.equal(derived.definition.paper_ids.length,2);assert.ok(derived.cells.every(cell=>cell.head===null));
  await page.getByRole('button',{name:'Open original comparison and judgments',exact:true}).waitFor();await step('The expanded board retains collection and investigation provenance. No prior judgment is automatically copied.',3000);
  await button('Open original comparison and judgments').click();await page.locator('.board-table').waitFor();
  const old=await call(setup.endpoint),afterAudit=await call(setup.endpoint+'/exports?format=json');assert.deepEqual(old.definition,setup.definition);assert.deepEqual(stripFreshness(afterAudit),stripFreshness(setup.audit));assert.equal(old.freshness,'historical');
  await center(page.locator('.board-table'));await step('The original board and judgment remain intact. New preparation makes it historical; exact old evidence is still readable.',3200);
  await page.locator('[data-board-cell]').first().click();await button('Inspect more context in this paper').click();await page.locator('[id=comparison-source]').waitFor();
  await page.getByRole('button',{name:/^(Investigate related literature|Reopen cell investigations)$/}).click();await button('Reopen investigation').click();await page.getByText('Append-only investigation history',{exact:true}).click();await center(page.getByText('Append-only investigation history',{exact:true}));
  await step('Audit history retains the triggering cell, exact query approvals, simulated execution, manual decisions, handoff and note revisions.');
  await button('Prepare readable audit export').click();
  for(const [label,file] of [['Download readable audit','investigation-audit.md'],['Download audit JSON','investigation-audit.json']]){const d=page.waitForEvent('download');await page.getByRole('link',{name:label,exact:true}).click();await(await d).saveAs(path.join(out,'exports',file));}
  const audit=JSON.parse(fs.readFileSync(path.join(out,'exports/investigation-audit.json'),'utf8'));assert.equal(audit.research.notes.length,2);assert.equal(audit.research.handoffs.length,1);assert.notEqual(audit.research.notes[0].inspection.source_paper.id,setup.paper);assert.equal(audit.investigation.origin.cell.id,setup.cell.id);
  await step('Completed: attributed evaluation and expanded comparison, with original research records retained. Real PubMed, models and human usefulness NOT RUN.',3500);
  capturing=false;if(capturePromise)await capturePromise;
  assert.deepEqual(errors,[]);assert.equal(traffic.filter(r=>/\/investigations\/[^/]+\/execute$/.test(r.path)).length,1);
  const result={status:'PASS',source:process.env.LRE_SOURCE_SHA||'integration working tree',viewports:[1440,390,320],page_errors:errors,provider:'offline fixed public fixtures only',original_scientific_record:'unchanged; freshness historical after explicit preparation',checks:['shared concept generator','exact approval invalidation','manual shortlist','explicit immutable collection','actual source preparation','verified related-paper note revisions','immediate navigation draft retention','expanded comparison starts unassessed','original historical references','audit export']};
  fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify(result,null,2));fs.writeFileSync(path.join(out,'preservation-check.json'),JSON.stringify({before:setup.audit,after:afterAudit},null,2));
  const fresh=await seed(page,'Try v0.2 yourself');fs.writeFileSync(path.join(out,'demo-state.json'),JSON.stringify({origin,fresh_url:url(fresh),completed_url:url(setup),completed_cell_url:url(setup,true),derived_url:origin+'/?'+new URLSearchParams({page:'compare',workspace:setup.root.split('/')[1],board:derived.definition.board_id}),fresh,completed:setup,result},null,2));
  console.log(JSON.stringify(result));
 }catch(error){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});fs.writeFileSync(path.join(out,'failure.txt'),await page.locator('body').innerText().catch(()=>''));throw error;}
 finally{capturing=false;if(capturePromise)await capturePromise.catch(()=>{});if(record){fs.writeFileSync(path.join(frameDir,'manifest.json'),JSON.stringify(frames));fs.writeFileSync(path.join(out,'walkthrough-chapters.json'),JSON.stringify(chapters,null,2));}await context.close();if(browser)await browser.close();}
})().catch(error=>{console.error(error.stack);process.exit(1)});
