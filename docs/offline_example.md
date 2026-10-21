# Thirty-paper offline example

The current checkout bundles 30 distinct real Europe PMC papers, their verified
CC BY 4.0 full-text XML, citation metadata, and a precomputed semantic map.
Opening the collection requires no NCBI contact, API key, optional model setup,
network request, embedding calculation or projection. This extends the existing
MVP services and SQLite/map contracts; it does not introduce another engine.

## Open it

Start the existing local React/FastAPI application using
[the local startup instructions](mvp_v0_2.md#start-and-stop). Mapping requirements
and `MVP_MAP_ENABLED=1` are **not needed** for this bundled example. At
`http://127.0.0.1:3000/`:

1. Choose **Saved example · offline** and create a workspace, or reopen an
   existing saved-example workspace.
2. Click **Open saved example**. It adds the current 30-paper capture and its
   saved map. The map appears beside the paper selection list automatically.
3. Hover/focus points, click a point to reveal its paper, filter, or select up to
   ten papers for source preparation. Selection does not refit the map.
4. Continue through source preparation, exact passage inspection, human judgments
   and CSV/JSON exports as before. Selecting a paper is not formal inclusion.

An earlier one-paper capture remains one paper in history. The upgrade message
and **Open saved example** button add a new capture; they do not rewrite that
record or its assessments. Old query/date/cap draft fields cannot accidentally
limit the current offline bundle to one paper. Bundle identity participates in
the submission retry fingerprint, so an older successful request cannot replay
the wrong bundle.

Streamlit uses the same 30-paper source provider. Semantic map display belongs
to the React workspace; Streamlit's existing evidence workflow remains available.
Optional local model setup is still needed to compute new maps for other saved
searches or explicitly rebuild a map.

## What is bundled

The independent public capture reported **194 matches**, returned **100 CORE
metadata records**, and retained the first **30** distinct permitted articles
through rank 43. Thirteen candidates were excluded: nine unsupported metadata
licenses, three unresolved XML permissions and one bounded timeout. The remaining
57 were not evaluated after the target was reached. These are curation counts,
not screening decisions. Excluded abstracts/full texts are not redistributed.

The query combines gut microbiome/microbiota, women/female and Asian geographic
keywords. Such words do not establish ancestry, women-only cohorts, human studies
or eligibility for this review. The collection includes different study types
and is an exploratory demonstration, not 30 formally included studies, a complete
systematic search, a relevance benchmark or evidence for a scientific conclusion.

The [public pack](../examples/mvp/offline_microbiome_30_v1/README.md) provides every
article's attribution and original-source link. Its manifest records actual
query/time, candidate audit, own article identifiers, permitted license and file
hashes. Original XML is unchanged. The historical one-paper pack remains
unchanged at `tests/fixtures/mvp/`.

The map was generated once with **BAAI/bge-small-en-v1.5**, revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`: 30 real 384-dimensional vectors,
15,808 input tokens and 45 windows. All tokens were covered; 15 papers needed
multiple windows. Existing UMAP cosine projection produced 30 stored points.
Python socket connections were denied during generation, with zero connection
attempts recorded and zero paid inference calls. The recorded 18.35 seconds cover
profile hashing, model loading, embedding, projection and validation together.

The [generation receipt](../examples/mvp/offline_microbiome_30_v1/map-generation.json)
and map manifest retain model/file/runtime hashes and generation time. Each
explicit offline capture receives new workspace/search/map bindings to those
same vectors and coordinates. No fictitious completed inference job is created.
Coordinate SHA-256:
`f33bee282b88782074f71c15ce5156dbce3a6ae55a26a7cdbc904642e463f934`.

## Maintenance and validation

Only these explicit maintenance commands capture public sources or run a model:

```sh
# Capture into a NEW directory; uses bounded live Europe PMC requests.
.venv-map/bin/python scripts/capture_offline_example.py --output /absolute/path/to/a/new-versioned-pack

# Compute once using the already-cached pinned model; no downloads or network.
.venv-map/bin/python scripts/build_saved_example_map.py --pack /absolute/path/to/a/new-versioned-pack --allow-local-model
```

Existing directories/map files are not overwritten. A future release should use
a new bundle identifier and a reviewed capture/import update. Application startup,
ordinary tests and opening the example never invoke these commands. A malformed
or modified source/map bundle fails closed; it is not replaced with invented
records or positions.

Acceptance includes 30 unique real identities, raw/canonical source hashes,
licenses, token/vector/map bindings, invalid bundle rejection, restart/retry
idempotence, session isolation, deletion cleanup and the existing evidence flow.
A fresh-process test blocks all optional model/numerical imports and network
connections while opening and inspecting the bundled map. Frontend regression
checks an old one-paper draft opening all 30 records with map readiness false.
Scientific relevance, recall and human usefulness remain **NOT_ASSESSED**.

### Executed checks, 2026-10-21

```sh
# Repository root, Streamlit-compatible environment:
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q -rs
# 182 passed in 10.31s; zero skips.

# Repository root, existing API/map environment:
.venv-map/bin/python -m pytest tests/mapping tests/web_api -q -rs
# 127 passed in 35.74s; zero skips; two existing dependency deprecations.

# apps/web:
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --import tsx --test tests/*.test.ts tests/*.test.tsx
# 32 passed in 655.61ms; zero skips; React test-renderer deprecation notices.

NEXT_TELEMETRY_DISABLED=1 /Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/next/dist/bin/next build
# Production build, TypeScript and page generation passed.

# Repository root:
git diff --check
# Passed.
```

Independent evaluation added 26 source/API cases included in those Python totals.
Intermediate runs exposed two single-paper assumptions: the API test helper
selected every returned paper, and a history assertion assumed the first passage
belonged to the first source. The helper now selects at most ten, and the assertion
binds to the actual passage's paper identifier. A frontend compatibility guard
also handles optional provenance metadata in older partial test fixtures. Final
checks above pass; intermediate failures are not reported as passes.

The actual browser upgraded an existing one-paper offline workspace to a new
30-paper capture. The earlier search, question, preparations, runs and assessments
were hash-checked unchanged. Opening again and reloading retained exactly one
new capture and one 30-point map, with **zero model jobs**. Check/uncheck updates,
filtering to four points and restoring all 30 preserved coordinates. Desktop and
mobile views, paper focus, and Map/Papers navigation were checked. Screenshots and
private receipts are under `.mvp-web-state/ui-checks/offline-example-30-2026-10-21/`.
Temporary viewport overrides were reset.

Evidence categories: the one-time pack capture was a **real live Europe PMC**
acquisition; the map generation was a **real pinned local CPU model run** with
network connections denied. Ordinary opening/reopening was **offline replay**.
There was **no new live PubMed execution** and **no paid inference**. No commit,
push, merge or deployment was performed for this change.

### Changed files

| Path | Change |
| --- | --- |
| `examples/mvp/offline_microbiome_30_v1/` | Versioned public source/attribution pack and checked real-model map bundle |
| `src/mvp/adapters/saved_examples.py` | New default, strict source/count/identity integrity, public bundle metadata |
| `src/mvp/adapters/saved_example_map.py` | Checked seed loading and workspace/search rebinding without inference |
| `src/mvp/adapters/map_storage.py` | Atomic idempotent import using existing vector/cache/map tables and quotas |
| `src/mvp/map_jobs.py` | Lifecycle-guarded saved-map installation without fictitious jobs |
| `src/web_api/app.py` | Install the bundle after an explicit matching offline search POST |
| `apps/web/components/discover.tsx` | Current-bundle upgrade, fixed 30-record opening, retry fingerprint and history notice |
| `apps/web/components/map-explorer.tsx` | Separate saved-map inspection from optional new-map computation |
| `scripts/capture_offline_example.py` | Explicit bounded public capture maintenance command |
| `scripts/build_saved_example_map.py` | Explicit pinned, network-denied public map generation maintenance command |
| `tests/mvp/test_offline_example_30.py` | Independent real source/provenance/rights and corruption checks |
| `tests/web_api/test_offline_example_map.py` | No-model/no-network, lifecycle, scoping, tamper and evidence-flow checks |
| `apps/web/tests/offline-example.test.tsx` | Historical draft upgrade and saved-map display without local inference |
| `tests/mvp/test_providers.py` | Keep exact original one-paper assertions on its explicit historical fixture |
| `tests/web_api/test_api.py` | Multi-paper source selection and source-bound history assertions |
| `README.md`, `docs/offline_example.md` | Current usage, architecture and executed evidence |

Historical fixtures, frozen Qwen/ledger/retrieval profiles, unrelated local changes,
private data and `main` remain preserved. No changes to evidence contracts,
assessment rules, source provenance or original export schemas were required.
