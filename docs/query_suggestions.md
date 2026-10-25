# PubMed keyword proposals

Use **Live PubMed** for a live exploratory search. A **saved example** reopens a
recorded capture. Query proposals are local and never run a search or call a
model. The existing provider sends the exact editable query in a form POST body;
long Boolean strategies remain supported up to 20,000 characters.

## Generate and use a new proposal

1. Enter a natural-language **Research question**.
2. Select **Propose editable query**. Inspect the retained concepts and grouping.
3. Select **Use proposed query** to replace the editable **PubMed query**.
4. Review or edit it, then explicitly select **Search PubMed preview**.
5. Open **Exact search provenance** to inspect PubMed's translation and warnings.

Existing drafts and historical captures are preserved. Updating the application
cannot repair an old query already in a saved draft: propose and explicitly apply
again. Dismissing a proposal leaves the current query intact. Editing either
input invalidates pending proposals, including responses arriving after an edit
and revert. Applying a proposal does not search or change the research question.

## Natural language becomes compact concepts

The prior fallback sent question framing to PubMed as search terms. Four saved
searches of the default source question returned zero; their translations
required words such as `source`, `report`, and `studied`. The prior specialist
template had a different defect: it dropped named outcomes and exposures while
expanding Asia into a long country list. Both behaviors are superseded.

The replacement uses deterministic phrase matching and a conservative residual
keyword path. Longer recognized phrases protect meaningful boundaries; unknown
terms such as `bruxism` remain available. It removes question framing, preserves
explicit concepts, and deduplicates repeated terms without an arbitrary word cap.
It adds no synonyms, countries, MeSH assignments, or model-generated text.

Distinct concept groups use `AND`; nearby coordinated alternatives use `OR`.
For known roles, lists of outcomes, exposures, populations, geographies, or topics
are treated as alternatives. A lower-case `or` can connect unfamiliar concepts.
The explanation exposes this grouping for review. This is an editable heuristic,
not a semantic understanding of every question.

Multiword concepts are parenthesized, unquoted and untagged, allowing PubMed's
automatic term mapping. Parentheses group concepts; they do not enforce an exact
phrase. NLM recommends identifying key concepts and keeping basic search syntax
simple; full systematic searches need additional work for indexed and non-indexed
records. See the [PubMed User Guide](https://pubmed.ncbi.nlm.nih.gov/help/#how-do-i-search-pubmed)
and [NLM's keyword-search guidance](https://www.nlm.nih.gov/oet/ed/pubmed/mesh/mod02/04-000.html).

For the previously failing example:

> What does this source report about diet, gut microbiota, and gestational
> diabetes among the studied Chinese pregnant women?

```text
diet AND (gut microbiota) AND (gestational diabetes) AND Chinese AND (pregnant women)
```

For the current broad research question, the proposal retains all named
outcomes and exposures:

```text
(gut microbiome)
AND ((reproductive longevity) OR (healthy aging) OR (gynecological disease))
AND women
AND Asia
AND (diet OR exposome)
```

The trailing note “Southeast Asian studies are preferred” appears in the
explanation for human screening; it does not become an additional mandatory
restriction. An explicit required population such as “Southeast Asian women”
stays in the query. Geographic words do not establish participants' origins.

An unfamiliar question also gets keyword extraction:

```text
Can exercise improve sleep after surgery?
→ exercise AND sleep AND surgery
```

## Preserved strategies and explicit limits

- Inputs with PubMed field tags or uppercase Boolean syntax are preserved
  byte-for-byte, including whitespace. Preservation does not validate syntax.
- English framing rules and a small phrase vocabulary can misread unfamiliar
  wording. Inspect every proposed group. Lists joined by natural-language
  “and” can become alternatives; edit the query when co-occurrence is intended.
- Natural-language exclusions and comparison direction are not encoded. The
  explanation flags these limitations; use a reviewer-authored strategy when
  these semantics matter. “Whether or not” alone is not an exclusion.
- Recognized trailing preference clauses are shown separately in the explanation.
  Ambiguous or embedded preferences still need manual review.
- Filler-only input returns no query and disables **Use proposed query**.
  If expansion would exceed the 20,000-character limit, the whole proposal is
  refused with an explanation; terms are not silently truncated.
- Every `AND` group is mandatory. A question with many outcome/exposure groups
  can be restrictive even when it parses correctly. Broaden deliberately or
  split it into protocol-defined searches; do not silently drop concepts.

For a systematic review, retain the reviewer-approved comprehensive strategy,
search dates, filters and provider receipts. The short proposal is an exploratory
starting point. Search results, map points and source selection are not formal
inclusion decisions. Parsing, result counts, relevance and recall are separate.

## Validation — 2026-10-21

Changed files for this correction only (earlier uncommitted MVP work is separate):

| File | Change |
| --- | --- |
| `src/mvp/query_suggestions.py` | Local phrase/keyword extraction, alternatives, preferences and explicit limits. |
| `tests/mvp/test_query_suggestions.py` | 46 parser/service regressions, including original failing input. |
| `tests/mvp/test_query_suggestions_independent.py` | 22 independent acceptance probes. |
| `apps/web/components/discover.tsx` | Empty proposal cannot be applied; usage hint explains keyword generation. |
| `apps/web/tests/query-suggestions.test.tsx` | Sixth component test protects the retained query on empty proposals. |
| `tests/web_api/test_query_suggestions.py` | Three real-adapter offline API tests; no provider calls or research/draft mutation. |
| `docs/query_suggestions.md` | Current usage, boundaries and verification evidence. |

Executed from the repository root unless indicated:

```sh
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q -rs
# 227 passed in 8.79s; zero skipped. Includes 68 query tests and Streamlit checks.

.venv-map/bin/python -m pytest tests/web_api -q -rs
# 47 passed in 17.13s; zero skipped; two existing dependency deprecation warnings.

# From apps/web:
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --import tsx --test tests/*.test.ts tests/*.test.tsx
# 33 passed in 621.87ms; zero skipped; React test-renderer deprecation notices.

NEXT_TELEMETRY_DISABLED=1 /Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/next/dist/bin/next build
# Production build, TypeScript and page generation passed.

git diff --check
# Passed.
```

Independent evaluation caught and prompted fixes for possessive `women’s`/`women's`
creating a stray `s`, “best promotes” becoming mandatory, preference clauses
narrowing geography, and mixed “whether or not … without …” losing its negation
caveat. Earlier obsolete template tests were replaced; no tests were skipped.

### Actual browser checks

A separate **UI CHECK ONLY** local live-mode workspace confirmed:

- Preview displays compact keywords and explanation without replacing the current
  query; applying explicitly copies the exact proposal.
- The applied query survives navigation, reopening and the application restart.
- Filler-only input leaves the existing query intact and disables apply.
- The broad question retains reproductive/aging/gynecological outcomes and
  diet/exposome alternatives; its regional preference remains an explanation.
- At 390 × 844, keyboard Enter applies the proposal and the page has no horizontal
  overflow (body/document width both 390px). Temporary viewport overrides reset.

Browser checks created zero saved searches, source preparations or evidence runs.
They did not change an existing research workspace. Screenshots and a diagnostic
receipt stay ignored under `.mvp-web-state/ui-checks/query-keywords-2026-10-21/`.

### Live PubMed diagnostics

Two bounded ESearch requests executed at **2026-10-21 03:21:33 UTC**, with the
configured NCBI contact. Each requested at most 30 identifiers, with no citation
or full-text fetch. Exact proposal hashes, provider translations, ordered IDs and
warnings are retained in the ignored `pubmed-diagnostics.json` receipt. They are
diagnostics, not new formal review captures.

| Exact generated query | Provider-reported matches | Provider warnings |
| --- | ---: | --- |
| Previously failing default source question, as shown above | 3 | None |
| Broad original research question, as shown above | 1 | None |

The known example PMID `42051515` was among the first query's three identifiers.
The second query remains restrictive despite clean parsing. These checks establish
live provider interpretation and a known-item match, not systematic sensitivity
or scientific eligibility. Future counts can change. No relevance ratings were
performed.

### Preserved boundaries and startup

The query contract, providers, SQLite schema, source provenance, assessments,
exports, passage retrieval, frozen model profiles, and saved map behavior were
not changed. No dependency installation, embedding inference, paid call, migration,
commit, push, merge or deployment was performed. Embedding checks: **NOT_RUN** for
this correction. Scientific relevance/recall: **NOT_ASSESSED**.

Final preservation check: 683 unrelated file hashes were unchanged, staging was
empty, `HEAD` remained `404b002`, and local `main` remained `a506ae0`. Current
branch: `codex/mvp-v0-3`.

The existing loopback app was restarted with the corrected code at
`http://127.0.0.1:3000/`. Startup remains the procedure in
[the v0.3 checkpoint guide](mvp_v0_3.md). For a manual local start, use the existing
API environment, configured `NCBI_EMAIL` (and optional `NCBI_API_KEY`) and
`scripts/run_web.py --production --node /path/to/node --data-dir .mvp-web-state`;
that runner does not automatically load `.env`. Keep private state local.
