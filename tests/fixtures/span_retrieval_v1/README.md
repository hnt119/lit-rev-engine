# Source-first span development cases

The manifest fixes source text, questions, requirements and exact half-open Unicode code-point anchors before any B1 ranking runs. `SHA256SUMS` binds that fixture. Synthetic cases are authored for software testing. Three sources reference the existing rights-checked public pack by source/block hashes. They are agent-authored development cases, not human gold, unseen papers or held-out evidence.

The twelve paper/field cases share eleven source groups. Eight synthetic sources cover a late answer beyond character 1,200, Unicode/CRLF, negation, population versus author affiliation, multiple cohorts, table heading/row/footnote, abstract-only information and unavailable answers. The public development sources are PMC12844664, PMC11058859 and PMC11820775. Related fields from one source remain in the same development group.

`human_adjudication_template.csv` is blank for human judgments. It does not turn these labels into independent verification. The split manifest assigns every existing group to development and explicitly has no held-out group. Before a human evaluation, assign whole related-study groups to splits, review the source-first labels independently, record adjudication, and introduce a second topic before broad claims.

## Reviewed gates, fixed before B1 runs

- Every source hash and exact anchor must validate. Every delivered quotation must equal its canonical block slice; source and block identity must match.
- Both profiles use the same complete available canonical source, at most three references, 1,200 characters/400 declared budget tokens per reference and 3,600 characters/1,200 tokens per packet. The tokenizer is a Unicode word-or-nonspace-punctuation counter. It is a resource proxy, not a model-token claim.
- B1 with explicit components targets every required anchor/component in the mandatory answerable synthetic cases, including the late answer and table qualifiers. Report failures rather than changing the frozen anchors. Record B0's late-prefix miss. No invented quotation, changed canonical text, duplicate exact reference or overlap of at least half the shorter selected span may pass. Report smaller overlaps and their repeated characters.
- The primary comparison is B0 prefix versus B1 using only the identical full question. B1 with explicit component queries is a separate supplementary lane. Its extra-query gains must not be attributed solely to span selection.
- A named evaluator-only common transport cap applies after ranking to both profiles. Retain native B0 prefixes, native budget violations and whether the cap actually changed delivery. Do not silently truncate a baseline or omit an over-budget case.
- Public development results report matched anchor/component numerators and denominators by paper/field and grouped paper. B1 aggregate exact-anchor coverage should not regress against B0; report every per-case regression for review. This is a narrow development comparison, with no automatic product or clinical-quality claim.
- Report indexed/omitted blocks and characters separately from block/window matches. Missing indexing and missing retrieved evidence must remain explicit.
- For insufficient-context cases, report how often retrieval returns candidates. A nonempty candidate is not an unsupported generated claim. No generation occurs in this comparison.
- Report elapsed time, characters, declared budget tokens, overlap and duplicate references. Software tests and development scores do not establish researcher usefulness, semantic recall or superiority over another product.

The coordinating agent reviewed these gates and the frozen manifest before B1 runs. If development reveals a failure, preserve these cases and report it; do not replace the anchors or tune away every remaining development miss. Keep B1 optional until broader evaluation warrants changing the default.
