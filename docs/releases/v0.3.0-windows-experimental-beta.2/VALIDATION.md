# Windows experimental release — actual validation

**Windows 11 x64 · Experimental · Unsigned · Not tested on Windows.**

Exact clean source: `664b86d4ed510c3d16982b5813b27e6bd1150129`. Version `0.3.0-windows-experimental-beta.2` / build3003. Build and validation host: macOS Apple Silicon; target runtime was never executed. No Windows VM, GUI automation, native installation or OS security bypass was used.

| Fresh observed check | Result / limit |
| --- | --- |
| Clean source snapshot and production frontend | PASS; existing archive auditor and actual standalone Next production/type build; no engine redesign |
| Windows assembly + NSIS3.13 compile | PASS on Mac, using pinned Electron45/Python3.12.15+20261021 target runtimes; not Windows execution |
| Exact committed-source host batch | **187 Python tests passed;23 Node tests passed;0 failures/skips**. Packaging/security mocks/fixtures and active/historical inert NSIS preprocessing/compilation |
| Host archive test/list/safe extraction | PASS; exact7451-file installed manifest match, plus manifest itself |
| Complete retained PE import audit | PASS;112PE files,0unresolved declared imports. 626WindowsOS/API-set edges and exported symbols are runtime-unverified |
| Target dependency metadata | PASS;17WindowsCPython3.12AMD64 distributions; no guarantee about arbitrary dynamic loading |
| Exact-source/terms binding | PASS;4newrootresources, complete SDK/Python bytes, approved sourceinput/route hashes, same displayed/retained text, build3003 and sourceSHA |
| Core pywin32 subset | PASS;136original optional omissions remain recorded. All4,345 retained Python files compared to8566 baseline are unchanged |
| Notice/SBOM collection | 160metadata components;112header-identified native files;0missing-notice items;431notice-archive files. Inventory is not legal certification or complete static-link analysis |
| Microsoft and FFmpeg bindings |5exactDLL+2existing-license bindings PASS;both unchanged exact FFmpeg source companions hashes verified; upstream binary reproduction NOT_RUN |
| Signing | Unsigned; no embedded Authenticode certificate table. Windows trust/security behavior NOT_RUN |

The active NSIS source rejects silent mode in .onInit, resets an unchecked agreement page, validates actual checkbox state before setting its local flag, and guards the first Application instruction before installation writes. Both the exact final input preprocessing and inert host compile were checked. This is not a record that a Windows user actually accepted, declined or installed anything. All Windows installation/execution/GUI/security/download-origin, Start launch, Core workflow, native exports, restart/reinstall/uninstall/data-preservation checks remain **NOT_RUN**, explicitly waived for this experimental channel by owner direction.

No real neural models, live PubMed, cloud generation, paid usage, scientific accuracy or independent human usefulness evaluation ran. Existing semantic/retrieval profiles and original research state were preserved. The earlier6381privateinstaller lacks this agreement and is not substituted for this artifact.

## License route and evidence scope

The owner explicitly authorized the documented conditional Electron→SDK D3DCompiler and Python→CRT downstream routes in issue18. The current package includes operative Microsoft-only protections and complete retained texts, exact pins and a route record. No personal SDK/VisualStudio license acquisition or private upstream contract assent is asserted. Generic Runtime/BuildTools end-user EULAs are not used as publisher redistribution grants. MIT/Python/FFmpeg rights remain separate.

The15-file vendor provenance directory is preserved byte-for-byte, including its historical remaining-owner-actions text. The current source-bound MICROSOFT_COMPONENT_LICENSE_ROUTE.json records the subsequent owner authorization and active mechanism; it does not rewrite the older integrity evidence. Generic SBOM source/signing/acceptance prompts remain disclosed limitations, not claims that those checks passed. This is an owner-authorized experimental channel, not a stable Windows qualification or legal certificate.

Raw exact commands/logs and full independent operator receipts stay private. Public HOST_STATIC_AUDIT.json, INDEPENDENT_STATIC_SUMMARY.json and source tag support these bounded observations. Source/host checks are separate from any future installed-Windows or scientific evaluation.
