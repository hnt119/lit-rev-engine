'use client';

import { useEffect, useRef, useState } from 'react';
import demo from '@/data/literature-showcase.json';
import download from '@/data/local-preview-download.json';
import styles from './LiteratureShowcase.module.css';

const downloadBase = `/downloads/lit-rev-engine-${download.version}`;
// Source commits keep an unbound template. Only the offline artifact binder
// enables these relative links after the corresponding files actually exist.
const downloadReady = download.available && /^[a-f0-9]{40}$/.test(download.source_commit)
  && /^[a-f0-9]{64}$/.test(download.archive_sha256) && download.archive_bytes > 0
  && download.spdx_license === 'MIT'
  && /^[a-f0-9]{64}$/.test(download.license_sha256)
  && /^[a-f0-9]{64}$/.test(download.installation_sha256)
  && download.archive_path === `${downloadBase}.zip`
  && download.manifest_path === `${downloadBase}.manifest.json`
  && download.checksums_path === `${downloadBase}.SHA256SUMS`
  && download.license_path === `${downloadBase}.LICENSE.txt`
  && download.installation_path === `${downloadBase}.INSTALL.md`;
type DemoStage = 'comparison' | 'passages' | 'source';
type DemoLocation = { paperId: string; fieldId: string; stage: DemoStage; tableScroll: number };
const sectionFor: Record<DemoStage, string> = {
  comparison: 'saved-comparison', passages: 'saved-passage-results', source: 'saved-evidence',
};
const subquestions: Record<string, string> = {
  population: 'What population and study design were reported?',
  diet: 'What dietary exposure or intervention was reported?',
  longevity: 'What does this retained excerpt establish about reproductive lifespan?',
};

function validLocation(value: unknown): value is DemoLocation {
  if (!value || typeof value !== 'object') return false;
  const location = value as DemoLocation;
  return demo.papers.some((item) => item.id === location.paperId)
    && demo.fields.some((item) => item.id === location.fieldId)
    && ['comparison', 'passages', 'source'].includes(location.stage)
    && Number.isFinite(location.tableScroll) && location.tableScroll >= 0;
}

// A bounded public projection. These interactions call no research services.
export default function LiteratureShowcase() {
  const [filter, setFilter] = useState('');
  const [paperId, setPaperId] = useState(demo.papers[0].id);
  const [fieldId, setFieldId] = useState(demo.fields[0].id);
  const [stage, setStage] = useState<DemoStage>('comparison');
  const inspector = useRef<HTMLHeadingElement>(null);
  const passageHeading = useRef<HTMLHeadingElement>(null);
  const tableFrame = useRef<HTMLDivElement>(null);
  const cells = useRef(new Map<string, HTMLButtonElement>());
  const current = useRef<DemoLocation>({ paperId, fieldId, stage, tableScroll: 0 });
  current.current = { paperId, fieldId, stage, tableScroll: tableFrame.current?.scrollLeft ?? 0 };
  const paper = demo.papers.find((item) => item.id === paperId)!;
  const field = demo.fields.find((item) => item.id === fieldId)!;
  const cell = paper.cells.find((item) => item.fieldId === fieldId)!;
  const excerpt = paper.excerpts.find((item) => item.id === cell.excerptId)!;
  const query = filter.trim().toLocaleLowerCase();
  const visiblePapers = demo.papers.filter((item) =>
    [item.title, item.label, ...item.tags].join(' ').toLocaleLowerCase().includes(query));
  // The engine uses Unicode code-point offsets, rather than JS UTF-16 indexes.
  const context = Array.from(excerpt.context);
  const start = excerpt.quoteStart - excerpt.contextStart;
  const end = excerpt.quoteEnd - excerpt.contextStart;

  function focusLocation(location: DemoLocation) {
    requestAnimationFrame(() => {
      if (tableFrame.current) tableFrame.current.scrollLeft = location.tableScroll;
      const target = location.stage === 'comparison'
        ? cells.current.get(`${location.paperId}:${location.fieldId}`)
        : location.stage === 'passages' ? passageHeading.current : inspector.current;
      target?.focus({ preventScroll: true });
      target?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'auto' });
    });
  }

  function restore(location: DemoLocation) {
    setPaperId(location.paperId); setFieldId(location.fieldId); setStage(location.stage);
    current.current = location;
    focusLocation(location);
  }

  useEffect(() => {
    // Only public paper/field identifiers and UI position enter history. No storage,
    // source text, questions or research-service state is used by this demonstration.
    const saved: unknown = window.history.state?.literatureDemo;
    if (validLocation(saved) && window.location.hash === `#${sectionFor[saved.stage]}`) restore(saved);
    const back = () => {
      const location: unknown = window.history.state?.literatureDemo;
      if (validLocation(location)) restore(location);
    };
    window.addEventListener('popstate', back);
    return () => window.removeEventListener('popstate', back);
  }, []);

  function navigate(stage: DemoStage, nextPaperId = paperId, nextFieldId = fieldId) {
    const previous = { ...current.current, tableScroll: tableFrame.current?.scrollLeft ?? 0 };
    window.history.replaceState({ ...window.history.state, literatureDemo: previous }, '', window.location.href);
    const next = { paperId: nextPaperId, fieldId: nextFieldId, stage, tableScroll: previous.tableScroll };
    window.history.pushState({ ...window.history.state, literatureDemo: next }, '', `#${sectionFor[stage]}`);
    restore(next);
  }

  function selectPaper(nextPaperId: string) {
    setPaperId(nextPaperId);
    setStage('comparison');
  }

  return (
    <div className={styles.showcase} id="literature-saved-demo">
      <div className={styles.demoHeader}>
        <span className={styles.label}>try the demo · saved example · read-only</span>
        <h2>Explore the route from paper to evidence</h2>
        <p className={styles.intro}>Three real papers from a saved 30-paper collection. Follow a comparison cell through saved passage results to its exact source, then return to the same cell. This narrow gut-microbiome illustration is not a representative all-site review. Nothing here searches, generates, or records a review.</p>
      </div>

      <ol className={styles.flow} aria-label="Demonstration sections">
        <li><a href="#saved-papers">papers</a></li>
        <li><a href="#saved-comparison">comparison</a></li>
        <li><a href="#saved-passage-results">saved passages</a></li>
        <li><a href="#saved-evidence">source</a></li>
      </ol>

      <section className={styles.paperSection} aria-labelledby="saved-papers">
        <h3 id="saved-papers">01 · Saved papers</h3>
        <label className={styles.filterLabel} htmlFor="saved-paper-filter">Filter these three papers</label>
        <input id="saved-paper-filter" className={styles.filter} type="search" value={filter}
          onChange={(event) => setFilter(event.target.value)} placeholder="Try Singapore, menopause, or diet"
          aria-describedby="saved-filter-help" />
        <p id="saved-filter-help" className={styles.hint}>Local title and keyword filter. This does not run a literature search.</p>
        <p className={styles.count} role="status">{visiblePapers.length} of 3 saved papers shown</p>
        <ul className={styles.paperList} aria-label="Saved paper selection">
          {visiblePapers.map((item) => (
            <li key={item.id}>
              <button type="button" className={styles.paperButton} aria-pressed={paperId === item.id}
                aria-controls="saved-comparison" onClick={() => selectPaper(item.id)}>
                <span className={styles.paperHeading}>{item.label}<span className={styles.paperYear}>{item.year}</span></span>
                <span className={styles.paperTitle}>{item.title}</span>
                <span className={styles.paperTags}>{item.tags.join(' · ')}</span>
              </button>
            </li>
          ))}
        </ul>
        {visiblePapers.length === 0 && <p className={styles.hint}>No match in this small saved collection. Clear the filter to see all three papers.</p>}
      </section>

      <section className={styles.comparisonSection} aria-labelledby="saved-comparison">
        <h3 id="saved-comparison">02 · Compare a question across sources</h3>
        <p className={styles.question}>{demo.question}</p>
        <p className={styles.intro}>The values below are illustrative comparison notes written for this demo. They are not researcher submissions or AI outputs. Select any cell to open its saved passage result; opening or returning never edits a comparison value.</p>
        <p className={styles.hint} id="comparison-scroll-help">All three papers remain in the board. On a narrow screen, scroll the table sideways.</p>
        <div ref={tableFrame} className={styles.tableFrame} role="region" aria-label="Three-paper comparison table"
          aria-describedby="comparison-scroll-help" tabIndex={0}>
          <table className={styles.board}>
            <caption>Saved example · three papers × three fields · unverified illustrative notes</caption>
            <thead><tr><th scope="col">Review field</th>{demo.papers.map((item) => <th key={item.id} scope="col">{item.label}</th>)}</tr></thead>
            <tbody>{demo.fields.map((item) => (
              <tr key={item.id}>
                <th scope="row">{item.label}</th>
                {demo.papers.map((candidate) => {
                  const value = candidate.cells.find((entry) => entry.fieldId === item.id)!;
                  const selected = paperId === candidate.id && fieldId === item.id;
                  return <td key={candidate.id}>
                    <button type="button" className={styles.cellButton} aria-pressed={selected}
                      ref={(node) => { const key = `${candidate.id}:${item.id}`; if (node) cells.current.set(key, node); else cells.current.delete(key); }}
                      aria-label={`Open saved passages for ${item.label} for ${candidate.label}`}
                      aria-controls="saved-passage-results-panel" onClick={() => navigate('passages', candidate.id, item.id)}>
                      <span>{value.value ?? 'Not established in this excerpt'}</span>
                      <span className={styles.cellState}>{value.state === 'not_established' ? 'partial context · open question' : 'illustrative note · needs review'}</span>
                      <span className={styles.inspectLabel}>open saved passages <span aria-hidden="true">↗</span></span>
                    </button>
                  </td>;
                })}
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      <section id="saved-passage-results-panel" className={styles.passageSection} aria-labelledby="saved-passage-results">
        <h3 id="saved-passage-results" ref={passageHeading} tabIndex={-1}>03 · Saved example retrieval</h3>
        <p className={styles.selection} role="status">Comparison: Asian women, diet and gut microbiome · one-paper scope: {paper.label} · field: {field.label}</p>
        <p className={styles.question}>{subquestions[fieldId]}</p>
        <p className={styles.hint}>One curated saved excerpt is available for this cell. These are precomputed demonstration results, not a live query, a ranking comparison, or a complete paper search. No search runs when you navigate here.</p>
        <article className={styles.savedPassage} aria-label={`Saved passage for ${field.label}`}>
          <span className={styles.label}>saved result 1 of 1 · {excerpt.sourceType === 'abstract' ? 'abstract only' : 'retained full text'} · {excerpt.section}</span>
          <h4>{paper.title}</h4>
          <p>{excerpt.quote}</p>
          {cell.value === null && <p className={styles.hint}>This saved result does not establish the requested reproductive-lifespan information. It does not establish whole-paper absence.</p>}
          <div className={styles.journeyActions}>
            <button type="button" onClick={() => navigate('source')} aria-controls="saved-evidence-panel">Inspect exact saved passage</button>
            <button type="button" onClick={() => navigate('comparison')}>Back to comparison cell</button>
          </div>
        </article>
      </section>

      <section id="saved-evidence-panel" className={styles.inspector} aria-labelledby="saved-evidence">
        <h3 id="saved-evidence" ref={inspector} tabIndex={-1}>04 · Inspect the exact source</h3>
        <p className={styles.selection} role="status">{paper.label} · {field.label}</p>
        <div className={styles.journeyActions}>
          <button type="button" onClick={() => navigate('passages')}>Back to saved passage results</button>
          <button type="button" onClick={() => navigate('comparison')}>Back to comparison cell</button>
        </div>
        <span className={styles.label}>{excerpt.sourceType === 'abstract' ? 'abstract excerpt' : 'full-text excerpt'} · {excerpt.section}</span>
        <blockquote className={styles.quote}><p>“{excerpt.quote}”</p></blockquote>
        <p className={styles.result}>{cell.value === null
          ? 'This selected passage does not establish an effect on reproductive lifespan. This is an unresolved question in partial context, not a claim that the whole paper contains no relevant information.'
          : 'The quotation and its location are reproducible. Whether this note is an appropriate interpretation still requires a researcher’s judgment.'}</p>
        <details className={styles.context} key={`${paperId}-${fieldId}`}>
          <summary>Surrounding context and exact anchor</summary>
          <p className={styles.contextText}>{excerpt.contextStart > 0 && '…'}{context.slice(0, start).join('')}<mark>{context.slice(start, end).join('')}</mark>{context.slice(end).join('')}{excerpt.contextEnd < excerpt.blockLength && '…'}</p>
          <dl className={styles.anchors}>
            <dt>Canonical block</dt><dd>{excerpt.blockId}</dd>
            <dt>Quotation offsets</dt><dd>[{excerpt.quoteStart}, {excerpt.quoteEnd})</dd>
            <dt>Context offsets</dt><dd>[{excerpt.contextStart}, {excerpt.contextEnd}) of {excerpt.blockLength} characters</dd>
            <dt>Parser</dt><dd>{paper.parserId}</dd>
            <dt>Source SHA-256</dt><dd>{paper.sourceSha256}</dd>
          </dl>
          <p className={styles.hint}>Offsets count Unicode code points in one whitespace-normalized block from the retained XML. Context is deliberately partial. An exact anchor establishes location and identity, not scientific support.</p>
        </details>
        <div className={styles.citation}>
          <span className={styles.label}>citation &amp; reuse</span>
          <p>{paper.citation}</p>
          <div className={styles.links}><a href={paper.sourceUrl}>Read the original paper ↗</a><a href={paper.retainedXmlUrl}>Retained source XML ↗</a></div>
          <details className={styles.attribution} key={paperId}>
            <summary>Attribution and license</summary>
            <p>{paper.attribution}</p>
            <p><a href={paper.licenseUrl}>Creative Commons Attribution 4.0</a>. Display transformations: selected excerpts, normalized whitespace and highlighted quotation. Original XML bytes remain unchanged in the public source bundle.</p>
          </details>
        </div>
      </section>

      <div className={styles.actions}>
        <a href="#literature-saved-demo">Try the demo · saved example, read-only</a>
        {downloadReady && <>
          <a href={download.archive_path} download>Download local beta · setup required</a>
          <a href={download.installation_path}>Installation</a>
          <a href={download.license_path}>MIT license</a>
        </>}
        <a href="https://github.com/hnt119/lit-rev-engine">View source ↗</a>
      </div>
      <p className={styles.downloadNotice}>Local beta — setup required. Version {download.version} is the full Track A source distribution, not a standalone installer. It includes no runtimes, credentials or model weights. The default offline/manual workflow needs no inference. New maps and optional AI features require explicit separate configuration; the beta retains their existing resource and human-review limits.</p>
      {!downloadReady && <p className={styles.downloadNotice}>A verified MIT beta artifact has not been bound to this source overlay. Download, installation and license-file links remain unavailable until the matching package is supplied.</p>}
      <details className={styles.downloadDetails}>
        <summary>Setup requirements and download verification</summary>
        <p>Requires Python 3.12, Node.js 24 and pnpm 10.20.0. Internet access is required to install locked dependencies. Start with the README inside the archive. Models stay optional, separately acquired and off by default.</p>
        <p>Beta target: macOS Apple Silicon. The validated platform is macOS arm64; Linux installation is unverified and Windows is unsupported. The download's capability and validation record separates software checks, provider checks and real-model checks.</p>
        <p>MIT covers the owner's original engine code. Public articles, datasets, model weights and dependencies retain their own terms. It does not relicense private research data. The separate protocol-review pilot is not included in this Track A download.</p>
        {downloadReady && <>
          <div className={styles.links}><a href={download.manifest_path} download>Download file manifest</a><a href={download.checksums_path} download>Download SHA256SUMS</a></div>
          <span className={styles.label}>ZIP SHA-256</span>
          <code className={styles.downloadHash}>{download.archive_sha256}</code>
          <span className={styles.label}>Committed source</span>
          <code className={styles.downloadHash}>{download.source_commit}</code>
          <p>The exact beta source snapshot is inside the ZIP. The source action above opens the existing public repository; preparation of this page does not itself publish the new commit, release or website.</p>
        </>}
      </details>
      <p className={styles.boundary}>Saved source capture: {demo.capturedAt.slice(0, 10)}. No backend, account, model or browser storage is used by this demo. Scientific usefulness and human review quality have not been validated here.</p>
    </div>
  );
}
