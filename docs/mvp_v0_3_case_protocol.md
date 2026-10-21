# Real-case readiness for MVP v0.3

This path audits one named saved v0.2 workspace, search, source preparation and
optional map. It reuses the existing services and storage. It neither searches
PubMed nor fetches sources nor loads an embedding model. The existing one-paper
saved example remains unchanged. Synthetic software fixtures remain software
fixtures; they do not satisfy the real multi-paper gate.

## Prepare the exact case

Copy [the proposed protocol](../examples/mvp/research_case_protocol.example.json)
to a private directory. It contains an editable generic starting query and no
known-paper relevance judgments. It is separate from the user's privately
supplied workbook and any dated real-case protocol extracted from it.

The supplied search-strategy workbook was inspected read-only for this cycle.
Its broader union is the primary systematic-review search plan; its Asia-focused
subset is a useful narrower exploratory coverage check. Its diet-focused search
is another planned comparator. Preserve exact executed syntax and the relation
between these variants in the private protocol. Do not claim that a capped
Asia-focused preview implements the broader systematic search. The workbook's
provisional pilot reports are not an independently approved held-out relevance
set. No workbook paper content is copied into the checked-in generic example.

Have the researcher approve the exact executed syntax, question, sort, date
restriction and cap. Record approval evidence and the SHA-256 of the exact query
UTF-8 bytes; changing whitespace or syntax invalidates that approval. The
`check` manifest reports the digest without making a request. Approval is a
record of a human decision, not an automated certification.

The default exploratory cap is 30 and maximum 50. A preview is separate from
complete PubMed capture and formal inclusion. Use the existing Discover page
and its single API process for the explicitly approved search. Do not start a
second live provider process to prepare a demonstration. Configure the actual
server `NCBI_EMAIL` outside source control first. The audit reports only its
presence and format, never its value or API key.

Inspect actual results before selecting five to ten report IDs. Put their exact
ordered IDs in `selected_paper_ids`, then prepare those reports through the
existing page. Do not replace failed, abstract-only or unavailable reports to
make the demonstration appear complete. If the query returns fewer than 20
metadata records, record the actual count. Query broadening needs a new explicit
decision and a separate search record.

Record the actual capture request/response, runtime and failures privately.
`SearchPreview` preserves query, translation, search time, provider counts and
metadata but does not persist the original request cap independently. Therefore
the audit labels that cap as **from protocol**, enforces the observed counts,
and does not claim to recover an absent original request. An audit of a saved
live capture is not a new live execution.

## Run the read-only audit

Use the configured web Python environment; this checkout uses `.venv-map`.
The paths below are private examples;
choose a fresh output directory for each execution.

```sh
.venv-map/bin/python scripts/mvp_research_case.py check \
  --protocol /private/tmp/my-case/protocol.json \
  --output /private/tmp/my-case/readiness-01

.venv-map/bin/python scripts/mvp_research_case.py audit \
  --protocol /private/tmp/my-case/protocol.json \
  --data-dir /absolute/path/to/.mvp-web-state \
  --workspace-id WORKSPACE_ID --search-id SEARCH_ID \
  --preparation-id PREPARATION_ID --map-id MAP_ID \
  --output /private/tmp/my-case/audit-01
```

Leave out `--preparation-id` before preparation and `--map-id` before mapping;
the manifest retains `NOT_PREPARED`/`MODEL_NOT_RUN`. Auditing an explicitly named
workspace requires local filesystem access to its private registry. No
capability is printed, placed in the protocol or included in the manifest.
Missing IDs never cause a replacement workspace or example to be manufactured.
Configuration presence flags describe the audit process environment, not the
configuration of a server that previously captured the case. The CLI does not
automatically source `.env` or claim an absent audit variable means an earlier
live capture lacked its contact. Load the trusted local configuration explicitly
when needed, as described in [the checkpoint guide](mvp_v0_3.md).

The manifest records original query/question, query translation, dates, sort,
search timestamp, provider-reported/fetched/distinct counts, selected outcomes,
source versions/hashes, block counts, failures, map/profile/input/coordinate
manifests, and two identical map loads. It checks retained hashes and stable
identity. These checks do not establish entailment, population suitability or
scientific usefulness. Per-source URLs/licenses are private provenance; a
recorded license is not a completed redistribution review.

The optional existing local map workflow is an explicit separate action. Its
real-model receipt must record runtime, model files/profile, token coverage and
failures. Reopening the saved map through this audit never refits positions or
calls the model. A profile written in a map is provenance, not independent proof
that real weights executed. The audit therefore reports model execution in this
command as `MODEL_NOT_RUN` even when it validates a persisted map.

## Discovery evaluation

The audit includes the existing transparent suggestion and the approved exact
query side by side without executing another query. Supply researcher-written
concept groups explicitly; no synonyms, MeSH terms or relaxation are invented.
Assess whether the current generic first-twelve-terms AND strategy overconstrains
the actual question before changing query construction.

Known-paper recovery counts only unique `held_out` IDs marked
`reviewer_approved` with an applicability rationale. Candidates are not scored.
With no approved held-out set the denominator is zero and fraction null, not a
successful recall score. Recovery concerns membership in this capped preview,
not recall of all relevant literature. Keep the held-out set fixed before
comparing separately approved queries, and label any tuning/development set.

## Honest evidence and rights boundaries

The manifest separates software integrity, saved provider capture, current
provider execution, persisted model artifact, current real-model execution,
human semantic assessment and human usefulness. `LIVE_NOT_RUN`,
`MODEL_NOT_RUN`, `NOT_ASSESSED` and `NOT_RUN` remain valid outcomes.

Output is a fresh directory with mode 0700 and a manifest with mode 0600. It
omits full abstracts, quotations, source text, credentials and hidden reasoning.
It is still private research content, including the query and identifiers.
There is no public-export mode. Publication requires a field-by-field rights
and privacy review and separate authorization.

NCBI states that publishers or authors may claim copyright in PubMed abstracts;
free access to PMC also does not itself confer redistribution rights. See the
[NCBI policies](https://www.ncbi.nlm.nih.gov/home/about/policies/) and
[PMC copyright notice](https://pmc.ncbi.nlm.nih.gov/about/copyright/).

## Current limits

This audit supplies repeatable readiness and integrity evidence. It does not
perform capture, prove that a model executed, generate human review judgments,
or make a multi-paper software test a real research case. The C0 real-case gate
requires separately recorded approved live capture, actual selected source
outcomes, explicit local model execution and browser reopening. A missing
prerequisite stays visible; no live or model call occurs merely on opening the
case or changing views.
