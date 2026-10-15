/* Local-only review UI. Receipt and reviewer strings are always inert text. */
(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const ui = Object.fromEntries([
    "loading", "load-error", "workbench", "display-mode", "question-select",
    "question-text", "question-components", "no-components", "bundle-choices",
    "source-select", "source-metadata", "source-blocks", "source-inspect-message",
    "selected-bundle", "passages", "assessment-form", "reviewer", "assessment-status",
    "reason", "missing-components", "contradiction", "source-inspected", "supersedes",
    "revision-note", "save-button", "new-draft", "save-error", "save-result",
    "review-timer", "assessment-history", "packet-provenance", "packet-tag",
  ].map((id) => [id, byId(id)]));
  const state = {
    session: null, question: null, bundle: null, source: null, anchor: null,
    drafts: new Map(), blocks: new Map(), saving: false, sequence: 0,
  };
  const statuses = {
    not_assessed: "Not assessed", sufficient: "Sufficient", partial: "Partial",
    insufficient: "Insufficient", uncertain: "Uncertain",
  };
  const ratingLabels = ["0 · irrelevant / wrong", "1 · background", "2 · partial", "3 · direct"];

  function node(tag, text, className) {
    const result = document.createElement(tag);
    if (text !== undefined && text !== null) result.textContent = String(text);
    if (className) result.className = className;
    return result;
  }
  function option(value, label) {
    const result = node("option", label);
    result.value = value;
    return result;
  }
  function tell(target, message) {
    target.textContent = message;
    target.hidden = !message;
  }
  function metadata(rows) {
    const list = node("dl", null, "metadata-list");
    for (const [label, value] of rows) {
      list.append(node("dt", label));
      const cell = node("dd", value === undefined || value === null ? "Not retained" : value);
      if (label.toLowerCase().includes("sha256") || label.endsWith("ID")) cell.className = "hash";
      list.append(cell);
    }
    return list;
  }
  function detail(title, child) {
    const result = node("details");
    result.append(node("summary", title), child);
    return result;
  }
  const serialize = (value) => JSON.stringify(value, null, 2);
  const locationText = (locator) => serialize(locator || {});
  function currentRecords() {
    const rows = state.session.assessments.filter((row) => row.bundle_id === state.bundle.id);
    const replaced = new Set(rows.map((row) => row.supersedes).filter(Boolean));
    return rows.filter((row) => !replaced.has(row.id));
  }
  function blankDraft() {
    return {
      packet_id: state.session.packet.packet_id, bundle_id: state.bundle.id,
      reviewer: "", status: "not_assessed", reason: "",
      ratings: state.bundle.passages.map((passage) => ({
        passage_id: passage.id, rating: null,
        component_ratings: Object.fromEntries(state.question.components.map((part) => [part.id, null])),
      })),
      supporting_passage_ids: [], missing_components: [], contradiction: false,
      source_inspected: false, supersedes: null, review_seconds: null,
      elapsedMs: 0, startedAt: Date.now(), locked: false, savedId: null, dirty: false,
    };
  }
  function draft() {
    if (!state.drafts.has(state.bundle.id)) state.drafts.set(state.bundle.id, blankDraft());
    return state.drafts.get(state.bundle.id);
  }
  function pauseTimer() {
    if (!state.bundle || !state.drafts.has(state.bundle.id)) return;
    const own = draft();
    if (own.startedAt !== null) own.elapsedMs += Date.now() - own.startedAt;
    own.startedAt = null;
  }
  function reviewSeconds(own) {
    return Math.round((own.elapsedMs + (own.startedAt === null ? 0 : Date.now() - own.startedAt)) / 1000);
  }
  function touch() {
    draft().dirty = true;
    tell(ui["save-error"], "");
  }
  function findSource(passage) {
    return state.session.packet.sources.find((source) =>
      source.record_id === passage.record_id && source.document_id === passage.document_id &&
      source.document_version === passage.document_version && source.source_sha256 === passage.source_sha256);
  }
  function renderProvenance() {
    const packet = state.session.packet;
    ui["packet-tag"].textContent = `Packet ${packet.packet_id.slice(0, 12)}`;
    ui["packet-provenance"].replaceChildren(metadata([
      ["Packet ID", packet.packet_id],
      ...Object.entries(packet.binding).map(([key, value]) => [key, value]),
      ["Display mode", packet.display_mode], ["Review basis", "Single-human judgment"],
      ["Independent verification", "NOT_RUN"], ["Source answerability", "Not assessed"],
      ["Current ledger state", "Not checked"],
    ]));
    const limits = node("ul");
    for (const limitation of packet.limitations || []) limits.append(node("li", limitation));
    ui["packet-provenance"].append(limits);
    const revealed = state.session.reveal_methods === true && packet.display_mode === "revealed";
    ui["display-mode"].classList.toggle("revealed", revealed);
    tell(ui["display-mode"], revealed
      ? "Diagnostic reveal enabled: method names, scores, and selection reasons are visible. Saved assessments are marked revealed. This view is no longer blinded."
      : "Blinded display: method names, scores, and selection reasons are hidden. The software demo uses previously exposed fixtures; saved-receipt judgments do not establish fresh accuracy confirmation.");
  }
  function renderQuestion() {
    ui["question-text"].textContent = state.question.text;
    ui["question-components"].replaceChildren();
    for (const part of state.question.components) {
      const item = node("li");
      item.append(node("span", `${part.id} · `, "component-id"), node("span", part.text));
      ui["question-components"].append(item);
    }
    ui["no-components"].hidden = state.question.components.length !== 0;
    renderBundleChoices();
  }
  function renderBundleChoices() {
    ui["bundle-choices"].replaceChildren();
    const bundles = state.session.packet.bundles.filter((bundle) => bundle.question_id === state.question.id);
    for (const bundle of bundles) {
      const button = node("button", null, "bundle-choice");
      button.type = "button";
      button.setAttribute("aria-pressed", String(bundle.id === state.bundle.id));
      const savedCount = state.session.assessments.filter((row) => row.bundle_id === bundle.id).length;
      button.append(node("strong", `Bundle ${bundle.label}`),
        node("span", `${bundle.passages.length} passages · ${savedCount} saved records`));
      button.addEventListener("click", () => selectBundle(bundle));
      button.disabled = state.saving;
      ui["bundle-choices"].append(button);
    }
  }
  function renderSourceChoices() {
    ui["source-select"].replaceChildren();
    for (const source of state.session.packet.sources) {
      ui["source-select"].append(option(source.id,
        `${source.title || source.document_id} · version ${source.document_version}`));
    }
    const firstPassage = state.bundle.passages[0];
    if (!state.source) state.source = (firstPassage && findSource(firstPassage)) || state.session.packet.sources[0];
    if (!state.source) {
      ui["source-metadata"].replaceChildren(node("p", "No retained source text is available.", "empty"));
      return;
    }
    ui["source-select"].value = state.source.id;
    renderSource();
  }
  function appendSourceText(target, text, anchor) {
    // Saved Python anchors count Unicode code points, rather than UTF-16 units.
    const characters = Array.from(text);
    const exact = anchor && Number.isInteger(anchor.start) && Number.isInteger(anchor.end) &&
      anchor.start >= 0 && anchor.end > anchor.start && anchor.end <= characters.length &&
      characters.slice(anchor.start, anchor.end).join("") === anchor.quote;
    if (!exact) {
      target.textContent = text;
      return false;
    }
    target.append(document.createTextNode(characters.slice(0, anchor.start).join("")),
      node("mark", characters.slice(anchor.start, anchor.end).join("")),
      document.createTextNode(characters.slice(anchor.end).join("")));
    return true;
  }
  function renderSource() {
    const source = state.source;
    if (!source) return;
    ui["source-metadata"].replaceChildren(node("h3", source.title || "Untitled retained source"), metadata([
      ["Record ID", source.record_id], ["Document ID", source.document_id], ["Version", source.document_version],
    ]), detail("Saved source provenance", metadata([
      ["Source SHA256", source.source_sha256], ["Blocks SHA256", source.blocks_sha256],
      ["Saved source URL", source.source_url], ["Retained blocks", source.blocks.length],
    ])));
    ui["source-blocks"].replaceChildren();
    state.blocks.clear();
    let highlighted = false;
    for (const block of source.blocks) {
      const target = state.anchor && state.anchor.block_id === block.id;
      const article = node("article", null, `source-block${target ? " targeted" : ""}`);
      article.setAttribute("tabindex", "-1");
      article.append(node("div", `Block ${block.ordinal} · ${block.id}`, "block-label"));
      const text = node("p", null, "block-text");
      if (appendSourceText(text, block.text, target ? state.anchor : null)) highlighted = true;
      article.append(text, node("div", `Locator: ${locationText(block.locator)}`, "block-label"));
      ui["source-blocks"].append(article);
      state.blocks.set(block.id, article);
    }
    ui["source-inspect-message"].textContent = state.anchor
      ? (highlighted ? "Selected passage highlighted in its retained source block." : "Saved anchor could not be matched in this retained text.")
      : "Choose “Inspect source” on a passage to locate its exact saved anchor.";
    if (state.anchor && state.blocks.has(state.anchor.block_id)) {
      const block = state.blocks.get(state.anchor.block_id);
      block.scrollIntoView({ block: "nearest" });
      block.focus({ preventScroll: true });
    }
  }
  function inspectPassage(passage) {
    const source = findSource(passage);
    if (!source) {
      ui["source-inspect-message"].textContent = "This passage has no matching retained source version.";
      return;
    }
    state.source = source;
    state.anchor = passage.anchor;
    ui["source-select"].value = source.id;
    renderSource();
  }
  function ratingControl(labelText, value, onChange) {
    const id = `rating-${++state.sequence}`;
    const label = node("label", labelText);
    label.htmlFor = id;
    const select = node("select");
    select.id = id;
    select.append(option("", "Unassessed"));
    ratingLabels.forEach((text, index) => select.append(option(String(index), text)));
    select.value = value === null || value === undefined ? "" : String(value);
    select.disabled = draft().locked || state.saving;
    select.addEventListener("change", () => {
      onChange(select.value === "" ? null : Number(select.value));
      touch();
    });
    return [label, select];
  }
  function checkbox(text, checked, onChange, disabled = false) {
    const label = node("label", null, "check");
    const input = node("input");
    input.type = "checkbox";
    input.checked = checked;
    input.disabled = disabled;
    input.addEventListener("change", () => { onChange(input.checked); touch(); });
    label.append(input, node("span", text));
    return label;
  }
  function setMembership(values, value, checked) {
    if (checked && !values.includes(value)) values.push(value);
    if (!checked && values.includes(value)) values.splice(values.indexOf(value), 1);
  }
  function renderPassages() {
    const own = draft();
    ui.passages.replaceChildren();
    if (!state.bundle.passages.length) ui.passages.append(node("p", "This bundle contains no passages.", "empty"));
    for (const passage of state.bundle.passages) {
      const row = own.ratings.find((rating) => rating.passage_id === passage.id);
      const card = node("article", null, "passage-card");
      const heading = node("div", null, "passage-heading");
      const inspect = node("button", "Inspect source");
      inspect.type = "button";
      inspect.addEventListener("click", () => inspectPassage(passage));
      heading.append(node("h3", `Passage ${passage.rank}`), inspect);
      card.append(heading, node("span", passage.candidate_kind === "title_or_navigation" ? "Title / navigation" : "Source block", "badge passage-kind"),
        node("p", passage.title || passage.document_id, "passage-title"),
        node("blockquote", passage.anchor.quote, "passage-quote"));
      const meta = node("div", null, "passage-meta");
      meta.append(node("span", `Version ${passage.document_version} · block ${passage.anchor.block_id} · characters ${passage.anchor.start}–${passage.anchor.end}`),
        node("p", `Locator: ${locationText(passage.locator)}`));
      meta.append(detail("Passage binding", metadata([
        ["Passage ID", passage.id], ["Record ID", passage.record_id], ["Document ID", passage.document_id],
        ["Source SHA256", passage.source_sha256], ["Blocks SHA256", passage.blocks_sha256],
        ["Candidate kind", passage.candidate_kind],
      ])));
      card.append(meta);
      if (state.session.reveal_methods === true && state.session.packet.display_mode === "revealed") {
        const diagnostic = node("details", null, "diagnostic");
        diagnostic.append(node("summary", "Revealed diagnostic details"), node("pre", serialize({
          method: state.bundle.method_key, score: passage.score,
          query_scores: passage.query_scores, selection_reasons: passage.selection_reasons,
        })));
        card.append(diagnostic);
      }
      const ratings = node("div", null, "rating-grid");
      ratings.append(...ratingControl("Whole-question relevance", row.rating, (value) => { row.rating = value; }));
      for (const part of state.question.components) {
        ratings.append(...ratingControl(`${part.id} · ${part.text}`, row.component_ratings[part.id],
          (value) => { row.component_ratings[part.id] = value; }));
      }
      card.append(ratings, checkbox(`Use passage ${passage.rank} as supporting evidence`,
        own.supporting_passage_ids.includes(passage.id),
        (checked) => setMembership(own.supporting_passage_ids, passage.id, checked), own.locked || state.saving));
      ui.passages.append(card);
    }
  }
  function renderMissingComponents() {
    const own = draft();
    ui["missing-components"].replaceChildren();
    const parts = state.question.components.length ? state.question.components : [{ id: "whole_question", text: "The whole question" }];
    for (const part of parts) ui["missing-components"].append(checkbox(`${part.id} · ${part.text}`,
      own.missing_components.includes(part.id),
      (checked) => setMembership(own.missing_components, part.id, checked), own.locked || state.saving));
  }
  function renderForm() {
    const own = draft();
    ui["reviewer"].value = own.reviewer;
    ui["assessment-status"].value = own.status;
    ui.reason.value = own.reason;
    ui.contradiction.checked = own.contradiction;
    ui["source-inspected"].checked = own.source_inspected;
    ui.reason.required = own.status !== "not_assessed";
    ui.supersedes.replaceChildren(option("", "Save a new assessment"));
    for (const record of currentRecords()) ui.supersedes.append(option(record.id,
      `Replace ${record.reviewer} · ${statuses[record.status] || record.status} · ${record.id.slice(0, 8)}`));
    ui.supersedes.value = own.supersedes || "";
    for (const id of ["reviewer", "assessment-status", "reason", "contradiction", "source-inspected", "supersedes"])
      ui[id].disabled = own.locked || state.saving;
    ui["save-button"].disabled = own.locked || state.saving;
    ui["save-button"].textContent = state.saving ? "Saving…" : own.locked ? "Saved" : "Save assessment";
    ui["new-draft"].hidden = !own.locked;
    tell(ui["revision-note"], own.supersedes ? `Explicit replacement of assessment ${own.supersedes}. The earlier record will remain in history.` : "");
    ui["review-timer"].textContent = own.locked ? "Review time saved" : "Time in this bundle is recorded on save";
    ui["question-select"].disabled = state.saving;
  }
  function renderHistory() {
    const rows = state.session.assessments.filter((row) => row.bundle_id === state.bundle.id);
    const current = new Set(currentRecords().map((row) => row.id));
    ui["assessment-history"].replaceChildren();
    if (!rows.length) {
      ui["assessment-history"].append(node("p", "No saved assessments for this bundle.", "empty"));
      return;
    }
    const sorted = rows.map((row, index) => ({ row, index })).sort((a, b) =>
      Number(current.has(b.row.id)) - Number(current.has(a.row.id)) || b.index - a.index);
    for (const { row } of sorted) {
      const article = node("article", null, "history-record");
      const isCurrent = current.has(row.id);
      article.append(node("span", isCurrent ? "CURRENT" : "SUPERSEDED", `badge${isCurrent ? "" : " old"}`),
        node("p", `${row.reviewer} · ${statuses[row.status] || row.status}`, "status-summary"),
        node("p", `${row.created_at} · ${row.display_mode} display`, "small muted"),
        node("p", row.reason || "No assessment reason recorded."),
        node("p", `Source inspected: ${row.source_inspected ? "yes" : "no"} · Contradiction: ${row.contradiction ? "yes" : "no"}`, "small"),
        node("p", `Assessment ${row.id}`, "history-id"));
      if (row.supersedes) article.append(node("p", `Replaces ${row.supersedes}`, "history-id"));
      const passageLabel = (id) => {
        const passage = state.bundle.passages.find((item) => item.id === id);
        return passage ? `Passage ${passage.rank}` : id;
      };
      const savedRatings = node("ul");
      const grade = (value) => value === null || value === undefined ? "unassessed" : ratingLabels[value];
      for (const rating of row.ratings) {
        const components = Object.entries(rating.component_ratings).map(([id, value]) => `${id}: ${grade(value)}`);
        savedRatings.append(node("li", `${passageLabel(rating.passage_id)} · whole question: ${grade(rating.rating)}` +
          (components.length ? ` · ${components.join("; ")}` : "")));
      }
      if (!row.ratings.length) savedRatings.append(node("li", "No passage ratings recorded."));
      const savedDetails = node("div");
      savedDetails.append(metadata([
        ["Supporting evidence", row.supporting_passage_ids.map(passageLabel).join(", ") || "None declared"],
        ["Missing components", row.missing_components.join(", ") || "None declared"],
        ["Review seconds", row.review_seconds === null ? "Not recorded" : row.review_seconds],
      ]), savedRatings);
      article.append(detail("Saved ratings and support", savedDetails),
        detail("Immutable record and binding", node("pre", serialize(row))));
      if (isCurrent) {
        const revise = node("button", "Revise this assessment");
        revise.type = "button";
        revise.disabled = state.saving;
        revise.addEventListener("click", () => reviseRecord(row));
        article.append(revise);
      }
      ui["assessment-history"].append(article);
    }
  }
  function renderReview() {
    const revealed = state.session.reveal_methods === true && state.session.packet.display_mode === "revealed";
    ui["selected-bundle"].textContent = `Bundle ${state.bundle.label} · ${state.bundle.passages.length} passages` +
      (revealed ? ` · diagnostic method: ${state.bundle.method_key}` : " · anonymous display");
    renderPassages();
    renderMissingComponents();
    renderForm();
    renderHistory();
  }
  function selectBundle(bundle) {
    if (state.saving) return;
    pauseTimer();
    state.bundle = bundle;
    const own = draft();
    if (!own.locked) own.startedAt = Date.now();
    tell(ui["save-error"], "");
    tell(ui["save-result"], own.savedId ? `Saved assessment ${own.savedId}. Use “Revise this assessment” to append a replacement.` : "");
    renderBundleChoices();
    renderReview();
  }
  function reviseRecord(record) {
    pauseTimer();
    const own = blankDraft();
    for (const key of ["reviewer", "status", "reason", "supporting_passage_ids", "missing_components", "contradiction", "source_inspected"])
      own[key] = JSON.parse(JSON.stringify(record[key]));
    for (const row of own.ratings) {
      const saved = record.ratings.find((rating) => rating.passage_id === row.passage_id);
      if (saved) { row.rating = saved.rating; row.component_ratings = { ...row.component_ratings, ...saved.component_ratings }; }
    }
    own.supersedes = record.id;
    own.dirty = true;
    state.drafts.set(state.bundle.id, own);
    tell(ui["save-error"], "");
    tell(ui["save-result"], "");
    renderReview();
    ui.reviewer.focus();
  }
  function readPayload() {
    const own = draft();
    const value = {};
    for (const key of ["packet_id", "bundle_id", "reviewer", "status", "reason", "ratings", "supporting_passage_ids",
      "missing_components", "contradiction", "source_inspected", "supersedes"]) value[key] = own[key];
    value.reviewer = value.reviewer.trim();
    value.reason = value.reason.trim();
    value.review_seconds = reviewSeconds(own);
    return value;
  }
  function checkPayload(value) {
    if (!value.reviewer) return "Enter an explicit reviewer label before saving.";
    if (value.reviewer.length > 160) return "Use a reviewer label of at most 160 characters.";
    if (new TextEncoder().encode(value.reason).length > 20000) return "The reason exceeds the 20,000-byte saved-text limit. Shorten it before saving.";
    if (value.status !== "not_assessed" && !value.reason) return "Explain the judgment in the reason field.";
    if (value.status === "sufficient" && (!value.supporting_passage_ids.length || value.missing_components.length))
      return "A sufficient judgment needs at least one supporting passage and no missing components.";
    if (["partial", "insufficient"].includes(value.status) && !value.missing_components.length)
      return "Select the missing components for a partial or insufficient judgment.";
    const current = currentRecords();
    const sameReviewer = current.find((row) => row.reviewer === value.reviewer);
    if (sameReviewer && value.supersedes !== sameReviewer.id)
      return "This reviewer already has a current assessment. Explicitly choose it in the history action or use “Revise this assessment”.";
    const replaced = value.supersedes && current.find((row) => row.id === value.supersedes);
    if (value.supersedes && (!replaced || replaced.reviewer !== value.reviewer))
      return "A replacement must use the same reviewer label as the selected current assessment.";
    return null;
  }
  async function responseJson(response) {
    let value;
    try { value = await response.json(); }
    catch (_) { throw new Error(`The local server returned an unreadable response (${response.status}). Your draft is preserved.`); }
    if (!response.ok) {
      const message = value.error || value.message || `The local server rejected the request (${response.status}).`;
      throw new Error(typeof message === "string" ? message : serialize(message));
    }
    return value;
  }
  async function save(event) {
    event.preventDefault();
    if (state.saving || draft().locked) return;
    const value = readPayload();
    const issue = checkPayload(value);
    if (issue) { tell(ui["save-error"], issue); return; }
    const own = draft();
    tell(ui["save-error"], "");
    tell(ui["save-result"], "");
    state.saving = true;
    renderBundleChoices();
    renderReview();
    try {
      const response = await fetch("/api/assessments", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-Workbench-CSRF": state.session.csrf_token },
        body: JSON.stringify(value),
      });
      const result = await responseJson(response);
      if (!result.assessment || !result.assessment.id) throw new Error("The save response did not contain an assessment record. Reload to check the saved history before trying again.");
      state.session.assessments.push(result.assessment);
      pauseTimer();
      own.locked = true;
      own.savedId = result.assessment.id;
      own.dirty = false;
      tell(ui["save-result"], `Saved assessment ${result.assessment.id}. It will remain available after reload. Use “Revise this assessment” to append a replacement.`);
    } catch (error) {
      tell(ui["save-error"], `${error.message || "Save failed."}\nYour draft is preserved. If the connection failed after submission, reload and inspect history before retrying.`);
    } finally {
      state.saving = false;
      renderBundleChoices();
      renderReview();
    }
  }
  function bindInputs() {
    for (const [id, key, type] of [
      ["reviewer", "reviewer", "value"], ["reason", "reason", "value"],
      ["assessment-status", "status", "value"], ["contradiction", "contradiction", "checked"],
      ["source-inspected", "source_inspected", "checked"], ["supersedes", "supersedes", "value"],
    ]) ui[id].addEventListener(type === "checked" || id === "assessment-status" || id === "supersedes" ? "change" : "input", () => {
      draft()[key] = id === "supersedes" ? (ui[id].value || null) : ui[id][type];
      touch();
      if (id === "assessment-status") ui.reason.required = draft().status !== "not_assessed";
      if (id === "supersedes") tell(ui["revision-note"], draft().supersedes ? `Explicit replacement of assessment ${draft().supersedes}. The earlier record will remain in history.` : "");
    });
    ui["question-select"].addEventListener("change", () => {
      pauseTimer();
      state.question = state.session.packet.questions.find((row) => row.id === ui["question-select"].value);
      const bundle = state.session.packet.bundles.find((row) => row.question_id === state.question.id);
      selectBundle(bundle);
      renderQuestion();
    });
    ui["source-select"].addEventListener("change", () => {
      state.source = state.session.packet.sources.find((row) => row.id === ui["source-select"].value);
      state.anchor = null;
      renderSource();
    });
    ui["assessment-form"].addEventListener("submit", save);
    ui["new-draft"].addEventListener("click", () => {
      state.drafts.set(state.bundle.id, blankDraft());
      tell(ui["save-result"], "");
      tell(ui["save-error"], "");
      renderReview();
      ui.reviewer.focus();
    });
    document.addEventListener("visibilitychange", () => {
      if (!state.bundle) return;
      if (document.hidden) pauseTimer();
      else if (!draft().locked) draft().startedAt = Date.now();
    });
    window.addEventListener("beforeunload", (event) => {
      if ([...state.drafts.values()].some((own) => own.dirty && !own.locked)) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
  }
  async function start() {
    try {
      const response = await fetch("/api/session", { credentials: "same-origin", cache: "no-store" });
      const session = await responseJson(response);
      if (!session.packet || !session.packet.questions.length || !session.packet.bundles.length || !Array.isArray(session.assessments))
        throw new Error("The local server did not provide a usable review packet.");
      state.session = session;
      state.question = session.packet.questions[0];
      for (const question of session.packet.questions) ui["question-select"].append(option(question.id, `${question.id} · ${question.text}`));
      ui["question-select"].value = state.question.id;
      state.bundle = session.packet.bundles.find((row) => row.question_id === state.question.id);
      draft();
      bindInputs();
      renderProvenance();
      renderQuestion();
      renderSourceChoices();
      renderReview();
      ui.workbench.hidden = false;
      ui.loading.hidden = true;
    } catch (error) {
      ui.loading.hidden = true;
      tell(ui["load-error"], `${error.message || "Unable to load the local review session."} Reload this page after the local server is available.`);
    }
  }
  start();
})();
