# Frozen component development upload

`kaggle-upload.zip` is a byte-exact copy of the prepared development upload.
It contains exactly four files: `job.json`, `component_core.py`,
`qwen_kaggle_environment.py`, and `qwen_components_kaggle_runner.py`.
`manifest.json` records each member's exact SHA-256 and byte count.

This bundle contains public licensed research passages, original requests and
components, and synthetic review-project identifiers. Source licensing and
attribution are retained in the
[development source archive](../qwen_components_development_sources/README.md).
It contains no gold answers, review database, credentials, browser/account data
or inference results. **At preservation, no inference or result existed for this
frozen job.** Subsequent execution belongs in the separate
[run record](../../../docs/qwen-components-runs-v1.md).

Trusted bindings:

- ZIP: `c5ad1ea40db7528ffcdf4b1c98fe936bcac8bbfb9a3a3df51bd64f6e27477a81`, **80,534 bytes**.
- Job payload: `4de843130af3727968e1a0f7bfd150c5743fcfb521d820a5c0fe0fd9c3bc3ce2`.
- [Development freeze](../../../docs/qwen-components-development-freeze-v1.json): `a70cfd4a4a1526e2e8da72f1b34ef1586ce6be430e9474892cf76a9b45d5ade0`.

After publication, this exact ZIP can be supplied by HTTPS URL to a **private**
Kaggle dataset. Retain the trusted job checksum locally and verify all three
executable bindings before loading them, as specified in the
[component guide](../../../docs/qwen-components-guide.md). Packaging changes
neither the frozen job nor its selected method, acceptance gates or evidence.
