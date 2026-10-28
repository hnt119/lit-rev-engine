# Evidence Gap Navigator v0.2 — development guide

This guide describes the v0.2 development increment on top of the v0.1 investigation workflow. It is not included in the published Mac, Windows or source releases. PR #22 remains the separate, unmerged v0.1 review; this guide does not imply either increment has shipped. Core needs no model, key or neural download.

## Move around without losing the comparison

The workspace navigation stays available while you scroll. The current page lists only sections available in that view; selecting a section moves focus to it without replacing the page or resetting its drafts. On a narrow screen, expand **Navigate · [current page]** to choose a page or section, then continue in the compact view. Scrolling updates the active section without taking control of scrolling.

Open **Compare**, select an unresolved cell or use **Needs review**, and choose **Investigate related literature**. If more inspection of the original source may answer the question, choose **Inspect more context in this paper** first. The cell keeps its existing support judgment and inspected-scope result throughout.

## Draft and approve a follow-up search

1. Enter your reason and choose **Create investigation draft**. The saved origin retains the exact board definition, paper, field, submitted cell revision, saved draft, source-manifest identities and separately labeled editor snapshot. The reason is unsaved until this action completes.
2. Review the follow-up objective and editable plan. Approved concepts from the original search can provide a starting point. The field question is context; it does not silently become another PubMed restriction.
3. To build from your wording, choose **Suggest editable concepts**. The same Core builder is available in Discover and investigations. It uses a small deterministic phrase and wording table, with exact source phrases and separately labeled added wording. Suggested roles and synonyms are not validated scientific terminology or MeSH mappings. Specialist Boolean text remains editable as a manual strategy; uncertain or unsupported wording still needs your review.
4. Review the suggestions before choosing **Use suggestions as editable draft**. Replacing an existing plan requires an explicit choice. Edit or remove unwanted terms, choose each concept's role and search use, and resolve uncertainties. Optional preferences and screening criteria stay outside the query unless you deliberately change their use.
5. Choose **Approve reviewed Core terms for compilation**, then **Build reviewed Boolean strategies**. Required concept groups use AND; alternative terms within a group use OR. An optional broader strategy retains one reviewed anchor concept and exposes the omitted constraints for acknowledgment. Neither strategy has measured recall or precision.
6. Save the revised plan. Read the **exact executable PubMed query**, dates, sort and deferred or unresolved constraints, then approve that saved revision. Term review, plan saving and exact-query approval are separate steps. A query change requires a new saved revision and approval before execution.
7. In a configured live workspace, explicitly request diagnostics or run the approved search with a bounded result limit. Saved-example workspaces support drafting and audit inspection but cannot execute supplied queries. An offline demonstration may simulate provider responses; its visible simulation label is not evidence of a live PubMed request.
8. Review returned records as candidates and choose **Shortlist**, **Dismiss** or **Leave unassessed**. A shortlist alone adds no paper to a comparison and prepares no source.

Viewing, navigating, filtering or reopening does not request PubMed, model inference or source preparation. There is no hidden generation fallback. A failed provider request is not a zero-match finding; replaying a retained request does not silently start another provider attempt.

## Commit selected papers and prepare sources

Choose **Add evidence or expand comparison** to continue from the shortlist. Select the candidate records and any previous reports you want alongside them, name the follow-up collection and choose **Review selected papers for comparison**. Review exact duplicates and conflicting records; resolve the available choices explicitly. Changes to the selection require another preview before committing.

Choose **Add selected papers to comparison workflow** to save an immutable collection. This retains each paper's investigation, executed query, result snapshot and manual-selection provenance. It does not prepare sources or modify the original board. The existing comparison limit remains **30 papers and 6 fields**; an over-capacity selection must be reduced visibly rather than silently truncated.

Open the committed selection and explicitly choose **Prepare selected sources**. Read the saved job receipt and each paper's full-text, abstract-only, unavailable or failed outcome, then choose **Use this prepared selection** to continue with those sources. A failed preparation needs an explicit retry; an unavailable source is not evidence of absence. Preparation may access source providers only after this action.

**Publishing a new preparation changes the workspace's current source preparation.** The original comparison may therefore become historical and read-only. Its original source versions, references, drafts and submitted judgments remain retained and inspectable. They are not rewritten to use the new sources. Use the retained-preparation and saved-retrieval controls to reopen earlier work.

## Write a source-linked research evaluation

1. Enter the question for the prepared related papers and explicitly choose **Retrieve prepared passages**. Core lexical ranks help find text; they do not establish support.
2. Choose **Inspect related-paper passage** for a shortlisted paper committed through this investigation. Read the named paper, source type and exact excerpt. Original reports can appear as context in a mixed collection; they do not become related-paper evidence merely by appearing in the retrieval.
3. Choose **Use this passage in my research evaluation**. Review the research question, write your own interpretation, and acknowledge both inspection and attribution to the named related paper.
4. Choose **Save source-linked research evaluation**. The note retains the investigation and triggering cell, paper identity, exact source version/hash and excerpt range, interpretation and revision history. Reopen a saved evaluation to revise it explicitly.

A candidate citation or shortlist is not verified passage evidence. The evaluation remains separate from the original paper's cell. A source from Paper B cannot fill a missing fact as if Paper A contained it.

## Continue in an expanded comparison

After preparation, review **Continue in an expanded comparison**. Choose which prepared previous reports and new papers to include, review the comparison question and retained field questions, then choose **Create expanded comparison** and **Open expanded comparison**.

All cells on the new board begin unassessed, including cells for previous reports. Original judgments remain on their original board; they are not promoted to new source bindings. The expanded board exposes its investigation provenance and **Open original comparison and judgments**. Use the ordinary **Select evidence → Comment & judge → Review & save** workflow for each new entry.

## Return, reopen and export

Choose **Return to original cell** to inspect or continue the original comparison context. Reopen the cell's saved investigation to recover its saved plan, candidate decisions and research workflow. Draft changes are saved separately from plan revisions, evaluations and submitted cells; check **Draft: saved**. A stale revision or two-tab conflict requires explicit inspection and reconciliation. Failed edits remain available for comparison rather than overwriting another tab silently.

Use **Prepare readable audit export** to inspect and download Markdown or JSON. The audit retains the researcher's reason, captured origin, exact query revisions and approvals, provider receipts, candidate decisions, committed selections, inspected passages and evaluation revisions. The export is a private research record, not a portable access credential or complete application backup. Existing browser-session and private-directory protections still apply.

An unresolved cell is not proof of a scientific research gap. **Not found in inspected material** does not mean absent from the whole paper. Search matches, scores, source preparation and exact-text checks do not establish relevance, eligibility, study independence or scientific support. No automatic conflict judgment or gap score is produced.

Consult the [evaluation report](evidence_gap_navigator_evaluation.md) for source-bound checks and limits. Historical v0.1 test results do not validate later increments. Real PubMed execution, scientific quality and researcher usefulness must be reported separately from offline software tests.
