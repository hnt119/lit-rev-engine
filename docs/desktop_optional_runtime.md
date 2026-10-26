# Optional retrieval runtime for the desktop candidate

Core works without neural libraries or model downloads. Qwen and MedCPT remain optional, experimental choices in the same application. Installing libraries does not install model weights, run a model, declare the selected profile ready, or establish scientific quality.

The private macOS Apple Silicon candidate includes a pinned optional-runtime catalog and an application-menu installation action. Obtain the exact reviewed runtime ZIP separately, choose **Install optional research libraries…** in the application menu, then save work, quit and reopen the application to activate it. The installer checks the catalog, archive, manifest and every extracted file before execution. It then imports the pinned libraries and performs a small CPU tensor check. It never runs pip, fetches a URL, or reads a provider key. The application uses its bundled core Python for installation; no developer Python, Node or Terminal is required.

The optional interpreter and libraries are installed under the dedicated desktop data directory, in `optional-runtimes/<runtime-id>`, outside the immutable application. Model weights use the existing explicit pack-install workflow and private model cache. Open Settings, explicitly install the selected pack, run its runtime check, and build an index for the intended preparation. Missing or invalid libraries, models or indexes remain visible; a failed selected neural profile never silently becomes Core lexical retrieval. Windows optional libraries are unavailable until a Windows x64 capsule has been built and checked on Windows.

## Current private macOS capsule

| Binding | Value |
|---|---|
| Runtime ID | `retrieval-python312-macos-arm64-v2` |
| Filename | `litrev-retrieval-runtime-darwin-arm64-v2.zip` |
| ZIP bytes | `171140185` |
| ZIP SHA-256 | `736b32b692236427081481793e67556220fb1a8f1b9871addab282a9c4611bb1` |
| Manifest SHA-256 | `3ba435a6926f42e9bd3bc2917ab7fda16f260951e49ceb93570ea7eec502635d` |
| Interpreter | `python/bin/python3.12` |
| Unpacked inventory | 21,947 files; 627,060,546 bytes |
| Model weights | None bundled |

This is a private candidate, not a published download. The catalog is an executable-code allowlist; a filename or user-selected archive alone grants no trust. The capsule binds exact SHA-256 values of the builder, installer helper, SBOM collector, runtime lock and existing pinned requirements. It contains no engine code and does not claim an uncommitted source tree is a clean release commit. A future change to those recipe inputs requires a new reviewed binding; do not overwrite an already distributed capsule.

At build time, prepare a fresh complete target Python prefix from the verified runtime-lock archive, install only the existing frozen Core and retrieval requirements, retain matching runtime/Python/native notices, then invoke `scripts/build_desktop_optional_runtime.py`. The builder does not download dependencies. It inventories only installed distribution metadata for version checks; vendored metadata remains retained in the file inventory and SBOM. Run target builds on the actual target OS. The current builder rejects a Windows capsule built on macOS.

## Validation scope

The installer safety tests use synthetic non-executable fixtures and mocked native checks. Separate actual macOS checks installed the real capsule in fresh temporary data, imported Torch/Transformers and exercised cached pinned models on CPU. Model runtime checks execute encoders and rerankers on disclosed integration text. A source-linked query/index check uses one approved public abstract with exact ranges; this is an integration check, not a retrieval-quality benchmark or whole-paper review. Model files and original research data are not modified. Final packaged-app installation and OS trust checks are recorded separately in the desktop evaluation.

## Recovery and limitations

Save drafts before a runtime change. A service restart ends the current in-memory provider-credential session; re-enter any session-scoped credentials explicitly. Installation has bounded archive size, file count, expanded bytes, output and runtime. The desktop launch wrapper supervises the unchanged pinned helper through an anonymous parent pipe. Normal quit, parent-pipe loss or the runtime limit requests graceful cleanup, then bounds a still-live owned process group with a hard stop. A normal cancellation removes the owned partial installation and lease. An abrupt process or machine crash may leave a `.runtime-install.lock` and `.runtime-partial-*` directory. Do not remove those while an installer is running. After fully quitting this application and confirming that its installer is stopped, retain a backup of the dedicated desktop data directory before an operator removes only the abandoned optional-runtime lease/partial directory. Never delete research stores to recover a runtime. An unexpected existing install is not automatically overwritten or migrated.

Installed files are rehashed before use. Corruption disables the optional runtime and leaves Core available; source-linked historical results remain readable. There is no background installation, guaranteed storage recovery, automatic provider fallback or bundled model. Runtime archives are executable code and must be kept with their verified binding. Current private artifacts have not completed public native-component/source review or production signing/notarization; their SBOM is inventory evidence, not legal clearance or a public-distribution approval.
