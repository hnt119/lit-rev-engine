"""Static, offline reviewer shell; receipt text enters the page through textContent."""


def render_page() -> str:
    """Return a CSP-compatible shell without embedding packet or assessment data."""
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Local evidence review</title>
  <link rel="stylesheet" href="/assets/workbench.css">
  <script src="/assets/workbench.js" defer></script>
</head>
<body>
  <header class="site-header">
    <p class="eyebrow">Local reviewer workbench</p>
    <h1>Inspect sources. Judge evidence.</h1>
    <p class="intro">Compare saved passage bundles against the question and its components.</p>
    <div class="evidence-notice">
      <strong>Single-human judgment</strong>
      <span>Independent verification: <b>NOT_RUN</b></span>
      <span>Source answerability: <b>not assessed</b></span>
      <span>Current ledger state: <b>not checked</b></span>
    </div>
    <p class="scope-note">Saved-receipt assessment. The software demo uses regression fixtures that were already exposed. No retrieval accuracy or fresh confirmation is inferred from this view.</p>
    <p id="display-mode" class="mode-banner" hidden></p>
  </header>
  <main id="app">
    <div id="loading" class="panel" role="status">Loading the saved review packet…</div>
    <div id="load-error" class="error panel" role="alert" hidden></div>
    <div id="workbench" hidden>
      <section class="panel question-panel" aria-labelledby="question-heading">
        <div class="section-heading"><h2 id="question-heading">1. Read the question</h2><span id="packet-tag" class="small muted"></span></div>
        <label for="question-select">Question</label>
        <select id="question-select"></select>
        <p id="question-text" class="question-text"></p>
        <ol id="question-components" class="components"></ol>
        <p id="no-components" class="muted" hidden>Judge the whole question; this question has no separate components.</p>
        <div class="bundle-heading"><h3>Anonymous passage bundle</h3><p class="small muted">Judge each bundle on its evidence. Ratings begin unassessed.</p></div>
        <div id="bundle-choices" class="bundle-choices" role="group" aria-label="Choose passage bundle"></div>
      </section>
      <div class="workspace">
        <section class="panel source-panel" aria-labelledby="source-heading">
          <h2 id="source-heading">2. Inspect retained source text</h2>
          <p class="small muted">Full retained canonical text, grouped by source block. This is saved text, not the original PDF layout or a live ledger check. Viewing text does not automatically mark a source as inspected.</p>
          <label for="source-select">Source document</label>
          <select id="source-select"></select>
          <div id="source-metadata" class="source-metadata"></div>
          <p id="source-inspect-message" class="small" role="status"></p>
          <div id="source-blocks" class="source-blocks" tabindex="0" aria-label="Retained canonical source text"></div>
        </section>
        <section class="review-panel" aria-labelledby="review-heading">
          <form id="assessment-form">
            <div class="panel">
              <h2 id="review-heading">3. Assess the selected bundle</h2>
              <p id="selected-bundle" class="small muted"></p>
              <details class="rubric"><summary>Passage rating rubric</summary><ul><li><b>Unassessed:</b> no judgment recorded.</li><li><b>0:</b> irrelevant, or wrong time or concept.</li><li><b>1:</b> background context only.</li><li><b>2:</b> partial support; a material detail is missing.</li><li><b>3:</b> direct support for the question or component.</li></ul></details>
              <div id="passages"></div>
            </div>
            <div class="panel assessment-panel">
              <h3>Bundle judgment</h3>
              <p class="small muted">Sufficiency concerns this retrieved bundle. A contradiction is recorded separately and does not automatically determine sufficiency.</p>
              <p id="revision-note" class="revision-note" hidden></p>
              <label for="reviewer">Reviewer label <span class="required">required</span></label>
              <input id="reviewer" name="reviewer" type="text" autocomplete="off" maxlength="160" required placeholder="Your name or reviewer code">
              <label for="assessment-status">Sufficiency</label>
              <select id="assessment-status" name="status">
                <option value="not_assessed">Not assessed</option>
                <option value="sufficient">Sufficient — the bundle supports the whole question</option>
                <option value="partial">Partial — some required evidence is missing</option>
                <option value="insufficient">Insufficient — required evidence is missing</option>
                <option value="uncertain">Uncertain — I cannot make a reliable judgment</option>
              </select>
              <label for="reason">Reason <span class="small muted">required for an assessed status</span></label>
              <textarea id="reason" name="reason" rows="4" maxlength="20000" placeholder="Explain support, gaps, limitations, or uncertainty."></textarea>
              <fieldset id="missing-fieldset"><legend>Missing question components</legend><p class="small muted">Select every missing component for partial or insufficient. A sufficient bundle must have no missing components and at least one supporting passage.</p><div id="missing-components"></div></fieldset>
              <label class="check"><input id="contradiction" type="checkbox"><span>I found contradictory evidence in this bundle</span></label>
              <label class="check"><input id="source-inspected" type="checkbox"><span>I inspected the retained source text for this judgment</span></label>
              <label for="supersedes">Assessment history action</label>
              <select id="supersedes"><option value="">Save a new assessment</option></select>
              <p class="small muted">A replacement appends a new record and preserves the earlier record. The same reviewer must explicitly replace their current assessment for this bundle.</p>
              <div id="save-error" class="error" role="alert" hidden></div>
              <div id="save-result" class="success" role="status" hidden></div>
              <div class="form-actions"><button id="save-button" type="submit" class="primary">Save assessment</button><button id="new-draft" type="button" hidden>Start another review</button><span id="review-timer" class="small muted"></span></div>
            </div>
          </form>
          <section class="panel history-panel" aria-labelledby="history-heading"><h2 id="history-heading">Saved assessments</h2><p class="small muted">Records persist in the local assessment store. Current records and their superseded history are shown for this bundle.</p><div id="assessment-history"></div></section>
        </section>
      </div>
      <details class="panel packet-details"><summary>Packet provenance and limits</summary><div id="packet-provenance"></div></details>
    </div>
  </main>
  <footer>Local evidence review · saved canonical text · no independent verification</footer>
  <noscript><p class="error panel">JavaScript is required to inspect sources and save assessments.</p></noscript>
</body>
</html>"""
