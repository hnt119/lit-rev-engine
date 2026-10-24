# Local preview .2 — distribution terms and audit scope

This is a release-preparation record, not a new license grant. It records the
existing source/attribution situation for the source-only local preview and
prepared static portfolio overlay. No license has been selected for the owner.

## Unresolved project-code terms

**PUBLICATION BLOCKER: the engine's distribution/reuse terms remain unresolved.**
The repository's existing README explicitly says: “No license has been added
for the project code.” No `LICENSE`, `COPYING` or `NOTICE` file was found among
tracked files or matching paths in available Git history. There is therefore no
existing engine license file to copy into the download. Publisher article
licenses do not license this engine, launcher, comparison UI or portfolio code.

The owner must decide the terms under which the application source may be
distributed/reused before approving public pre-release publication. This record
does not choose MIT, another open-source license, an end-user agreement or an
all-rights-reserved policy. Technical packaging checks and permission to push
the reviewed source branch do not resolve this decision.

## Approved public research example

The retained `examples/mvp/offline_microbiome_30_v1/manifest.json` identifies
**30 sources, all CC BY 4.0**. A fresh local audit found a source URL, title,
author/copyright attribution, license URL, transformations and matching XML /
metadata SHA-256 values for every source. No missing attribution or mismatching
source-file hash was found. The source bundle's README lists all 30 citations
and license links; both that README and the complete manifest must remain in
the release.

XML bytes are retained unchanged, including their own permission notices.
No article image files or PDFs are bundled. The canonical parser normalizes
text for the application; displayed quotations, context selection and
highlighting are transformations, not a replacement of the original article.
The static overlay uses only its existing three-source projection, with nine
exact excerpts and attribution, license, original-source and retained-XML links.
Its illustrative comparison notes do not imply author endorsement.

CC BY 4.0 requires appropriate attribution, a license link and identification of
changes; the official deed also distinguishes the deed from its legal code.
Keep the retained notices and source-specific exceptions when redistributing
the example. See the [official CC BY 4.0 deed and legal-code link](https://creativecommons.org/licenses/by/4.0/).

The public source XML may contain the articles' published author contact details;
these are part of the attributed public articles, not the researcher's private
contact configuration, cookies or workspace state. No private research export
is approved by this public-example inventory.

## Saved map and optional models

The bundled map contains saved coordinates and title/abstract vectors for the
same approved 30-paper source capture. Its retained generation record identifies
`BAAI/bge-small-en-v1.5` at revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`. The
[model card at that exact revision](https://huggingface.co/BAAI/bge-small-en-v1.5/raw/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a/README.md)
declares MIT; it is not an engine-code license. Keep map/input provenance and
article attribution with those saved example artifacts.

No model weights, model runtime, model cache or paid provider access is included
in the ZIP. Optional future model installations retain their own model and
dependency terms and require a separate review if weights are ever distributed.
Opening the saved map does not download a model or create a new map.

## Dependencies and notices

The source archive includes version-pinned Python requirements and the existing
JavaScript package manifest/lockfile. It does **not** include `node_modules`, a
Python virtual environment, compiled frontend output, Python/Node/pnpm runtimes
or third-party package binaries/source trees. Setup obtains packages separately;
their package licenses and notices are not relicensed by this project.

As an inventory check, installed production package metadata from the earlier
fresh preview setup declared the following terms. These declarations are not a
legal compatibility opinion, a full software bill of materials or a substitute
for each package's own notices:

| Installed package | Version | Declared license |
| --- | --- | --- |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| certifi | 2026.10.18 | MPL-2.0 |
| click | 8.5.0 | BSD-3-Clause |
| fastapi | 0.153.0 | MIT |
| h11 | 0.16.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| pydantic | 2.13.4 | MIT |
| pydantic_core | 2.46.4 | MIT |
| starlette | 1.3.1 | BSD-3-Clause |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| uvicorn | 0.54.0 | BSD-3-Clause |
| next | 16.4.2 | MIT |
| react | 19.3.1 | MIT |
| react-dom | 19.3.1 | MIT |

The installed Next/React packages retained their own license files. Runtime,
model, dependency or prebuilt-frontend redistribution would change this scope
and require a new complete notice/license audit. No dependency upgrades were
made for this release freeze.

## Privacy and scope checks

The pre-staging scoped application, launcher, tests, documentation and overlay
text scan found no private-key block, credential-shaped token or absolute
personal Desktop/Documents/Codex/SSH path. Manual review additionally identified
a person-specific escaped contact pattern in the archive-audit test. It was
removed, and a separate source recheck confirmed its absence before staging.
The final index audit must independently check the actual staged bytes.
Synthetic test secrets and tests of environment stripping remain tests;
they are not active credentials. The original README/.gitignore unrelated
changes, research databases, Render drafts, local browser state and other
unrelated untracked files were outside the intended commit set.

This pre-staging scan is distinct from the final staged-file and clean-commit
archive audits. The release coordinator must record those final results for the
actual committed source revision and rebuilt asset; an earlier working-tree
archive and its old hash are historical evidence, not a publishable candidate.
Do not include earlier ZIPs, private QA cookies/logs, caches, backups, model
weights or generated runtime state in the commit or GitHub release uploads.
