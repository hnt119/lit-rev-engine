# Portfolio MIT beta overlay — not a website deployment

Website base: `hnt119/hnt119.github.io`, clean `main` at
`3a03ea54b84d2658901522613641c054e5096637`.

This directory mirrors website-relative paths for a review-only update of the
existing literature-review project article and `LiteratureShowcase` component.
The actual website checkout and branch are not modified. No publication or
application hosting is performed. Apply only `src/` (and verified `public/`
downloads when supplied) to a separate portfolio feature worktree at that base.

The website's own `AGENTS.md`, installed Next.js 16.4.1 client-component/static
export guidance, existing component, navigation, layout and global CSS were
inspected. The overlay reuses the component name, global theme variables and
editorial layout. It adds no dependencies, routes, backend, storage, account,
network request, model invocation or shared framework. Normal citation/source
links navigate only when a visitor activates them.

## Public data and boundaries

`src/data/literature-showcase.json` is a bounded projection of three saved public
sources from `examples/mvp/offline_microbiome_30_v1` at engine commit
`9891ac352d39c66395e21af2e9732a76b076d002`:

- `PMC11058859`: Singapore pregnancy cohort.
- `PMC11820775`: Cheonggukjang trial.
- `PMC12567037`: Japanese women / body weight.

Each source is CC BY 4.0. The projection preserves citation, attribution, license,
upstream URL, pinned retained-XML URL, source and metadata hashes, parser identity,
and exact quote/context offsets. It deliberately omits author contact details,
full XML, images and all private research/workspace content. Nine selected
excerpts are curated display material, not new retrieval execution. Six example
comparison values are illustrative notes, and three reproductive-lifespan cells
are explicitly unresolved in their partial selected contexts. No human support,
independent verification or review inclusion is asserted.

This gut-microbiome example is a narrow illustration, not a representative
all-site review or the separate researcher pilot. The website is deliberately
read-only. The full Track A MIT local beta remains a separately installed
application: offline/manual work needs no inference, while new maps and supported
AI capabilities require explicit optional configuration and separately acquired
dependencies/models. Existing resource budgets and human-review rules remain.
Track B is not included in this download.

Offsets count Unicode code points in one existing normalized canonical block;
the component uses `Array.from` to avoid confusing them with UTF-16 indexes.
Source text is rendered through normal React text nodes, without raw HTML.

## Comparison → saved passages → source → return

Selecting a comparison cell opens the existing excerpt projection as **Saved
example retrieval**, scoped to that exact public paper and field. It displays
one curated saved result, the field subquestion and the paper scope. This is
not a newly executed retrieval or a ranked-recall benchmark. No query, model,
preparation, backend simulation or write is triggered by navigation.

`Inspect exact saved passage` focuses the same existing exact-source inspector.
Explicit return actions restore the saved-results heading or the original
comparison cell and its table position. Keyboard activation uses ordinary
buttons; browser Back/Forward and refresh restore this journey from validated
public paper/field identifiers in browser history. Only fixed section anchors
enter the URL, never questions, quotation text or notes. The demo does not use
local/session storage or private workspace state. Unrecognized history data is
ignored. Reproductive-lifespan cells keep their explicit partial-context warning
through the entire journey; opening a result never changes the illustrative note.

## Deterministic verification

From the engine checkout:

```sh
python3 showcase/portfolio/scripts/build_public_demo.py --check
```

This reparses only those three retained XML files with the existing parser,
checks manifest/source/metadata hashes and identifiers, requires one unambiguous
block per quotation, reconstructs exact offsets, enforces context/output bounds,
and compares the complete generated public projection. It uses no network,
models, database or private data. To intentionally regenerate after reviewing a
source change, omit `--check`; inspect the resulting diff.

The parent task separately validates a clean website export with the overlay,
TypeScript/static build and actual browser checks. Those results are distinct
from this source-anchor check and from human usefulness validation.

## Exact-commit release binding

The committed overlay contains an **unbound**
`src/data/local-preview-download.json` template. It displays the source/demo
without active download links, artifact hashes or an invented GitHub release
URL. Existing `public/downloads/` files in an older working tree are historical
local outputs; they are not source-commit inputs and must not be published as
the clean-commit candidate.

A source commit cannot contain its own final ZIP checksum while that ZIP's
metadata also names that same commit. The release flow therefore keeps the
committed source and generated distribution outputs separate:

1. Commit and review the unbound overlay and application source.
2. Build the purpose-built `0.3.0-beta.1` ZIP from a clean checkout of
   that exact commit. Its `RELEASE.json` must record the full source SHA and
   `source_state: "clean committed checkout"`.
3. Bind that ZIP, manifest and checksums into a **new directory outside every
   Git checkout**. The binder validates the exact source SHA/version, both
   checksums, every ZIP member/manifest hash, the source-snapshot digest, exact
   standard MIT license bytes and separate public-source notices. Known Track B
   pilot files are rejected.
4. Apply only the generated `src/` and `public/` to a separate temporary export
   feature worktree of the website base for validation. Do not apply them to the original portfolio
   or publish them without separate authorization.

```sh
python3 showcase/portfolio/scripts/bind_release.py \
  --archive /path/to/lit-rev-engine-0.3.0-beta.1.zip \
  --manifest /path/to/lit-rev-engine-0.3.0-beta.1.manifest.json \
  --checksums /path/to/lit-rev-engine-0.3.0-beta.1.SHA256SUMS \
  --source-commit "$SOURCE_SHA" \
  --output /absolute/new-overlay-output
```

`$SOURCE_SHA` is the actual full forty-character commit SHA, not a tag or a
placeholder to leave in metadata. The output parent must already exist; the
output directory must not exist. The binder refuses a working-tree archive,
wrong commit, mismatching manifest/checksums, symlink artifact or output inside
a Git checkout. It leaves the committed template, old working-tree artifacts
and actual website untouched. The generated `RELEASE_BINDING.json` is a local
preparation receipt, not publication approval or a publisher signature.

Only after verification does the generated overlay enable website-relative
links to the three actual release files it copied into `public/downloads/`.
The UI then displays the supplied ZIP hash and committed source SHA. No public
GitHub release URL is constructed. Two additional website-only text files are
derived from that verified ZIP: `NAME.INSTALL.md` is byte-identical to its README
and `NAME.LICENSE.txt` is byte-identical to its standard MIT license. Their
relative paths and SHA-256 values are recorded in generated metadata. Installation
and MIT actions therefore work before the new source commit is public.
View source opens the existing public repository; the exact beta source is in
the ZIP and its full SHA is shown unlinked, without a speculative commit URL.
The binder copies only explicitly listed public overlay files, the three
verified assets and those two derivatives; it does not copy arbitrary
files, research state, caches or old downloads from the source directory.

Offline binder checks:

```sh
python3 showcase/portfolio/scripts/test_bind_release.py -v
```

The UI labels the package **Local beta — setup required**, a source package
rather than a standalone app. It requires Python 3.12, Node.js 24, pnpm 10.20.0
and network access for dependency installation; runtimes and model weights are
not bundled. macOS arm64 was tested; Linux installation is unverified and
Windows is unsupported. Actual fresh installation and browser results belong
to the separate release evaluation. Model execution, scientific usefulness and
human review quality are not established by static export checks.

The owner has explicitly selected MIT for the original engine code. “Beta”
describes maturity and support, not an extra use/redistribution restriction.
Articles, datasets, model weights, dependencies and private user research retain
their own terms; MIT does not relicense them. The original source attribution
and CC BY notices remain in the demo projection. The binder rejects a missing,
modified or merely self-labelled MIT grant. The existing final publication
workflow still requires approval before release upload or portfolio publication.

This directory and its generated outputs remain a review preparation. Do not
publish, release-upload, deploy or modify the actual portfolio without the
user's separate authorization.
