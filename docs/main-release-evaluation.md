# Main-branch documentation release audit

Checked **3 October 2026, Asia/Singapore**. GitHub's default branch is `main`. Its fetched tip was `882114ee1d8d3afd9cb310448ad1ff00dfda0ee0`, eleven commits behind the accepted engine release `69e7a6b7093a5a1067aaf7a806caa4d5d9ae7bce`, with no divergent commits. GitHub reported `main` unprotected and the authenticated account authorized to push. The user requested a normal fast-forward publication to `main`; the feature branch is retained.

This update adds an entry-point guide, repository map, saved human-pilot contract and cloud-model research plan. It changes no operational code, dependency, test, source fixture, frozen ranking result or model default. The accepted engine's previous clean-checkout gate remains **1,240 tests and 31 subtests**, plus seven source/gold checkers; the full suite was not rerun for these documentation changes.

Implementation executed all seven literal shell blocks in [Getting started](getting-started.md), using Python 3.12 with site packages disabled and an isolated temporary database. The coordinator independently executed those same blocks and reviewed the exported artifacts: six occurrences, two duplicates, four records, one included report, one reasoned title/abstract exclusion, two pending records, and nine byte-identical files across two unchanged-ledger exports. Protected source/example bytes remained unchanged. The final staging check also executed all seven blocks from the staged checkout, resolved 64 local documentation links and confirmed that all checkout files remained byte-identical.

The evaluation agent could not start this cycle because its thread limit was reached. The coordinator performed the additional review; this audit does not attribute those checks to an evaluation agent.

Model research uses linked primary cards and serving documentation in [Model strategy](model-strategy.md). No model was downloaded, deployed or evaluated here. The cloud pair is a comparison candidate, not a demonstrated improvement. The [human review pilot](pilot-milestone.md) remains planned and requires the team's actual protocol inputs.

Only reviewed documentation enters this commit. The existing local retrieval experiments and ignore-file change are excluded. Publication uses a non-force fast-forward, followed by remote-tip verification.
